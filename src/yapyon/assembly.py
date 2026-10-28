"""The one merge operation, retaining unfinished composition programs (§15)."""

import copy
from collections import defaultdict, deque

from .lexer import AkanError, Yakamashiwa
from .parser import (Comprehension, Expression, Mapping, Merge, MultiMap, Pair,
                     ResolvedTemplate, Scalar, Sequence, Slot, YString, children)


class MergedMapping(Mapping):
    """A binary dictionary program with a cached, editable structural view."""

    def __init__(self, earlier, later, *, budget=None):
        if budget is not None:
            budget(earlier)
        self.layers = [earlier, later]
        self._views = {}
        self._merge_budget = budget
        super().__init__(earlier.line, earlier.col, [])
        self.source = earlier.source
        self.fill_checks = earlier.fill_checks + later.fill_checks

    def key_layers(self):
        """Original contributions, for key validation rather than combination."""
        for layer in self.layers:
            if isinstance(layer, MergedMapping) and layer.layers:
                yield from layer.key_layers()
            else:
                yield layer

    def visible_pairs(self):
        if not self.layers:
            return self.pairs
        groups = {}
        for layer in self.layers:
            pairs = layer.visible_pairs() if isinstance(layer, MergedMapping) else layer.pairs
            for pair in pairs:
                if self._merge_budget is not None:
                    self._merge_budget(pair)
                if isinstance(pair.key, str):
                    groups.setdefault(pair.key, []).append(pair)
        out = []
        for key, pairs in groups.items():
            signature = tuple((p, p.value, p.replace) for p in pairs)
            cached = self._views.get(key)
            if (cached is not None and len(cached[0]) == len(signature)
                    and all(a is d and b is e and c == f
                            for (a, b, c), (d, e, f) in zip(cached[0], signature))):
                pair = cached[1]
            else:
                pair = pairs[0] if len(pairs) == 1 else copy.copy(pairs[0])
                for later in pairs[1:]:
                    pair.value = (later.value if later.replace else
                                  merge_nodes(pair.value, later.value, budget=self._merge_budget))
                    pair.replace = pair.replace or later.replace
                self._views[key] = (signature, pair)
            out.append(pair)
        return out

    def walk_pairs(self):
        if not self.layers:
            return self.pairs
        known = {p.key: p for p in self.visible_pairs()}
        out = []
        for layer in self.key_layers():
            for pair in layer.pairs:
                if isinstance(pair.key, YString):
                    out.append(pair)
                elif pair.key in known:
                    out.append(known.pop(pair.key))
        return out

    def edit_pair(self, pair, new=None, *, remove=False):
        placed = False
        for layer in self.key_layers():
            kept = []
            for entry in layer.pairs:
                matches = (entry.key == pair.key if isinstance(pair.key, str)
                           else entry.identity == pair.identity)
                if not matches:
                    kept.append(entry)
                elif not remove and not placed:
                    replacement = copy.copy(pair)
                    replacement.value = new
                    kept.append(replacement)
                    placed = True
            layer.pairs = kept
            layer.reindex()
        self._invalidate()

    def _invalidate(self):
        for layer in self.layers:
            if isinstance(layer, MergedMapping) and layer.layers:
                layer._invalidate()
        self._views.clear()
        self.pairs = []
        self.reindex()

    def key_pair(self, key, *, named=False):
        if not self.layers:
            return super().key_pair(key, named=named)
        return Mapping(self.line, self.col, self.visible_pairs()).key_pair(key, named=named)

    def pending_key(self, depth=1):
        if not self.layers:
            return super().pending_key()
        if self._merge_budget is not None:
            self._merge_budget(self, depth=depth)
        for layer in self.layers:
            pending = (layer.pending_key(depth + 1) if isinstance(layer, MergedMapping)
                       else layer.pending_key())
            if pending is not None:
                return pending
        return None

    def waiting_for_name(self, key):
        if not self.layers:
            return None
        layers = list(self.key_layers())
        known = [(i, p) for i, layer in enumerate(layers)
                 for p in layer.pairs if p.key == key]
        if not known or not known[0][1].named:
            return None
        first, last = known[0][0], known[-1][0]
        occupied = {i for i, _ in known}
        for i, layer in enumerate(layers):
            pending = layer.pending_key()
            if pending is None or i in occupied:
                continue
            if i < first or i > last or kind(known[-1][1].value) != "atom":
                return pending
        return None

    def finish(self, depth=1):
        if self.layers and self._merge_budget is not None:
            self._merge_budget(self, depth=depth)
        if self.layers and self.pending_key(depth) is None:
            for layer in self.layers:
                if isinstance(layer, MergedMapping):
                    layer.finish(depth + 1)
            self.pairs = self.visible_pairs()
            self.layers = []
            self._views.clear()
            self._merge_budget = None
            self.reindex()
            return True
        return False


