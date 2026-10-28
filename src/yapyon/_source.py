"""Prepare unfinished source programs without resolution (§15.8)."""

import copy

from .assembly import MergedMapping, project, selected_slot
from .lexer import AkanError
from .parser import (Expression, Mapping, Merge, MultiMap, Sequence, Slot)


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


def _slot_program(node):
    if isinstance(node, Slot):
        first = copy.copy(node)
        first.layers = [node.layers[0]]
        return first, list(node.layers[1:])
    if isinstance(node, Merge):
        first, tails = _slot_program(node.args[0])
        return first, tails + [node.args[1]]
    view = project(node)
    if isinstance(view, Slot):
        return _slot_program(view)
    raise AkanError("cannot save this slot program: its selected slot has no "
                    "attached field representation (SPEC §15.8)",
                    node.line, node.col, node.source)


def _prepare(node):
    _check_fills(node)
    if isinstance(node, MergedMapping) and node.layers:
        layers = [_prepare(layer) for layer in node.layers]
        out = layers[0]
        for layer in layers[1:]:
            out = _chain(out, layer)
        return out
    if isinstance(node, Expression):
        node.args = [_prepare(arg) if arg is not None else None for arg in node.args]
        return node
    if isinstance(node, Mapping):
        tails = []
        for pair in node.pairs:
            if selected_slot(pair.value) is not None:
                first, additions = _slot_program(pair.value)
                pair.value = _prepare(first)
                for addition in additions:
                    later = copy.copy(pair)
                    later.value, later.replace = _prepare(addition), False
                    layer = Mapping(node.line, node.col, [later])
                    layer.source = node.source
                    tails.append(layer)
            else:
                pair.value = _prepare(pair.value)
        node.reindex()
        out = node
        for layer in tails:
            out = _chain(out, layer)
        return out
    if isinstance(node, Slot):
        node.layers = [_prepare(layer) for layer in node.layers]
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
