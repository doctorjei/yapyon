"""yapyon trees: a document read but not resolved — SPEC §15.

`parse(text)` and `parse_file(path)` return a `Tree`: the document as
written, holes unresolved and slots unfilled, every value keeping its
lexeme and its place. A consumer walks it with **handles**, combines trees
with `merge`, fills slots with `fill`, drops values with `remove`, and
then calls `resolve()` once.

A handle is a **location**, not an object: it holds its tree and the path
to its value, and reads that path each time it is used. So it is live —
it sees every later edit — and a handle kept after replacing a value
still names the place, which is how a consumer replaces it again. One whose
path no longer exists raises `KeyError` or `IndexError`, as a dict or list
would.

The parser's nodes stay private: nothing here hands one out. That is the
point of the module (operator, 2026-10-23: making the AST the interface
"makes me shudder") — the parser may change its node classes freely, and
consumers never notice.

Every edit takes its own copy of what it is given (§15.3's linearity): one
tree may fill or be merged into many places, and each keeps its own.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field

from ._digits import REFUSE_DIGITS
from ._keys import key_error, name_key
from .assembly import FillCheck, MergedMapping, merge_nodes
from .environment import STANDARD_ENV, environment
from .lexer import AkanError, Lexer, Yakamashiwa, fold_name
from .parser import (Copy, Mapping, MultiMap, Node, Pair, Parser, Scalar,
                     Sequence, Slot, YString, children)
from .resolver import REFUSE_DEPTH, REFUSE_SIZE, resolve

__all__ = ["Tree", "Handle", "Key", "parse", "parse_file", "merge"]


@dataclass(frozen=True)
class Key:
    """An unresolved key's location, returned by Tree.keys/items.

    Use it to index the same mapping without evaluating the key. Its lexeme
    is display information, not key equality. It never exposes an AST node.
    """

    identity: int
    lexeme: str = field(compare=False)

    def __repr__(self):
        return f"<key {self.lexeme}>"


def _keys_pairs(node):
    return node.walk_pairs() if isinstance(node, MergedMapping) else node.pairs


def _key(pair):
    return Key(pair.identity, pair.lexeme) if isinstance(pair.key, YString) else pair.key


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def parse(text: str, *, source: str | None = None,
          max_digits: int = REFUSE_DIGITS) -> "Tree":
    """Read a document without resolving it (SPEC §15.7).

    The text must be well-formed (GRAMMAR); nothing is looked up, filled,
    or checked against the environment until `Tree.resolve`. `source`
    names the document in every diagnostic about a value from it, wherever
    that value is merged or filled to."""
    lexer = Lexer(text, source=source, max_digits=max_digits)
    parser = Parser(lexer.tokenize(), lexer.warnings, source=source)
    return Tree(parser.parse(), source=source, warnings=parser.warnings)


def parse_file(path, *, source: str | None = None,
               max_digits: int = REFUSE_DIGITS) -> "Tree":
    """`parse` on a file's text (UTF-8); the file's path is the source
    unless `source` says otherwise."""
    with open(path, encoding="utf-8") as fp:
        text = fp.read()
    return parse(text, source=str(path) if source is None else source,
                 max_digits=max_digits)


def merge(*layers) -> "Tree":
    """A new tree: the first layer, with each later one merged over it
    (SPEC §15.2). Layers are trees or handles; none is changed."""
    if not layers:
        raise TypeError("merge needs at least one tree")
    out = Tree(_own(layers[0]))
    out.merge(*layers[1:])
    return out


# --------------------------------------------------------------------------- #
# The tree
# --------------------------------------------------------------------------- #
class Tree:
    """A document, read but not resolved. Index it like its top value:
    `tree["agent"]["persona"]` is a handle."""

    def __init__(self, root: Node, *, source: str | None = None,
                 warnings: list | None = None):
        self._root = root
        self.source = source
        self.warnings = list(warnings or [])   # shirans found while reading

    def __repr__(self):
        name = f" {self.source!r}" if self.source else ""
        return f"<yapyon.Tree{name}>"

    # -- walking (delegated to the top value) --------------------------------
    @property
    def root(self) -> "Handle":
        return Handle(self, ())

    def __getitem__(self, key) -> "Handle":
        return self.root[key]

    def __contains__(self, key) -> bool:
        return key in self.root

    def __iter__(self):
        return iter(self.root)

    def __len__(self) -> int:
        return len(self.root)

    def keys(self):
        return self.root.keys()

    def items(self):
        return self.root.items()

    def at(self, *path) -> "Handle":
        """The handle at `path` — keys and list indices — from the top."""
        handle = self.root
        for step in path:
            handle = handle[step]
        return handle

    def slots(self) -> list["Handle"]:
        """Every slot still to fill, in document order (SPEC §15.6). A slot
        inside another slot's overrides is not listed: it belongs to that
        slot's fill."""
        found = []

        def walk(node, path):
            if isinstance(node, Slot):
                found.append(Handle(self, path))
                return
            for step, child in _steps(node):
                walk(child, path + (step,))
        walk(self._root, ())
        return found

    # -- editing -------------------------------------------------------------
    def merge(self, *layers, at=()) -> None:
        """Merge each layer over the value at `at` (the top by default), in
        order — later wins (SPEC §15.2). Where `at`'s last key is absent
        from its mapping, the first layer is placed there. Layers are trees
        or handles; they are copied, never changed."""
        path = tuple(at)
        for layer in layers:
            node = _own(layer)
            if path and not self._has(path):
                parent = self._node(path[:-1])
                if not isinstance(parent, Mapping) or isinstance(path[-1], int):
                    self._node(path)          # raises the natural KeyError
                self._place(path, node)
                continue
            self._replace(path, merge_nodes(self._node(path), node))

    def to_source(self) -> str:
        """Write unfinished yapyon without resolving or changing this tree.

        Expressions and unfilled slots stay deferred. Potentially matching
        computed keys across merged dictionaries, a completed fill's
        undecided abstract-slot obligations, and pending overrides that
        would lose replacement boundaries are akan at save time (§15.8).
        Layout/comments and original diagnostic positions do not survive
        reloading the text; literal and expression spellings do.
        """
        from ._source import to_source
        return to_source(self._root, source=self.source)

    def resolve(self, *, env_allow=STANDARD_ENV, env=os.environ, warn=None,
                max_depth: int = REFUSE_DEPTH, max_size: int = REFUSE_SIZE,
                max_digits: int = REFUSE_DIGITS, contract=None,
                provide=None):
        """Resolve once, to plain Python — as `yapyon.loads` does, with the
        same arguments. Holes bind where their values now sit (SPEC §15.6);
        a slot still unfilled is akan. The tree itself is not changed, so
        it may be resolved again, or edited and resolved again."""
        from .loader import _functions, build
        if warn is not None:
            for message in self.warnings:
                warn(message)
        root = copy.deepcopy(self._root)
        done = resolve(root, warn=warn, max_depth=max_depth,
                       max_size=max_size, max_digits=max_digits,
                       functions=_functions(contract, provide),
                       environment=environment(env, env_allow),
                       source=self.source)
        return build(done, self.source)

    # -- paths ---------------------------------------------------------------
    def _node(self, path: tuple) -> Node:
        node = self._root
        for i, step in enumerate(path):
            node = _child(node, step, path[:i])
        return node

    def _has(self, path: tuple) -> bool:
        try:
            self._node(path)
        except (KeyError, IndexError):
            return False
        return True

    def _replace(self, path: tuple, new: Node) -> None:
        if not path:
            self._root = new
            return
        parent = self._node(path[:-1])
        step = path[-1]
        if isinstance(parent, Mapping):
            pair = _pair(parent, step, path[:-1])
            if isinstance(parent, MergedMapping) and parent.layers:
                parent.edit_pair(pair, new)
            else:
                pair.value = new
                parent.reindex()
        elif isinstance(parent, Sequence):
            parent.items[_index(parent, step, path[:-1])] = new
        else:
            raise Yakamashiwa("a path step through a value with no children")

    def _place(self, path: tuple, new: Node) -> None:
        parent = self._node(path[:-1])
        text = path[-1]
        why = key_error(text)
        if why:
            raise ValueError(why)
        named = name_key(text)
        key = fold_name(text) if named else text
        pair = Pair(new.line, new.col, key, new, text if named else "", named=named)
        pair.source = new.source
        if isinstance(parent, MergedMapping) and parent.layers:
            parent.layers.append(Mapping(new.line, new.col, [pair]))
        parent.pairs.append(pair)
        parent.reindex()

    def _remove(self, path: tuple) -> None:
        if not path:
            raise ValueError("the top of a tree cannot be removed")
        parent = self._node(path[:-1])
        step = path[-1]
        if isinstance(parent, Mapping):
            pair = _pair(parent, step, path[:-1])
            if isinstance(parent, MergedMapping) and parent.layers:
                parent.edit_pair(pair, remove=True)
            else:
                parent.pairs.remove(pair)
                parent.reindex()
        elif isinstance(parent, Sequence):
            del parent.items[_index(parent, step, path[:-1])]
        else:
            raise Yakamashiwa("a path step through a value with no children")


