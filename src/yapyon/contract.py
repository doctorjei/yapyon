"""Contracts and declared functions — SPEC §13.2–§13.6.

A **contract** is a yapyon record naming the functions a document may call,
with each one's parameters, result type, and where each language finds its
code. It is given to the loader, never named by a document (ehmon 3):

    contract = yapyon.loads_contract(text)
    data = yapyon.loads(doc, contract=contract, provide={"sym": fn})

This module holds the contract reader, the Python binding (`impl.python`:
`from` imports a module, otherwise `provide=` supplies the code by its
`symbol`), the **borrow** a function receives for a container argument, and
the conversion of a function's result back into fresh document data. The
call itself — shape, arguments inside-out, deferral — is the resolver's one
call path, shared with the built-ins.

**A borrow is read-only and downward** (§13.1): `Mapping`, `Sequence`, and
multimap views over the node itself, in document order, that can reach the
node's descendants and nothing else. The same node lent twice in one load is
the same view. Values below a declared type arrive as that type says —
an `int` where `float` is declared arrives as a `float` (§13.3).
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Mapping as _MappingABC
from collections.abc import Sequence as _SequenceABC

from ._digits import REFUSE_DIGITS, WARN_DIGITS, decimal_digits
from .lexer import AkanError, Lexer, fold_name, is_dunder, is_identifier
from .parser import Mapping, MultiMap, Node, Pair, Parser, Scalar, Sequence
from .typespec import (WIDENED, Type, TypeSpecError, choose, choose_value,
                       parse_type, show, value_kind)

#: The language this implementation reads from `impl` (§13.2). Others are
#: ignored, whatever their names.
LANGUAGE = "python"

_FUNCTION_KEYS = ("params", "returns", "impl")
_IMPL_KEYS = ("symbol", "from")


class Declared:
    """One function a contract declares."""

    __slots__ = ("name", "params", "returns", "symbol", "module", "line",
                 "col")

    def __init__(self, name, params, returns, symbol, module, line, col):
        self.name, self.params, self.returns = name, params, returns
        self.symbol, self.module = symbol, module
        self.line, self.col = line, col

    def __repr__(self):
        args = ", ".join(f"{p}: {show(t)}" for p, t in self.params)
        return f"Declared({self.name}({args}) -> {show(self.returns)})"


class Contract:
    """The functions a document may call, by name (§13.2)."""

    def __init__(self, functions: dict, source: str | None = None):
        self.functions, self.source = dict(functions), source

    def __contains__(self, name):
        return name in self.functions

    def __getitem__(self, name) -> Declared:
        return self.functions[name]

    def __iter__(self):
        return iter(self.functions)

    def __repr__(self):
        return f"Contract({', '.join(self.functions)})"


# --------------------------------------------------------------------------- #
# Reading a contract
# --------------------------------------------------------------------------- #
def loads_contract(text: str, *, source: str | None = None) -> Contract:
    """Read a contract from text. It is a record (§12), so it needs no
    resolver; every key is checked, at every level (§13.2)."""
    from .loader import _refuse_deferred
    lexer = Lexer(text, source=source)
    tokens = lexer.tokenize()
    tree = Parser(tokens, lexer.warnings, source=source).parse()
    _refuse_deferred(tokens, source)
    return Contract(_Reader(source).read(tree), source)


def load_contract(fp, *, source: str | None = None) -> Contract:
    """Read a contract from an open file (text mode, UTF-8)."""
    from .loader import _name_of
    return loads_contract(fp.read(), source=_name_of(fp, source))


class _Reader:
    def __init__(self, source):
        self.source = source

    def akan(self, msg, node):
        raise AkanError(msg, node.line, node.col, self.source)

    def mapping(self, node, what):
        if not isinstance(node, Mapping):
            self.akan(f"{what} is a mapping", node)
        return node

    def string(self, node, what):
        if not (isinstance(node, Scalar) and node.type == "str"):
            self.akan(f"{what} is a string", node)
        return node.value

    def type_(self, node, what):
        try:
            return parse_type(self.string(node, f"{what} — a type —"))
        except TypeSpecError as exc:
            self.akan(f"{what}: {exc}", node)

    def read(self, tree) -> dict:
        functions = {}
        for pair in self.mapping(tree, "a contract").pairs:
            functions[pair.key] = self.function(pair)
        return functions

    def function(self, pair) -> Declared:
        name = pair.key
        body = self.mapping(pair.value, f"function {name}'s declaration")
        for field in body.pairs:
            if field.key not in _FUNCTION_KEYS:
                self.akan(f"{name}: {field.lexeme or field.key!r} is not a "
                          f"contract key; a function declares "
                          f"{', '.join(_FUNCTION_KEYS)}", field)
        for required in _FUNCTION_KEYS:
            if required not in body.by_key:
                self.akan(f"{name}: {required} is required", pair)
        params = [(p.key, self.type_(p.value, f"{name}'s parameter {p.key}"))
                  for p in self.mapping(body.by_key["params"],
                                        f"{name}'s params").pairs]
        returns = self.type_(body.by_key["returns"], f"{name}'s returns")
        impl = self.mapping(body.by_key["impl"], f"{name}'s impl")
        entry = impl.by_key.get(LANGUAGE)
        if entry is None:
            self.akan(f"{name} has no impl.{LANGUAGE} entry, so this "
                      f"implementation cannot call it", pair)
        entry = self.mapping(entry, f"{name}'s impl.{LANGUAGE}")
        for field in entry.pairs:
            if field.key not in _IMPL_KEYS:
                self.akan(f"{name}: {field.lexeme or field.key!r} is not an "
                          f"impl key; a language entry has "
                          f"{' and '.join(_IMPL_KEYS)}", field)
        if "symbol" not in entry.by_key:
            self.akan(f"{name}: impl.{LANGUAGE}.symbol is required", entry)
        symbol = self.string(entry.by_key["symbol"], f"{name}'s symbol")
        module = (self.string(entry.by_key["from"], f"{name}'s from")
                  if "from" in entry.by_key else None)
        return Declared(name, params, returns, symbol, module,
                        pair.line, pair.col)


# --------------------------------------------------------------------------- #
# Binding: where the Python code comes from
# --------------------------------------------------------------------------- #
class BindError(Exception):
    """The code for a declared function cannot be found."""


class Functions:
    """A contract bound to this load: `provide` supplies the code for every
    function declared without `from`. Code is found at the first call, so a
    contract's unused imports never run."""

    def __init__(self, contract: Contract, provide=None):
        self.contract, self.provide = contract, dict(provide or {})
        self._code: dict[str, object] = {}

    def get(self, name: str) -> Declared | None:
        return self.contract.functions.get(name)

    def code(self, declared: Declared):
        if declared.name not in self._code:
            self._code[declared.name] = self._find(declared)
        return self._code[declared.name]

    def _find(self, declared: Declared):
        if declared.module is None:
            if declared.symbol not in self.provide:
                raise BindError(f"{declared.name}() is declared without "
                                f"`from`, so the loader must provide its "
                                f"code, and provide= has no "
                                f"{declared.symbol!r}")
            found = self.provide[declared.symbol]
        else:
            try:
                found = importlib.import_module(declared.module)
                for part in declared.symbol.split("."):
                    found = getattr(found, part)
            except (ImportError, AttributeError) as exc:
                raise BindError(f"{declared.name}(): cannot load "
                                f"{declared.symbol!r} from "
                                f"{declared.module!r} ({exc})") from None
        if not callable(found):
            raise BindError(f"{declared.name}(): {declared.symbol!r} is not "
                            f"callable")
        return found


