"""Prepare an unfinished Tree for source writing without resolution (§15.8)."""

import copy

from .assembly import MergedMapping, merge_nodes
from .lexer import AkanError
from .parser import Mapping, MultiMap, Sequence, Slot, YString


def _pattern(key):
    if isinstance(key, str):
        return tuple(key)
    out = []
    for kind, text in key.parts:
        if kind == "text":
            out.extend(text)
        elif not out or out[-1] is not None:
            out.append(None)
    return tuple(out)


def _could_match(left, right):
    """Intersect literal-text patterns, treating each hole as any string."""
    a, b = _pattern(left), _pattern(right)
    pending, seen = [(0, 0)], set()
    while pending:
        i, j = pending.pop()
        if (i, j) in seen:
            continue
        seen.add((i, j))
        if i == len(a) and j == len(b):
            return True
        if i < len(a) and a[i] is None:
            pending.append((i + 1, j))
        if j < len(b) and b[j] is None:
            pending.append((i, j + 1))
        if i < len(a) and j < len(b):
            if a[i] is None or b[j] is None or a[i] == b[j]:
                pending.append((i if a[i] is None else i + 1,
                                j if b[j] is None else j + 1))
    return False


def _check_merge(node):
    earlier = []
    for layer in node.key_layers():
        for pair in layer.pairs:
            for other in earlier:
                if (not isinstance(pair.key, YString)
                        and not isinstance(other.key, YString)):
                    continue
                if _could_match(pair.key, other.key):
                    computed, competing = ((pair, other) if isinstance(pair.key, YString)
                                           else (other, pair))
                    where = _where(competing)
                    raise AkanError(
                        f"cannot save this dictionary merge: computed key "
                        f"{computed.lexeme!r} could match "
                        f"{competing.lexeme or competing.key!r} from another "
                        f"layer (at {where}); keep the merge in memory or "
                        "remove the competing contribution before saving "
                        "(SPEC §15.8)",
                        computed.line, computed.col, computed.source)
        earlier.extend(layer.pairs)


def _check_fills(node):
    for check in node.fill_checks:
        if not check.check():
            slot = check.slot
            raise AkanError(
                f"cannot save {slot.key}{slot.lexeme or '<>'}: this completed "
                "fill still has an undecided abstract-slot obligation; "
                "ordinary source cannot preserve that obligation — keep "
                "composing in memory or give explicit overrides before "
                "filling (SPEC §15.8)",
                slot.line, slot.col, slot.source)


def _mapping(node):
    if isinstance(node, MergedMapping) and node.layers:
        _check_merge(node)
    _check_fills(node)
    pairs = node.walk_pairs() if isinstance(node, MergedMapping) else node.pairs
    out = Mapping(node.line, node.col, pairs)
    out.source = node.source
    return out


def _where(node):
    return (f"{node.source}:{node.line}:{node.col}" if node.source else
            f"line {node.line}, col {node.col}")


def _replacement(slot, path, earlier, later):
    raise AkanError(
        f"cannot save {slot.key}{slot.lexeme or '<>'}: pending overrides "
        f"for {'.'.join(path)!r} would erase a replacement boundary "
        f"(at {_where(earlier)} and {_where(later)}), changing how a later "
        "filler is merged; fill this slot before saving or keep composing "
        "in memory (SPEC §15.8)",
        slot.line, slot.col, slot.source)


def _check_overrides(values, slot, path=()):
    """Override layers must act the same on a future, unknown filler."""
    if len(values) < 2:
        return
    combined = values[0]
    for value in values[1:]:
        combined = merge_nodes(combined, value)
    if isinstance(combined, Mapping):
        for i in range(len(values) - 2, -1, -1):
            if not isinstance(values[i], Mapping):
                _replacement(slot, path, values[i], values[i + 1])
        groups = {}
        for value in values:
            for pair in _mapping(value).pairs:
                if isinstance(pair.key, str):
                    groups.setdefault(pair.key, []).append(pair.value)
        for key, contributions in groups.items():
            _check_overrides(contributions, slot, path + (key,))
    elif isinstance(combined, Slot):
        named = False
        for i, value in enumerate(values):
            if named:
                if not isinstance(value, Mapping):
                    _replacement(slot, path, values[i - 1], value)
            elif isinstance(value, Slot):
                named = not value.abstract
            else:
                following = next(v for v in values[i + 1:] if isinstance(v, Slot))
                _replacement(slot, path, value, following)


def _prepare(node):
    if isinstance(node, Mapping):
        out = _mapping(node)
        for pair in out.pairs:
            pair.value = _prepare(pair.value)
        return out
    _check_fills(node)
    if isinstance(node, Slot):
        overrides = Mapping(node.line, node.col, [])
        for layer in node.layers:
            overrides = merge_nodes(overrides, layer)
        if isinstance(overrides, MergedMapping) and overrides.layers:
            _check_merge(overrides)
        _check_overrides(node.layers, node)
        node.layers = [_prepare(overrides)]
    elif isinstance(node, Sequence):
        node.items = [_prepare(item) for item in node.items]
    elif isinstance(node, MultiMap):
        for pair in node.entries:
            pair.value = _prepare(pair.value)
    return node


def to_source(root, *, source=None):
    from .emitter import _lines

    node = _prepare(copy.deepcopy(root))
    return "".join(line + "\n" for line in _lines(node, 0, source, unresolved=True))
