"""Prepare unfinished source programs without resolution (§15.8)."""

import copy

from .assembly import MergedMapping, kind, merge_nodes, project, selected_slot
from .lexer import AkanError
from .parser import (Expression, Mapping, Merge, MultiMap, Sequence, Slot,
                     children)


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


def _chain(earlier, later):
    node = Merge(earlier.line, earlier.col, earlier, later, authored=False)
    node.source = earlier.source
    return node


def _slot_program(node, history):
    if isinstance(node, Slot):
        layers = node.layers if node.abstract else _coalesce_overrides(node.layers, history)
        first = copy.copy(node)
        first.layers = [layers[0]]
        tails = []
        for layer in layers[1:]:
            if node.abstract:
                later = copy.copy(node)
                later.layers = [layer]
                tails.append(later)
            else:
                tails.append(layer)
        return first, tails
    if isinstance(node, Merge):
        first, tails = _slot_program(node.args[0], history)
        return first, tails + [node.args[1]]
    view = project(node)
    if isinstance(view, Slot):
        return _slot_program(view, history)
    raise AkanError("cannot save this slot program: its selected slot has no "
                    "attached field representation (SPEC §15.8)",
                    node.line, node.col, node.source)


def _has_history(node, memo):
    pending = [(node, False)]
    while pending:
        value, visited = pending.pop()
        if id(value) in memo:
            continue
        if value.fill_checks:
            memo[id(value)] = (value, True)
        elif visited:
            memo[id(value)] = (value, any(memo[id(child)][1]
                                         for child in children(value)))
        else:
            pending.append((value, True))
            pending.extend((child, False) for child in children(value)
                           if id(child) not in memo)
    return memo[id(node)][1]


def _collapse(node, history):
    if not isinstance(node, (MergedMapping, Merge)):
        return node
    view = project(node)
    if isinstance(view, MergedMapping):
        if view.pending_key() is not None:
            if view.layers and not _has_history(view, history):
                earlier, later = view.layers
                if type(earlier) is Mapping and not earlier.pairs:
                    return later
                if type(later) is Mapping and not later.pairs:
                    return earlier
            return node
        view.finish()
        if _has_history(view, history):
            return view
        out = Mapping(view.line, view.col, list(view.pairs))
        out.source = view.source
        return out
    return view


def _can_coalesce(earlier, later, history):
    """Prove sequential dictionary overrides safe for an unknown filler."""
    pending = [(earlier, later)]
    while pending:
        earlier, later = (_collapse(value, history) for value in pending.pop())
        if type(earlier) is not Mapping or not isinstance(later, Mapping):
            return False
        if _has_history(earlier, history) or _has_history(later, history):
            return False
        if not earlier.pairs:
            continue
        if type(later) is not Mapping:
            return False
        if earlier.pending_key() is not None or later.pending_key() is not None:
            return False
        originals = {pair.key: pair for pair in earlier.pairs}
        for incoming in later.pairs:
            original = originals.get(incoming.key)
            if original is None or kind(project(incoming.value)) == "atom":
                continue
            if original.replace or incoming.replace:
                return False
            pending.append((original.value, incoming.value))
    return True


def _coalesce_overrides(layers, history):
    out = [_collapse(layers[0], history)]
    for layer in layers[1:]:
        later = _collapse(layer, history)
        earlier = out[-1]
        if _can_coalesce(earlier, later, history):
            out[-1] = (later if not earlier.pairs else
                       _collapse(merge_nodes(earlier, later), history))
        else:
            out.append(later)
    return out


def _prepare(node, history):
    _check_fills(node)
    node = _collapse(node, history)
    if isinstance(node, MergedMapping) and node.layers:
        layers = [_prepare(layer, history) for layer in node.layers]
        out = layers[0]
        for layer in layers[1:]:
            out = _chain(out, layer)
        return out
    if isinstance(node, Expression):
        node.args = [_prepare(arg, history) if arg is not None else None for arg in node.args]
        if node.op == "group" and not isinstance(node.args[0], Expression):
            return node.args[0]
        return _chain(*node.args) if isinstance(node, Merge) else node
    if isinstance(node, Mapping):
        nearby = node.pending_key() is None and not _has_history(node, history)
        groups, tails = [[]], []
        for pair in node.pairs:
            groups[-1].append(pair)
            if selected_slot(pair.value) is not None:
                first, additions = _slot_program(pair.value, history)
                pair.value = _prepare(first, history)
                for addition in additions:
                    later = copy.copy(pair)
                    later.value, later.replace = _prepare(addition, history), False
                    if nearby:
                        groups.append([later])
                    else:
                        tails.append([later])
            else:
                pair.value = _prepare(pair.value, history)
        node.pairs = groups[0]
        node.reindex()
        out = node
        for pairs in groups[1:] + tails:
            layer = Mapping(node.line, node.col, pairs)
            layer.source = node.source
            out = _chain(out, layer)
        return out
    if isinstance(node, Slot):
        node.layers = [_prepare(layer, history) for layer in node.layers]
    elif isinstance(node, Sequence):
        node.items = [_prepare(item, history) for item in node.items]
    elif isinstance(node, MultiMap):
        for pair in node.entries:
            pair.value = _prepare(pair.value, history)
    return node


def to_source(root, *, source=None):
    from .emitter import _lines

    node = _prepare(copy.deepcopy(root), {})
    return "".join(line + "\n" for line in _lines(node, 0, source, unresolved=True))