# --------------------------------------------------------------------------- #
# Borrows: what a function receives for a node (§13.1)
# --------------------------------------------------------------------------- #
class Lender:
    """Makes borrows for one load, so the same node lent twice under the
    same type is the same object — a borrow keeps the node's identity."""

    def __init__(self):
        self._views: dict = {}

    def value(self, node: Node, union):
        """`node` as a host value under `union` (`None` means `Any`)."""
        alt = None
        if union is not None:
            alt, _ = choose(node, union)
            if alt is not None and alt.name == "Any":
                alt = None
        if isinstance(node, Scalar):
            if alt is not None and alt.name == "float" and node.type == "int":
                return float(node.value)
            return node.value
        item = None if alt is None else alt.item
        key = (id(node), item)
        if key not in self._views:
            view = (BorrowedMapping if isinstance(node, Mapping) else
                    BorrowedMultimap if isinstance(node, MultiMap) else
                    BorrowedList)
            self._views[key] = view(node, item, self)
        return self._views[key]


def float_misfit(node: Node, union) -> Node | None:
    """The first `int` that would widen to a `float` it has no float for
    (§13.3: "an `int` outside the float range is akan"), or None."""
    if union is None:
        return None
    alt, level = choose(node, union)
    if alt is None or alt.name == "Any" or level != WIDENED:
        return None
    if isinstance(node, Scalar):
        try:
            float(node.value)
        except OverflowError:
            return node
        return None
    children = (node.items if isinstance(node, Sequence) else
                [p.value for p in getattr(node, "pairs", None) or node.entries])
    for child in children:
        found = float_misfit(child, alt.item)
        if found is not None:
            return found
    return None