# --------------------------------------------------------------------------- #
# Handles
# --------------------------------------------------------------------------- #
_KIND = {Mapping: "mapping", Sequence: "sequence", MultiMap: "multimap",
         Slot: "slot", Scalar: "scalar", Copy: "copy", YString: "ystring"}


class Handle:
    """A place in a tree: its path from the top, read each time it is used.

    `kind` is one of mapping, sequence, multimap, slot, scalar, ystring,
    or copy. Scalars have a `type` (str, bytes, int, float, bool, none) and
    a `value`; y-strings a `type` (str, bytes, template). Every value but
    a container has a `lexeme`, its spelling as written; a slot has a
    `label` and its `overrides`. `where` is (source, line, column)."""

    __slots__ = ("tree", "path")

    def __init__(self, tree: Tree, path: tuple):
        self.tree, self.path = tree, path

    def __repr__(self):
        return f"<yapyon.Handle {self.kind} at {self._show()}>"

    def _show(self) -> str:
        return _show(self.path) or "the top"

    @property
    def _node(self) -> Node:
        return self.tree._node(self.path)

    # -- reading -------------------------------------------------------------
    @property
    def kind(self) -> str:
        node = self._node
        for cls in type(node).__mro__:
            if cls in _KIND:
                return _KIND[cls]
        raise Yakamashiwa(f"a tree holds a {type(node).__name__}")

    @property
    def key(self):
        """The last step of the path: a key, an index, or None at the top."""
        return self.path[-1] if self.path else None

    @property
    def type(self) -> str:
        node = self._node
        if isinstance(node, (Scalar, YString)):
            return node.type
        raise TypeError(f"a {self.kind} has no scalar type")

    @property
    def value(self):
        node = self._node
        if isinstance(node, Scalar):
            return node.value
        raise TypeError(f"{self._show()} is a {self.kind}, which has no "
                        f"value until the tree is resolved"
                        if isinstance(node, (YString, Slot)) else
                        f"{self._show()} is a {self.kind}; walk it, or "
                        f"resolve the tree")

    @property
    def lexeme(self) -> str | None:
        node = self._node
        if isinstance(node, (Scalar, YString, Slot)):
            return node.lexeme
        return None

    @property
    def where(self) -> tuple:
        node = self._node
        return (node.source, node.line, node.col)

    @property
    def label(self) -> tuple:
        node = self._slot("label")
        return node.label

    @property
    def abstract(self) -> bool:
        return self._slot("abstract").abstract

    @property
    def overrides(self) -> "Tree":
        """A slot's overrides, merged as they will apply — a copy, so
        editing it changes nothing here."""
        node = self._slot("overrides")
        merged = Mapping(node.line, node.col, [])
        for layer in node.layers:
            merged = merge_nodes(merged, copy.deepcopy(layer))
        return Tree(merged, source=node.source)

    def __getitem__(self, step) -> "Handle":
        node = self._node
        _child(node, step, self.path)            # raises if absent
        return Handle(self.tree, self.path + (step,))

    def __contains__(self, key) -> bool:
        node = self._node
        if not isinstance(node, Mapping):
            return False
        try:
            _pair(node, key, self.path)
        except KeyError:
            return False
        return True

    def __len__(self) -> int:
        node = self._node
        if isinstance(node, Mapping):
            return len(_keys_pairs(node))
        if isinstance(node, Sequence):
            return len(node.items)
        if isinstance(node, MultiMap):
            return len(node.entries)
        raise TypeError(f"a {self.kind} has no length")

    def __iter__(self):
        """A mapping's keys, or a sequence's items as handles."""
        node = self._node
        if isinstance(node, Mapping):
            return iter([_key(pair) for pair in _keys_pairs(node)])
        if isinstance(node, Sequence):
            return iter([self[i] for i in range(len(node.items))])
        raise TypeError(f"a {self.kind} cannot be iterated; "
                        f"{'resolve the tree' if self.kind == 'multimap' else 'it holds no values'}")

    def keys(self) -> list:
        node = self._node
        if not isinstance(node, Mapping):
            raise TypeError(f"a {self.kind} has no keys")
        return [_key(pair) for pair in _keys_pairs(node)]

    def items(self) -> list:
        return [(key, self[key]) for key in self.keys()]

    def key_lexeme(self) -> str | None:
        """The key this value sits under, as written."""
        if not self.path or isinstance(self.path[-1], int):
            return None
        parent = self.tree._node(self.path[:-1])
        return _pair(parent, self.path[-1], self.path[:-1]).lexeme

    # -- editing -------------------------------------------------------------
    def merge(self, *layers) -> None:
        """Merge each layer over this value, in order (SPEC §15.2)."""
        self.tree.merge(*layers, at=self.path)

    def replace(self, value) -> None:
        """Put a copy of `value` (a tree or handle) here, whole."""
        self.tree._replace(self.path, _own(value))

    def remove(self) -> None:
        """Take this value, and its key, out of the tree."""
        self.tree._remove(self.path)

    def fill(self, filler) -> None:
        """Fill this slot (SPEC §15.3).

        A **tree** is what the label's first name stands for: the rest of
        the label is followed inside it (§15.4) — `agent<base.agent>`
        filled with base's tree takes its `agent`. A **handle** is used as
        it is. Either way a copy is taken; the slot's overrides are merged
        over it; and if what the label reaches is itself a slot, that slot
        takes this one's place, with this one's overrides over its own."""
        slot = self._slot("fill")
        node = self._reach(slot, filler)
        if isinstance(node, Slot):
            moved = Slot(node.line, node.col, node.label,
                         node.layers + slot.layers, node.lexeme, node.key)
            moved.source = node.source
            self.tree._replace(self.path, moved)
            return
        layers = [layer for layer in slot.layers if layer.pairs]
        layers = copy.deepcopy(layers)
        checks = self._oblige(node, layers, slot)
        for layer in layers:
            node = merge_nodes(node, layer)
        if checks:
            node.fill_checks += tuple(checks)
        self.tree._replace(self.path, node)

    # -- filling, in detail --------------------------------------------------
    def _slot(self, what: str) -> Slot:
        node = self._node
        if not isinstance(node, Slot):
            raise TypeError(f"{self._show()} is a {self.kind}, not a slot; "
                            f"only a slot has a {what}"
                            if what != "fill" else
                            f"{self._show()} is a {self.kind}, not a slot; "
                            f"use replace or merge")
        return node

    def _reach(self, slot: Slot, filler) -> Node:
        """The copy a fill takes: the filler, followed along the label's
        path if it is a whole tree (SPEC §15.4)."""
        if isinstance(filler, Handle):
            if filler.tree is self.tree and \
                    self.path[:len(filler.path)] == filler.path:
                raise AkanError(f"{_label(slot)}: a slot cannot be filled "
                                f"with a value that contains it (SPEC §15.3)",
                                slot.line, slot.col, slot.source)
            return copy.deepcopy(filler._node)
        if not isinstance(filler, Tree):
            raise TypeError("fill takes a yapyon Tree or Handle")
        if filler is self.tree:
            raise AkanError(f"{_label(slot)}: a slot cannot be filled with "
                            f"the tree that holds it (SPEC §15.3)",
                            slot.line, slot.col, slot.source)
        node = filler._root
        steps = slot.label[1:]
        for i, step in enumerate(steps):
            if isinstance(node, Slot):
                raise AkanError(
                    f"{_label(slot)}: {'.'.join(slot.label[:i + 1])} is a "
                    f"slot not yet filled, and the label goes through it; "
                    f"fill that one first (SPEC §15.4)",
                    slot.line, slot.col, slot.source)
            pair = node.key_pair(step, named=True) if isinstance(node, Mapping) else None
            if pair is None:
                raise AkanError(
                    f"{_label(slot)}: what {slot.label[0]!r} stands for has "
                    f"no {'.'.join(slot.label[1:i + 2])!r} (SPEC §15.4)",
                    slot.line, slot.col, slot.source)
            node = pair.value
        return copy.deepcopy(node)

    def _oblige(self, filler: Node, layers: list, slot: Slot) -> list:
        """SPEC §15.5: defer only the comparison of keys not yet known."""
        checks = []
        for path, abstract in _abstracts(filler):
            node, steps = filler, []
            for step in path:
                if isinstance(node, Mapping):
                    pair = _pair(node, step, ())
                    steps.append(pair)
                    node = pair.value
                else:
                    steps.append(step)
                    node = _child(node, step, ())
            check = FillCheck(steps, layers, slot)
            try:
                done = check.check()
            except AkanError:
                where = ".".join(str(step) for step in path)
                raise AkanError(
                    f"{_label(slot)}: what fills this slot has the abstract "
                    f"slot {where}<> (at {_at(abstract)}), and these "
                    f"overrides give it no value — name what fills it "
                    f"({path[-1]}<label>: {{}}), pass it on ({path[-1]}<>: "
                    f"{{}}), or replace it (SPEC §15.5)",
                    slot.line, slot.col, slot.source) from None
            if not done:
                checks.append(check)
        return checks


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _own(value) -> Node:
    if isinstance(value, Tree):
        return copy.deepcopy(value._root)
    if isinstance(value, Handle):
        return copy.deepcopy(value._node)
    raise TypeError("expected a yapyon Tree or Handle")


