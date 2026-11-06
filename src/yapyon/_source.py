"""Prepare unfinished source programs without resolution (§15.8)."""

import copy

from .assembly import MergedMapping, empty_overrides, project, selected_slot
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
    if (empty_overrides(later) and isinstance(earlier, Merge)
            and empty_overrides(earlier.args[1])):
        return earlier
    node = Merge(earlier.line, earlier.col, earlier, later, authored=False)
    node.source = earlier.source
    return node


def _marked(node):
    empty = Mapping(node.line, node.col, [])
    empty.source = node.source
    return _chain(node, empty)


def _slot_program(node):
    if isinstance(node, Slot):
        first = copy.copy(node)
        first.layers = [node.layers[0]]
        tails = []
        for layer in node.layers[1:]:
            if node.abstract:
                later = copy.copy(node)
                later.layers = [layer]
                tails.append(later)
            else:
                tails.append(layer)
        return first, tails
    if isinstance(node, Merge):
        first, tails = _slot_program(node.args[0])
        return first, tails + [node.args[1]]
    view = project(node)
    if isinstance(view, Slot):
        return _slot_program(view)
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
    if not isinstance(node, (MergedMapping, Merge)) or _has_history(node, history):
        return node
    view = project(node)
    if isinstance(view, MergedMapping):
        if view.pending_key() is not None:
            return node
        view.finish()
        out = Mapping(view.line, view.col, list(view.pairs))
        out.source = view.source
        # A dictionary program emptied by later edits is not literal slot overrides.
        return _marked(out)
    return view


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
        tails = []
        for pair in node.pairs:
            if selected_slot(pair.value) is not None:
                first, additions = _slot_program(pair.value)
                pair.value = _prepare(first, history)
                for addition in additions:
                    later = copy.copy(pair)
                    later.value, later.replace = _prepare(addition, history), False
                    layer = Mapping(node.line, node.col, [later])
                    layer.source = node.source
                    tails.append(layer)
            else:
                pair.value = _prepare(pair.value, history)
        node.reindex()
        out = node
        for layer in tails:
            out = _chain(out, layer)
        return _marked(out) if tails or node.retained_program else out
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
