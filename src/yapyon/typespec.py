"""SPEC §13.3's types: the type-string grammar, and the deep check.

A type is a string in Python's typing spelling over §3's type names —
`str`, `list[int]`, `dict[str, Any] | multimap[str, Any]`, `int | None`.
`parse_type` reads one into a small tree; `check` holds a parsed document
node against it, **deep**, stopping only at `Any`, and reports the first
mismatch at the offending node's own position. Built-ins declare their
signatures in this spelling (`serializers.SERIALIZERS`), and so do contracts
(§13.2), so there is one reader and one checker for both.

Types read nodes, never values: the check needs no evaluation, and a
mismatch inside a borrowed container still has the line and column where the
author wrote it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .parser import Mapping, MultiMap, Node, ResolvedTemplate, Scalar, Sequence

SCALARS = ("str", "bytes", "int", "float", "bool", "None", "Any")
CONTAINERS = ("list", "dict", "multimap")

#: A `Scalar.type` as §13.3 names it.
_NODE_TYPE = {"str": "str", "bytes": "bytes", "int": "int", "float": "float",
              "bool": "bool", "none": "None"}


class TypeSpecError(ValueError):
    """A type string that is not one (§13.3), position-free."""


@dataclass(frozen=True)
class Type:
    """One alternative: a scalar name, or a container and its item type.
    A union is a tuple of these (`Union`), in declared order."""
    name: str
    item: "Union | None" = None

    def __str__(self):
        if self.item is None:
            return self.name
        if self.name == "list":
            return f"list[{show(self.item)}]"
        return f"{self.name}[str, {show(self.item)}]"


Union = tuple                    # of Type, first declared first


def show(union: Union) -> str:
    """The PEP 8 spelling writers use: `dict[str, int]`, `int | None`."""
    return " | ".join(map(str, union))


def parse_type(text: str) -> Union:
    """Read a §13.3 type string; `TypeSpecError` names what is wrong."""
    reader = _Reader(text)
    union = reader.union()
    reader.space()
    if reader.i != len(text):
        raise TypeSpecError(f"unexpected {text[reader.i:]!r} in the type "
                            f"{text!r}")
    return union


class _Reader:
    def __init__(self, text: str):
        self.text, self.i = text, 0

    def space(self):
        while self.i < len(self.text) and self.text[self.i] in " \t":
            self.i += 1

    def eat(self, token: str) -> bool:
        self.space()
        if self.text.startswith(token, self.i):
            self.i += len(token)
            return True
        return False

    def word(self) -> str:
        self.space()
        start = self.i
        while self.i < len(self.text) and (self.text[self.i].isascii()
                                           and self.text[self.i].isalpha()):
            self.i += 1
        return self.text[start:self.i]

    def union(self) -> Union:
        alts = [self.alt()]
        while self.eat("|"):
            alts.append(self.alt())
        return tuple(alts)

    def alt(self) -> Type:
        name = self.word()
        if name in SCALARS:
            return Type(name)
        if name not in CONTAINERS:
            raise TypeSpecError(
                f"{name or self.text[self.i:self.i + 1]!r} is not a type; "
                f"the types are {', '.join(SCALARS)}, and "
                f"{', '.join(c + '[...]' for c in CONTAINERS)}"
                if name or self.i < len(self.text) else
                f"the type {self.text!r} ends where a type was expected")
        if not self.eat("["):
            raise TypeSpecError(f"a bare {name} is akan: write its contained "
                                f"type, as {name}[Any]" if name == "list" else
                                f"a bare {name} is akan: write its key and "
                                f"value types, as {name}[str, Any]")
        if name != "list":
            key = self.word()
            if key != "str":
                raise TypeSpecError(f"a {name}'s key type must be str (keys "
                                    f"are identifiers), not {key!r}")
            if not self.eat(","):
                raise TypeSpecError(f"expected ',' after {name}[str")
        item = self.union()
        if not self.eat("]"):
            raise TypeSpecError(f"expected ']' to close {name}[")
        return Type(name, item)


# --------------------------------------------------------------------------- #
# The deep check
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Mismatch:
    """Where the check failed and why: `node` is the offending value, so the
    akan lands at its line and column (§13.3)."""
    node: Node
    wanted: Union
    found: str


def kind_of(node: Node) -> str:
    """The §13.3 name of what a node holds."""
    if isinstance(node, Scalar):
        return _NODE_TYPE[node.type]
    if isinstance(node, Mapping):
        return "dict"
    if isinstance(node, MultiMap):
        return "multimap"
    if isinstance(node, Sequence):
        return "list"
    if isinstance(node, ResolvedTemplate):
        return "a template"
    return type(node).__name__


def check(node: Node, union: Union) -> Mismatch | None:
    """`None` if `node` matches `union` all the way down, else the first
    mismatch. A union matches if any alternative does, tried in declared
    order; `bool` is not `int`; an `int` is accepted where `float` is
    declared. No type names a template, `Any` included (§13.3)."""
    if isinstance(node, ResolvedTemplate):
        return Mismatch(node, union, "a template")
    deepest = None
    for alt in union:
        miss = _check_alt(node, alt)
        if miss is None:
            return None
        if miss.node is not node and deepest is None:
            deepest = miss               # a container matched but held a misfit
    return deepest or Mismatch(node, union, kind_of(node))


def _check_alt(node: Node, alt: Type) -> Mismatch | None:
    if alt.name == "Any":
        return None
    found = kind_of(node)
    if alt.item is None:
        if found == alt.name or (alt.name == "float" and found == "int"):
            return None
        return Mismatch(node, (alt,), found)
    if found != alt.name:
        return Mismatch(node, (alt,), found)
    if isinstance(node, Sequence):
        children = node.items
    elif isinstance(node, Mapping):
        children = [pair.value for pair in node.pairs]
    else:
        children = [entry.value for entry in node.entries]
    for child in children:
        miss = check(child, alt.item)
        if miss is not None:
            return miss
    return None