class _Borrow:
    __slots__ = ("_node", "_item", "_lender")

    def __init__(self, node, item, lender):
        self._node, self._item, self._lender = node, item, lender

    def _lend(self, child):
        return self._lender.value(child, self._item)

    def __setattr__(self, name, value):
        if name in _Borrow.__slots__ and not hasattr(self, name):
            object.__setattr__(self, name, value)
            return
        raise TypeError("a borrow is read-only (SPEC §13.1)")


class BorrowedMapping(_Borrow, _MappingABC):
    """A borrowed mapping: keys in document order, values lent in turn."""
    __slots__ = ()

    def __getitem__(self, key):
        return self._lend(self._node.by_key[fold_name(key)]
                          if isinstance(key, str) else self._node.by_key[key])

    def __iter__(self):
        return (pair.key for pair in self._node.pairs)

    def __len__(self):
        return len(self._node.pairs)

    def __repr__(self):
        return f"BorrowedMapping({dict(self)!r})"


class BorrowedList(_Borrow, _SequenceABC):
    """A borrowed list, in document order."""
    __slots__ = ()

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self._lend(item) for item in self._node.items[index])
        return self._lend(self._node.items[index])

    def __len__(self):
        return len(self._node.items)

    def __repr__(self):
        return f"BorrowedList({list(self)!r})"


class BorrowedMultimap(_Borrow):
    """A borrowed multimap: `(key, value)` entries in document order,
    as `for k, v in mm` reads an `OrderedMultimap`."""
    __slots__ = ()

    def __iter__(self):
        return ((entry.key, self._lend(entry.value))
                for entry in self._node.entries)

    def __len__(self):
        return len(self._node.entries)

    def keys(self):
        return tuple(dict.fromkeys(entry.key for entry in self._node.entries))

    def get(self, key, default=()):
        found = tuple(self._lend(e.value) for e in self._node.entries
                      if e.key == fold_name(key))
        return found or default

    def __contains__(self, key):
        return any(e.key == fold_name(key) for e in self._node.entries)

    def __repr__(self):
        return f"BorrowedMultimap({list(self)!r})"


# --------------------------------------------------------------------------- #
# Results: fresh data, checked and folded (§13.4)
# --------------------------------------------------------------------------- #
class ResultError(Exception):
    """A returned value that is not yapyon data of the declared type."""


