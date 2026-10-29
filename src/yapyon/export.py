"""Host values to canonical record text, without evaluating document source.

The caller keeps input stable during serialization. These functions do not lock
caller-owned containers or promise a snapshot of concurrent mutations.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from ._digits import REFUSE_DIGITS, WARN_DIGITS, decimal_digits
from ._keys import KeyMap, key_error, name_key
from ._values import PathAkan, scalar_kind
from .emitter import _emit_prepared
from .lexer import fold_name
from .multimap import OrderedMultimap
from .parser import Mapping, MultiMap, Pair, Scalar, Sequence

MAX_DEPTH = 128
MAX_SIZE = 4 * 1024 * 1024


@dataclass(frozen=True)
class _Options:
    max_digits: int
    max_depth: int
    max_size: int
    warn: object


def _options(max_digits, max_depth, max_size, warn):
    for name, value, minimum in (("max_digits", max_digits, WARN_DIGITS),
                                 ("max_depth", max_depth, 1),
                                 ("max_size", max_size, 1)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{name} must be an integer")
        if int.__int__(value) < minimum:
            raise ValueError(f"{name} must be at least {minimum}")
    if warn is not None and not callable(warn):
        raise TypeError("warn must be callable or None")
    return _Options(int.__int__(max_digits), int.__int__(max_depth),
                    int.__int__(max_size), warn)


class _Path:
    __slots__ = ("parent", "step")

    def __init__(self, parent=None, step="root"):
        self.parent, self.step = parent, step

    def child(self, step):
        return _Path(self, step)

    def __str__(self):
        steps, here = [], self
        while here is not None:
            steps.append(here.step)
            here = here.parent
        return "".join(reversed(steps))


class _Budget:
    def __init__(self, maximum):
        self.maximum, self.used = maximum, 0

    def check(self, amount, path):
        if amount > self.maximum - self.used:
            raise ValueError(f"at {path}: serialized UTF-8 exceeds max_size "
                             f"of {self.maximum} bytes")

    def spend(self, amount, path):
        self.check(amount, path)
        self.used += amount

    def text(self, value, path):
        if len(value) > self.maximum - self.used:
            self.spend(len(value), path)
        for start in range(0, len(value), 4096):
            try:
                size = len(value[start:start + 4096].encode("utf-8"))
            except UnicodeEncodeError:
                raise ValueError(f"at {path}: text contains a lone surrogate") from None
            self.spend(size, path)


def _key(value, named, path, budget):
    if not isinstance(value, str):
        raise TypeError(f"at {path}: a key must be a string")
    budget.check(str.__len__(value) + 2, path)
    value = str.__str__(value)
    budget.text(value, path)
    why = key_error(value)
    if why:
        raise ValueError(f"at {path}: {why}")
    exact_name = name_key(value) and fold_name(value) == value
    if named is not None and not isinstance(named, bool):
        raise ValueError(f"at {path}: inconsistent key-kind provenance")
    if named is None:
        named = exact_name
    elif named and not exact_name:
        raise ValueError(f"at {path}: inconsistent name-key provenance; "
                         "the exact key cannot be written as a name")
    budget.spend(2 if named else 4, path)
    return value, bool(named)


def _key_step(key, index, *, multimap=False):
    if not isinstance(key, str):
        return f"[entry {index} key]"
    text = repr(str.__getitem__(key, slice(0, 64)))
    if str.__len__(key) > 64:
        text += f"...; entry {index}"
    return f"[entry {index}: {text}]" if multimap else f"[{text}]"


def _children(value, node, path, budget):
    if isinstance(node, Sequence):
        for index, child in enumerate(list.__iter__(value)):
            child_path = path.child(f"[{index}]")
            if index:
                budget.spend(2, child_path)
            yield child, child_path, node.items.append
        return
    if isinstance(node, Mapping):
        entries = dict.items(value)
        provenance = value._non_names if isinstance(value, KeyMap) else None
    else:
        entries, provenance = iter(dict.values(value._seq)), None
    seen = set()
    for index, entry in enumerate(entries):
        if isinstance(node, Mapping):
            key, child = entry
            named = None if provenance is None else key not in provenance
        else:
            key, child, named = entry.key, entry.value, entry._named
        child_path = path.child(_key_step(key, index, multimap=isinstance(node, MultiMap)))
        if isinstance(node, MultiMap):
            budget.spend(2, child_path)
        key, named = _key(key, named, child_path, budget)
        if isinstance(node, Mapping):
            if key in seen:
                raise ValueError(f"at {child_path}: duplicate exact string-key value")
            seen.add(key)

        def put(child_node, key=key, named=named, node=node):
            pairs = node.pairs if isinstance(node, Mapping) else node.entries
            pairs.append(Pair(0, 0, key, child_node, named=named))

        yield child, child_path, put


def _scalar(value, kind, path, options, budget):
    if kind == "str":
        budget.check(str.__len__(value) + 2, path)
        value = str.__str__(value)
        budget.text(value, path)
        budget.spend(2, path)
    elif kind == "bytes":
        budget.check(bytes.__len__(value) + 3, path)
        value = bytes.__bytes__(value)
        budget.spend(len(value) + 3, path)
    elif kind == "int":
        bits = int.bit_length(value)
        # log2(10) is below 3.322; refuse definite excess before large powers.
        def exceeds(ceiling):
            return ceiling < bits and bits > (ceiling * 3322 + 999) // 1000

        if exceeds(options.max_digits):
            lower = (bits - 1) * 30102999566 // 100000000000 + 1
            raise ValueError(f"at {path}: integer has at least {lower} decimal "
                             f"digits, past max_digits of {options.max_digits}")
        remaining = budget.maximum - budget.used
        if exceeds(remaining):
            budget.check(remaining + 1, path)
        value = int.__int__(value)
        digits = decimal_digits(value)
        if digits > options.max_digits:
            raise ValueError(f"at {path}: integer has {digits} decimal digits, "
                             f"past max_digits of {options.max_digits}")
        budget.spend(digits + (value < 0), path)
        if digits > WARN_DIGITS and options.warn is not None:
            options.warn(f"shiran: at {path}: integer has {digits} decimal digits; "
                         f"past {WARN_DIGITS}, decimal conversion is costly")
    elif kind == "float":
        value = float.__float__(value)
        if not math.isfinite(value):
            raise ValueError(f"at {path}: a float must be finite")
        budget.spend(len(repr(value)), path)
    else:
        budget.spend(4 if value is None or value is True else 5, path)
    return Scalar(0, 0, kind, value)


def _adapt(value, options):
    budget, active, root = _Budget(options.max_size), {}, []
    path = _Path()
    pending = [("value", value, path, 0, root.append)]
    while pending:
        task = pending.pop()
        if task[0] == "children":
            _, original, node, path, depth, iterator = task
            try:
                child, child_path, put = next(iterator)
            except StopIteration:
                del active[id(original)]
                if isinstance(node, Mapping):
                    node.reindex()
                continue
            pending.append(task)
            pending.append(("value", child, child_path, depth, put))
            continue
        _, original, path, depth, put = task
        kind = scalar_kind(original)
        if kind is not None:
            put(_scalar(original, kind, path, options, budget))
            continue
        if isinstance(original, dict):
            node = Mapping(0, 0, [])
            empty = not dict.__len__(original)
        elif isinstance(original, list):
            node = Sequence(0, 0, [])
            empty = not list.__len__(original)
        elif isinstance(original, OrderedMultimap):
            node = MultiMap(0, 0, [])
            empty = not OrderedMultimap.__len__(original)
        else:
            raise TypeError(f"at {path}: {type(original).__name__} is not "
                            "supported record data")
        if id(original) in active:
            raise PathAkan(f"container cycle reaches ancestor at {active[id(original)]}",
                           str(path))
        depth += 1
        if depth > options.max_depth:
            raise ValueError(f"at {path}: container depth {depth} exceeds "
                             f"max_depth of {options.max_depth}")
        # A lower bound limits adaptation work; the emitter measures actual bytes.
        minimum = 3 if isinstance(node, MultiMap) else 2
        if not empty and not isinstance(node, Sequence):
            minimum = 1
        budget.spend(minimum, path)
        active[id(original)] = path
        put(node)
        pending.append(("children", original, node, path, depth,
                        iter(_children(original, node, path, budget))))
    return root[0]


def _prepare(value, options):
    return _emit_prepared(_adapt(value, options), options.max_size)


def dumps(value, *, max_digits=REFUSE_DIGITS, max_depth=MAX_DEPTH,
          max_size=MAX_SIZE, warn=None) -> str:
    """Serialize supported host values as newline-terminated yapyon record text.

    Input must remain stable during serialization; synchronize concurrent
    mutations with a caller-owned lock. Shared acyclic containers are written
    independently. Actual cycles raise AkanError with a data path.
    """
    return _prepare(value, _options(max_digits, max_depth, max_size, warn))


def dump(value, fp, *, max_digits=REFUSE_DIGITS, max_depth=MAX_DEPTH,
         max_size=MAX_SIZE, warn=None) -> None:
    """Prepare record text, then write once to a caller-owned text stream.

    Do not close or flush the stream. Input/options are validated before writing;
    caller truncation and native I/O failures are not atomic file replacement.
    """
    options = _options(max_digits, max_depth, max_size, warn)
    write = getattr(fp, "write", None)
    if not callable(write):
        raise TypeError("fp must have a callable text write method")
    text = _prepare(value, options)
    count = write(text)
    if count is None:
        return
    if not isinstance(count, int) or isinstance(count, bool):
        raise TypeError("text write must return an integer count or None")
    if count != len(text):
        raise OSError("text stream did not report a complete write")


def dump_safe(value, path, *, max_digits=REFUSE_DIGITS, max_depth=MAX_DEPTH,
              max_size=MAX_SIZE, warn=None) -> None:
    """Save UTF-8 record text without truncating the destination while preparing.

    Follow destination symlinks and replace their selected target only after a
    separate complete file is written. On filesystem failure, preserve the native
    error and report a retained replacement through its recovery_path and notes.
    Input consistency still requires caller-owned synchronization when needed.
    """
    from ._safe import write_file

    options = _options(max_digits, max_depth, max_size, warn)
    write_file(_prepare(value, options), path)
