"""yapyon loader — v0.1

Two load modes, one pipeline.

`loads(text)` / `load(fp)` take a document to plain Python objects, in the
shape the json module's API taught everyone to expect. The pipeline is
lexer → parser → resolver → build, and the only interesting step is the last
one, because by then every y/ry/yb literal is already a plain scalar (§5).

`loads_record(text)` / `load_record(fp)` take a **yapyon record**: the
restricted form in which every leaf element has a literal value. That is the
same pipeline minus the resolver — there is nothing to resolve, because
nothing is deferred — plus a refusal of the y-family. `is_record(text)`
answers the question without loading.

Two of the ten types are not Python builtins and arrive as their own classes:
a `+ ` block becomes an `OrderedMultimap` (§7.1) and a `yt` literal becomes a
`Template` (§6). Everything else is str, bytes, int, float, bool, None, list,
or dict. A record never yields a `Template`; an `OrderedMultimap` is fine in
one, being plain keyed data rather than deferred structure.

`warn=` receives every shiran as a formatted string — currently the
shadowed-resolution warning of §5.2. The expansion caps of §5.3 are
loader-overridable here, as the spec says they should be; a record takes
neither, since both are resolver limits.
"""

from __future__ import annotations

from .lexer import AkanError, Lexer, Yakamashiwa
from .multimap import OrderedMultimap
from .parser import Mapping, MultiMap, Parser, Scalar, Sequence, YString
from .resolver import MAX_DEPTH, MAX_SIZE, resolve
from .template import Template


def build(node, source: str | None = None):
    """A resolved AST to plain Python objects.

    `source` is carried only so a `Template` can name its origin when it
    akans at fill, long after the document is gone.
    """
    if isinstance(node, Scalar):
        return node.value
    if isinstance(node, Mapping):
        return {pair.key: build(pair.value, source) for pair in node.pairs}
    if isinstance(node, Sequence):
        return [build(item, source) for item in node.items]
    if isinstance(node, MultiMap):
        multimap = OrderedMultimap()
        for entry in node.entries:
            multimap.insert(entry.key, build(entry.value, source))
        return multimap
    if isinstance(node, YString):
        if node.prefix != "yt":
            raise Yakamashiwa(f"unresolved {node.prefix}-string reached the "
                              f"loader")
        return Template(node.parts, node.line, node.col, source)
    raise Yakamashiwa(f"unknown node type {type(node).__name__}")


def loads(text: str, *, warn=None, max_depth: int = MAX_DEPTH,
          max_size: int = MAX_SIZE, source: str | None = None):
    """Load a document from text.

    `source` names the text for diagnostics — pass it when the caller knows
    where the bytes came from, and every akan reports `name:line:col`.
    """
    lexer = Lexer(text, source=source)
    parser = Parser(lexer.tokenize(), lexer.warnings, source=source)
    tree = parser.parse()
    if warn is not None:
        for message in parser.warnings:
            warn(message)
    return build(resolve(tree, warn=warn, max_depth=max_depth,
                         max_size=max_size, source=source), source)


def load(fp, *, warn=None, max_depth: int = MAX_DEPTH,
         max_size: int = MAX_SIZE, source: str | None = None):
    """Load a document from an open file (text mode, UTF-8).

    `source` defaults to the file's own name when it has one, so reading a
    file gets located diagnostics without the caller asking.
    """
    return loads(fp.read(), warn=warn, max_depth=max_depth,
                 max_size=max_size, source=_name_of(fp, source))


# --------------------------------------------------------------------------- #
# The yapyon record — every leaf element has a literal value
# --------------------------------------------------------------------------- #
# `parser.py`'s scalar kinds are eight: five literals (STRING, BYTES, INT,
# FLOAT, KEYWORD) and exactly these three. So the y-family *is* the
# non-literal set, and "every leaf is a literal" is testable as "no token
# carries a y-family prefix" — the definition and the test coincide.
_DEFERRED_KINDS = frozenset({"YSTR", "YBSTR", "YTSTR"})


def _name_of(fp, source: str | None) -> str | None:
    """An explicit `source` wins; otherwise the file's own name, if it has
    one. StringIO has none, which is why this is not just `fp.name`."""
    return source if source is not None else getattr(fp, "name", None)


def _refuse_deferred(tokens, source: str | None = None) -> None:
    """Enforce the record rule as a filter over the token stream.

    In the loader rather than the lexer on purpose: a mode flag reaching the
    lexer would be the feedback channel the design forbids, and none is
    needed — the prefix alone decides, with no context to consult.
    """
    for tok in tokens:
        if tok.kind in _DEFERRED_KINDS:
            raise AkanError(
                f"a record's leaves must all be literals; a "
                f"{tok.prefix}-string defers its value (load with "
                f"yapyon.loads for the full form)", tok.line, tok.col,
                source)


def is_record(text: str, *, source: str | None = None) -> bool:
    """True if every leaf element of `text` has a literal value.

    Lexes and looks; no parse. So this answers the *record* question only —
    text that lexes but does not parse still gets an answer here, and the
    parse error surfaces when it is loaded. Text that does not lex raises,
    there being no document to answer about — hence `source`, which names it
    in that akan.
    """
    return not any(tok.kind in _DEFERRED_KINDS
                   for tok in Lexer(text, source=source).tokenize())


def loads_record(text: str, *, warn=None, source: str | None = None):
    """Load a yapyon record from text — the fixed, literal-only form.

    A separate function rather than `loads(..., record=True)`: it reads
    better at call sites, and it keeps the safe path from being one keyword
    argument away from the unsafe one.

    The record check runs *after* the parse, so that a document which is not
    yapyon at all reports that first. A record is a strict subset of yapyon;
    asking whether something belongs to the subset is only meaningful once it
    belongs to the set.
    """
    lexer = Lexer(text, source=source)
    tokens = lexer.tokenize()
    parser = Parser(tokens, lexer.warnings, source=source)
    tree = parser.parse()
    _refuse_deferred(tokens, source)
    if warn is not None:
        for message in parser.warnings:
            warn(message)
    return build(tree, source)


def load_record(fp, *, warn=None, source: str | None = None):
    """Load a record from an open file (text mode, UTF-8)."""
    return loads_record(fp.read(), warn=warn, source=_name_of(fp, source))