def kind(node):
    """A proven value kind, or None when computation must establish it."""
    if isinstance(node, Mapping):
        return "dict"
    if isinstance(node, Sequence):
        return "list"
    if isinstance(node, MultiMap):
        return "multimap"
    if isinstance(node, Scalar):
        return "none" if node.type == "none" else "atom"
    if isinstance(node, ResolvedTemplate):
        return "atom"
    if isinstance(node, YString) and not isinstance(node, Expression) and node.prefix != "(":
        return "atom"
    return None


def empty_overrides(node):
    return (type(node) is Mapping and not node.pairs and not node.fill_checks)


_PENDING = object()


def _combine(earlier, later, *, collections=False, charge=None, depth=1):
    later = project(later, budget=charge, depth=depth)
    if kind(later) == "atom":
        return later
    earlier = project(earlier, budget=charge, depth=depth)
    if isinstance(later, Slot):
        if isinstance(earlier, Slot) and earlier.abstract:
            out = copy.copy(later)
            out.layers = earlier.layers + later.layers
            return out
        return later
    if isinstance(earlier, Slot):
        if earlier.abstract:
            return later
        if isinstance(later, Mapping):
            out = copy.copy(earlier)
            out.layers = earlier.layers + [later]
            return out
        return later if kind(later) == "atom" else _PENDING
    a, b = kind(earlier), kind(later)
    if a == "dict" and b == "dict":
        return MergedMapping(earlier, later, budget=charge)
    containers = ("dict", "list", "multimap")
    if a == "none" and b in containers:
        return later
    if b == "none" and a in containers:
        return earlier
    if a is not None and b is not None:
        if a == b and a in ("list", "multimap"):
            return collection_merge(earlier, later, charge=charge) if collections else _PENDING
        return later
    return _PENDING


def merge_nodes(earlier, later, *, budget=None):
    """Construct without evaluating; the resolver settles unknown combinations."""
    out = _combine(earlier, later, charge=budget)
    retained_expression = (isinstance(out, MergedMapping)
                           and any(isinstance(value, Expression) and not isinstance(value, Mapping)
                                   for value in (earlier, later)))
    if out is _PENDING or retained_expression:
        out = Merge(earlier.line, earlier.col, earlier, later, authored=False)
        out.source = earlier.source
        out.fill_checks = earlier.fill_checks + later.fill_checks
        out._merge_budget = budget
    return out


def project(node, *, collections=False, budget=None, depth=1):
    """A structural view; the stored program remains the source authority."""
    budget = budget or getattr(node, "_merge_budget", None)
    if isinstance(node, Expression) and not isinstance(node, Merge) and node.op == "group":
        return project(node.args[0], collections=collections, budget=budget, depth=depth)
    if not isinstance(node, Merge):
        return node
    if budget is not None:
        budget(node, depth=depth)
    later = project(node.args[1], collections=collections, budget=budget, depth=depth + 1)
    earlier = (node.args[0] if kind(later) == "atom" else
               project(node.args[0], collections=collections, budget=budget, depth=depth + 1))
    signature = (earlier, later, collections, budget)
    cached = getattr(node, "_projection", None)
    if (cached is not None and cached[0][0] is earlier
            and cached[0][1] is later and cached[0][2:] == signature[2:]):
        return cached[1]
    compare = collections and literal(earlier) and literal(later)
    out = _combine(earlier, later, collections=compare, charge=budget, depth=depth + 1)
    if out is _PENDING:
        return node
    node._projection = (signature, out)
    return out