def _steps(node: Node):
    """(step, child) for a mapping's pairs and a sequence's items."""
    if isinstance(node, Mapping):
        return [(_key(pair), pair.value) for pair in _keys_pairs(node)]
    if isinstance(node, Sequence):
        return list(enumerate(node.items))
    return []


def _child(node: Node, step, where: tuple) -> Node:
    if isinstance(node, Mapping) and isinstance(step, (str, Key)):
        return _pair(node, step, where).value
    if isinstance(node, Sequence) and isinstance(step, int) \
            and not isinstance(step, bool):
        return node.items[_index(node, step, where)]
    kind = next((_KIND[c] for c in type(node).__mro__ if c in _KIND), "value")
    raise KeyError(f"{_show(where) or 'the top'} is a {kind}; "
                   f"{step!r} names nothing in it")


def _pair(mapping: Mapping, key: str, where: tuple) -> Pair:
    if isinstance(key, Key):
        pair = next((p for p in _keys_pairs(mapping) if p.identity == key.identity), None)
    elif isinstance(key, str):
        pair = mapping.key_pair(key)
    else:
        pair = None
    if pair is not None:
        return pair
    raise KeyError(f"{_show(where + (key,))} is not in the tree")


def _index(seq: Sequence, index: int, where: tuple) -> int:
    if not -len(seq.items) <= index < len(seq.items):
        raise IndexError(f"{_show(where + (index,))} is past the end "
                         f"({len(seq.items)} items)")
    return index % len(seq.items)


def _show(path: tuple) -> str:
    out = ""
    for step in path:
        out += f"[{step}]" if isinstance(step, int) else (
            f".{step}" if out else str(step))
    return out


def _label(slot: Slot) -> str:
    return f"{slot.key}{slot.lexeme or '<>'}"


def _at(node: Node) -> str:
    where = f"line {node.line}, col {node.col}"
    return f"{node.source}:{node.line}:{node.col}" if node.source else where


def _abstracts(node: Node, path: tuple = ()):
    """(path, slot) for each abstract slot in a filler, outside any other
    slot's overrides — the ones a fill brings in (SPEC §15.5)."""
    if isinstance(node, Slot):
        if node.abstract:
            yield path, node
        return
    for step, child in _steps(node):
        yield from _abstracts(child, path + (step,))
