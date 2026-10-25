"""The one merge operation, including keys whose text is still pending (§15)."""

import copy

from .lexer import AkanError
from .parser import Mapping, Pair, Slot, YString


class MergedMapping(Mapping):
    """Ordered input layers, not a merge by expression spelling.

    Known entries provide a view for walking and for key dependencies. A
    view is cached by its contributing pairs, so resolving a value is never
    undone when more key text becomes available. Pending contributions keep
    their original mapping for duplicate checks and their layer precedence.
    """

    def __init__(self, earlier, later):
        self.layers = [earlier, later]
        self._views = {}
        super().__init__(earlier.line, earlier.col,
                         [p for layer in self.key_layers() for p in layer.pairs])
        self.source = earlier.source
        self.fill_checks = earlier.fill_checks + later.fill_checks

    def key_layers(self):
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
                if isinstance(pair.key, str):
                    groups.setdefault(pair.key, []).append(pair)
        out = []
        for key, pairs in groups.items():
            signature = tuple((p, p.value) for p in pairs)
            cached = self._views.get(key)
            if (cached is not None and len(cached[0]) == len(signature)
                    and all(a is c and b is d for (a, b), (c, d)
                            in zip(cached[0], signature))):
                pair = cached[1]
            else:
                pair = pairs[0] if len(pairs) == 1 else copy.copy(pairs[0])
                for later in pairs[1:]:
                    pair.value = merge_nodes(pair.value, later.value)
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
        """A consumer edits a location before resolution, never a source AST."""
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
        self._views.clear()
        self.pairs = [p for layer in self.key_layers() for p in layer.pairs]
        self.reindex()

    def key_pair(self, key, *, named=False):
        if not self.layers:
            return super().key_pair(key, named=named)
        view = Mapping(self.line, self.col, self.visible_pairs())
        return view.key_pair(key, named=named)

    def pending_key(self):
        if not self.layers:
            return super().pending_key()
        for layer in self.key_layers():
            if isinstance(layer, YString):
                return layer
            pending = layer.pending_key()
            if pending is not None:
                return pending
        return None

    def waiting_for_name(self, key):
        """An unknown cross-layer key that could still change this name.

        A pending key in the same authored mapping as a known key cannot
        override it: equality there is duplicate-key akan, not precedence.
        A later scalar also makes earlier value contributions irrelevant.
        """
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
            if i < first or i > last or isinstance(known[-1][1].value, Mapping):
                return pending
        return None

    def finish(self):
        if self.layers and self.pending_key() is None:
            for layer in self.layers:
                if isinstance(layer, MergedMapping):
                    layer.finish()
            self.pairs = self.visible_pairs()
            self.layers = []
            self._views.clear()
            self.reindex()
            return True
        return False


class FillCheck:
    """§15.5's obligation when its key text is not available at fill time."""

    def __init__(self, path, layers, slot):
        self.path, self.layers, self.slot = path, layers, slot

    def _given(self, node):
        for step in self.path:
            if not isinstance(node, Mapping) or isinstance(step, int):
                return True                         # an ancestor is replaced
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


def merge_nodes(earlier, later):
    """§15.2: mappings recurse; otherwise later replaces, without resolving.

    Containers are constructed rather than mutating either input. Child
    nodes may be shared inside this private construction; public Tree edits
    take their own copies before entering it.
    """
    if isinstance(later, Slot):
        if isinstance(earlier, Slot) and earlier.abstract:
            out = Slot(later.line, later.col, later.label,
                       earlier.layers + later.layers, later.lexeme, later.key)
            out.source = later.source
            return out
        return later
    if isinstance(earlier, Slot):
        if not earlier.abstract and isinstance(later, Mapping):
            out = Slot(earlier.line, earlier.col, earlier.label,
                       earlier.layers + [later], earlier.lexeme, earlier.key)
            out.source = earlier.source
            return out
        return later
    if isinstance(earlier, Mapping) and isinstance(later, Mapping):
        if (earlier.pending_key() is not None or later.pending_key() is not None
                or isinstance(earlier, MergedMapping) and earlier.layers
                or isinstance(later, MergedMapping) and later.layers):
            return MergedMapping(earlier, later)
        pairs = []
        for original in earlier.pairs:
            pair = copy.copy(original)
            if pair.key in later.by_key:
                pair.value = merge_nodes(pair.value, later.by_key[pair.key])
            pairs.append(pair)
        pairs += [p for p in later.pairs if p.key not in earlier.by_key]
        out = Mapping(earlier.line, earlier.col, pairs)
        out.source = earlier.source
        out.fill_checks = earlier.fill_checks + later.fill_checks
        return out
    return later