def literal(node):
    if isinstance(node, (YString, Slot, ResolvedTemplate)):
        return False
    if isinstance(node, MergedMapping) and node.layers:
        return all(literal(layer) for layer in node.layers)
    return all(literal(child) for child in children(node))


def selected_slot(node):
    node = project(node)
    if isinstance(node, Slot):
        return node
    if isinstance(node, Merge):
        return selected_slot(node.args[0])
    return None


def replace_selected_slot(node, value):
    if isinstance(node, Merge) and project(node) is node:
        out = copy.copy(node)
        out.args = [replace_selected_slot(node.args[0], value), node.args[1]]
        out.__dict__.pop("_projection", None)
        return out
    return value


def _fingerprint(node, charge=None):
    """An exact typed comparison key, not a hash-only summary."""
    if charge is not None:
        charge(node)
    if isinstance(node, Scalar):
        return (node.type, node.value)
    if isinstance(node, Sequence):
        return ("list", tuple(_fingerprint(item, charge) for item in node.items))
    if isinstance(node, Mapping):
        return ("dict", frozenset((p.key, _fingerprint(p.value, charge)) for p in node.pairs))
    if isinstance(node, MultiMap):
        return ("multimap", tuple((p.key, _fingerprint(p.value, charge)) for p in node.entries))
    if isinstance(node, ResolvedTemplate):
        return ("template", tuple(("text", p[1]) if p[0] == "text" else
                ("hole", p[1], getattr(p[2], "lexeme", ""), _fingerprint(p[2], charge))
                for p in node.parts))
    raise Yakamashiwa("duplicate comparison reached an unfinished value")


def collection_merge(earlier, later, *, charge=None):
    multimap = isinstance(earlier, MultiMap)
    original = earlier.entries if multimap else earlier.items
    incoming = later.entries if multimap else later.items
    out, buckets = list(original), defaultdict(deque)

    def identity(item):
        return ((item.key, _fingerprint(item.value, charge)) if multimap
                else _fingerprint(item, charge))

    for index, item in enumerate(original):
        buckets[identity(item)].append(index)
    for item in incoming:
        matches = buckets[identity(item)]
        if matches:
            out[matches.popleft()] = item
        else:
            out.append(item)
    cls = MultiMap if multimap else Sequence
    result = cls(earlier.line, earlier.col, out)
    result.source = earlier.source
    result.fill_checks = earlier.fill_checks + later.fill_checks
    return result


class FillCheck:
    """§15.5's obligation when its key text is not available at fill time."""

    def __init__(self, path, layers, slot):
        self.path, self.layers, self.slot = path, layers, slot

    def _given(self, node):
        for step in self.path:
            node = project(node)
            if not isinstance(node, Mapping) or isinstance(step, int):
                return True
            key = step.key if isinstance(step, Pair) else step
            if isinstance(key, YString):
                return None
            if isinstance(node, MergedMapping):
                node.finish()
                pairs = node.visible_pairs()
            else:
                pairs = node.pairs
            pair = next((p for p in pairs if p.key == key), None)
            if pair is None:
                return None if node.pending_key() is not None else False
            node = pair.value
        return True

    def check(self):
        states = [self._given(layer) for layer in self.layers]
        if any(state is True for state in states):
            return True
        if any(state is None for state in states):
            return False
        path = ".".join(str(p.key if isinstance(p, Pair) else p) for p in self.path)
        raise AkanError(f"{self.slot.key}{self.slot.lexeme or '<>'}: this fill "
                        f"brings in the abstract slot {path}<>; its overrides "
                        "must give that key a value (SPEC §15.5)",
                        self.slot.line, self.slot.col, self.slot.source)
