"""yapyon loader — v0.1

`loads(text)` / `load(fp)` take a document to plain Python objects, in the
shape the json module's API taught everyone to expect. The pipeline is
lexer → parser → resolver → build, and the only interesting step is the last
one, because by then every y/ry/yb literal is already a plain scalar (§5).

Two of the ten types are not Python builtins and arrive as their own classes:
a `+ ` block becomes an `OrderedMultimap` (§7.1) and a `yt` literal becomes a
`Template` (§6). Everything else is str, bytes, int, float, bool, None, list,
or dict.

`warn=` receives every shiran as a formatted string — currently the
shadowed-resolution warning of §5.2. The expansion caps of §5.3 are
loader-overridable here, as the spec says they should be.
"""

from __future__ import annotations

from .lexer import Lexer, Yakamashiwa
from .multimap import OrderedMultimap
from .parser import Mapping, MultiMap, Parser, Scalar, Sequence, YString
from .resolver import MAX_DEPTH, MAX_SIZE, resolve
from .template import Template


def build(node):
    """A resolved AST to plain Python objects."""
    if isinstance(node, Scalar):
        return node.value
    if isinstance(node, Mapping):
        return {pair.key: build(pair.value) for pair in node.pairs}
    if isinstance(node, Sequence):
        return [build(item) for item in node.items]
    if isinstance(node, MultiMap):
        multimap = OrderedMultimap()
        for entry in node.entries:
            multimap.insert(entry.key, build(entry.value))
        return multimap
    if isinstance(node, YString):
        if node.prefix != "yt":
            raise Yakamashiwa(f"unresolved {node.prefix}-string reached the "
                              f"loader")
        return Template(node.parts, node.line, node.col)
    raise Yakamashiwa(f"unknown node type {type(node).__name__}")


def loads(text: str, *, warn=None, max_depth: int = MAX_DEPTH,
          max_size: int = MAX_SIZE):
    """Load a document from text."""
    lexer = Lexer(text)
    parser = Parser(lexer.tokenize(), lexer.warnings)
    tree = parser.parse()
    if warn is not None:
        for message in parser.warnings:
            warn(message)
    return build(resolve(tree, warn=warn, max_depth=max_depth,
                         max_size=max_size))


def load(fp, *, warn=None, max_depth: int = MAX_DEPTH,
         max_size: int = MAX_SIZE):
    """Load a document from an open file (text mode, UTF-8)."""
    return loads(fp.read(), warn=warn, max_depth=max_depth, max_size=max_size)