def result_node(value, union, at: Node, *, max_digits: int, warn) -> Node:
    """A function's result as a new node at the call site: checked against
    `returns` deep, an `int` widened where `float` is declared, keys held to
    the identifier rule and folded. It has no lexemes (§13.4)."""
    if _holds_borrow(value):
        raise ResultError("returned a node of the document; a result is fresh "
                          "data (§13.4) — copy what you mean to return")
    alt, _ = choose_value(value, union)
    if alt is None:
        _explain(value, union)
        raise ResultError(f"returned {value_kind(value)}, but its contract "
                          f"declares {show(union)}")
    return _node(value, alt, at, max_digits, warn)


def _explain(value, union) -> None:
    """Where a container of the declared kind fails, say what inside it
    failed rather than only that the whole did not match."""
    kind = value_kind(value)
    for alt in union:
        if alt.name == kind and alt.item is not None:
            _node(value, alt, Scalar(0, 0, "none", None), REFUSE_DIGITS, None)


def _holds_borrow(value) -> bool:
    from .multimap import OrderedMultimap
    if isinstance(value, _Borrow):
        return True
    if isinstance(value, dict):
        return any(map(_holds_borrow, value.values()))
    if isinstance(value, (list, tuple)):
        return any(map(_holds_borrow, value))
    if isinstance(value, OrderedMultimap):
        return any(_holds_borrow(entry.value) for entry in value)
    return False


def _node(value, alt: Type, at, max_digits, warn) -> Node:
    if alt.name == "Any":
        alt = Type("Any")
    kind = value_kind(value)
    line, col = at.line, at.col
    if kind == "float" or (kind == "int" and alt.name == "float"):
        try:
            number = float(value)
        except OverflowError:
            raise ResultError(f"returned an int outside the float range, "
                              f"where float is declared") from None
        if math.isinf(number) or math.isnan(number):
            raise ResultError(f"returned {number}; yapyon has no infinity "
                              f"or NaN")
        return Scalar(line, col, "float", number)
    if kind == "int":
        digits = decimal_digits(value)
        if digits > max_digits:
            raise ResultError(f"returned an integer of {digits:,} decimal "
                              f"digits, past this implementation's ceiling "
                              f"of {max_digits:,} (SPEC §3.1)")
        if digits > WARN_DIGITS and warn is not None:
            warn(f"returned an integer of {digits:,} decimal digits: past "
                 f"{WARN_DIGITS:,}, converting decimal is costly (SPEC §3.1)")
        return Scalar(line, col, "int", value)
    if kind in ("str", "bytes", "bool"):
        return Scalar(line, col, kind, value)
    if kind == "None":
        return Scalar(line, col, "none", None)
    item = alt.item
    if kind == "list":
        return Sequence(line, col, [_child(v, item, at, max_digits, warn)
                                    for v in value])
    entries = value.items() if kind == "dict" else value
    pairs, seen = [], set()
    for key, child in entries:
        if not isinstance(key, str) or not is_identifier(key) \
                or is_dunder(fold_name(key)):
            raise ResultError(f"returned the key {key!r}, which is not a "
                              f"name a document could write (§7)")
        folded = fold_name(key)
        if kind == "dict" and folded in seen:
            raise ResultError(f"returned two keys that fold to {folded!r}")
        seen.add(folded)
        pairs.append(Pair(line, col, folded,
                          _child(child, item, at, max_digits, warn)))
    if kind == "dict":
        return Mapping(line, col, pairs)
    return MultiMap(line, col, pairs)


def _child(value, item, at, max_digits, warn) -> Node:
    if item is None:
        return _node(value, Type("Any"), at, max_digits, warn)
    alt, _ = choose_value(value, item)
    if alt is None:
        raise ResultError(f"returned {value_kind(value)} inside its result, "
                          f"where {show(item)} is declared")
    return _node(value, alt, at, max_digits, warn)
