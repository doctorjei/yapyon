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
`Template` (§6) — resolved like a y-string but handed over unjoined, so the
consumer can escape each value for wherever it is going. Everything else is
str, bytes, int, float, bool, None, list, or dict. A record never yields a
`Template`, since it needs the resolver; an `OrderedMultimap` is fine in one,
being plain keyed data.

`lookup(tree, ref, at=path)` is §5.2's search offered to a consumer: a
loaded tree, a position in it, and a reference resolved the way a hole
written there would be. It runs the resolver's own search rather than a
copy of the rule.

`warn=` receives every shiran as a formatted string — the avoidable-bracket
warning of §5.1, and §5.3's two warn-tier warnings.

§5.3 has **two tiers and they are different numbers**. `max_depth` /
`max_size` set this implementation's **refusal ceiling** (an akan above it),
and default to `4x` the spec's warn thresholds so that the warn tier is
reachable. The warn thresholds themselves — `resolver.MAX_DEPTH` /
`MAX_SIZE` — are fixed by the spec and are not arguments: a consumer chooses
what it will *refuse*, not what the format calls suspicious. A record takes
neither, since both are resolver limits.
"""

from __future__ import annotations

from .lexer import AkanError, Lexer, RefError, Yakamashiwa, fold_name
from .multimap import OrderedMultimap
from .parser import (Mapping, MultiMap, Pair, Parser, ResolvedTemplate,
                     Scalar, Sequence, YString)
from .resolver import (REFUSE_DEPTH, REFUSE_SIZE, Resolver, _Site, resolve,
                       splice_text)
from .template import Hole, Template


def build(node, source: str | None = None):
    """A resolved AST to plain Python objects.

    `source` is carried only so a `Template` can name its origin when
    `render()` akans, long after the document is gone.
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
    if isinstance(node, ResolvedTemplate):
        return Template(
            [part[1] if part[0] == "text" else _hole(part, source)
             for part in node.parts],
            node.line, node.col, source)
    if isinstance(node, YString):
        raise Yakamashiwa(f"unresolved {node.prefix}-string reached the "
                          f"loader")
    raise Yakamashiwa(f"unknown node type {type(node).__name__}")


def _hole(part, source: str | None) -> Hole:
    """One ("hole", ref, resolved node) into the consumer's view of it.

    `text` comes from `resolver.splice_text` — the one implementation of §5.5
    — so `Template.render()` cannot disagree with the `y` string this `yt` is
    the unjoined version of.
    """
    _, ref, node = part
    text, why = splice_text(node)
    return Hole(ref, build(node, source), getattr(node, "lexeme", ""),
                text, why)


def loads(text: str, *, warn=None, max_depth: int = REFUSE_DEPTH,
          max_size: int = REFUSE_SIZE, source: str | None = None):
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


def load(fp, *, warn=None, max_depth: int = REFUSE_DEPTH,
         max_size: int = REFUSE_SIZE, source: str | None = None):
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


#: The token kinds that mark a construct reaching **outside the document's own
#: bytes** — the axis `tier_of` measures.
#:
#: **Empty by fact, not by oversight.** Nothing in the shipped language
#: reaches outside the document: law 3 forbids ambient scope, includes and
#: environment at the format level, and the only callables are the three
#: declared serializers, whose results are known. So every well-formed
#: non-record document is level 2 today, and the set has nothing to hold.
#:
#: It is a set rather than a hardcoded `return 2` because the day a
#: tier-3 construct is built — file embedding, environment access, see
#: `workbook/designs/document-tiers.md` — its token kind is added here and
#: `tier_of` starts distinguishing the two with no other change. Growing
#: this set is a deliberate act: `tests/test_tiers.py` asserts it is empty,
#: so the change cannot arrive as a silent edit.
_TIER3_KINDS: frozenset = frozenset()


def tier_of(text: str, *, source: str | None = None) -> int:
    """The lowest loader capability `text` needs in order to mean itself.

    **1** — a record. Every leaf is a literal, so no resolver is needed at
    all (§12). **2** — self-contained. The document's own bytes decide its
    meaning, with the resolver in hand (law 3). **3** — meaning needs
    something outside the document; unreachable today, see `_TIER3_KINDS`.

    The axis is **closure, not power**: what you must have in hand to know
    what the document means. It is *lexically* decidable, which is what
    makes the level computable rather than merely declared — a declaration
    can be a contract, but detection is authoritative. That property is
    load-bearing: it is why a loader can check a claimed level instead of
    trusting one.

    Same discipline as `is_record`: this reads the token stream and does not
    parse, so text that lexes but does not parse still gets a level here,
    and the parse error surfaces when it is loaded. Text that does not lex
    raises, there being no document to answer about — hence `source`.
    """
    kinds = {tok.kind for tok in Lexer(text, source=source).tokenize()}
    if kinds & _TIER3_KINDS:
        return 3
    if kinds & _DEFERRED_KINDS:
        return 2
    return 1


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


# --------------------------------------------------------------------------- #
# §5.2's scope search, over a loaded tree
# --------------------------------------------------------------------------- #
class _PathAkan(AkanError):
    """An akan located by a path in a loaded tree, which has no lines.

    Still an `AkanError`, so a consumer's existing handler catches it; `line`
    and `col` are None because there is no source text to point into.
    """

    def __init__(self, msg: str, where: str):
        Exception.__init__(self, f"akan: at {where}: {msg}")
        self.msg, self.line, self.col, self.source = msg, None, None, None
        self.where = where


class _PathResolver(Resolver):
    """The resolver, reporting at a path instead of a line and column.

    Only the reporting changes. Every rule the search applies — nearest
    wins, the own-key skip, steps, indices, the multimap list view, the
    anchors, serializers — is the parent class's, which is the point.
    """

    def __init__(self, tree, where: str):
        super().__init__(tree)
        self._where = where

    def _akan(self, msg: str, at):
        raise _PathAkan(msg, self._where)


def lookup(tree, ref: str, *, at=()):
    """Resolve `ref` in a loaded tree, the way a hole written at `at` would.

    `tree` is what `loads` returns — or several such trees a consumer has
    assembled into one. `at` is a path from the root to the value the
    reference sits in: keys for mappings, integers for lists, e.g.
    `("harness", "protocol")`. That position is the whole of the scope rule:
    the search starts at the mapping holding the last key, nearest wins
    (§5.2), and a hole never finds its own key, so `lookup(t, "x",
    at=("blk", "x"))` reaches an outer `x`, exactly as `x: y"{x}"` would.

    `ref` is a hole's interior in full (GRAMMAR §G5): `mind.dialects[p]`,
    `__ROOT__.a`, `__PARENT__.b`, `__KEY__`, `xs[-1]`, a serializer. Returns
    the value it names, as `loads` would have built it — a multimap traversed
    by key gives its list view.

    **This is the resolver's search, not a second implementation of it.**
    The tree is wrapped back into the AST and the resolver's own lookup runs
    from a site built at `at`, so a document hole and this function cannot
    disagree about what a reference means.

    A multimap entry inside `at` is refused for now: its keys repeat, so a
    key cannot pick one entry, and positional entry access is reserved.
    """
    where = ".".join(str(step) for step in at) or "the root"
    try:
        root = _wrap(tree, where)
        chain = _chain_at(root, at, where)
        probe = YString(0, 0, "y", [("hole", ref)])
        found = _PathResolver(root, where)._lookup(
            ref, _Site(probe, chain, None))
    except RefError as exc:
        raise _PathAkan(f"{{{ref}}}: {exc}", where) from None
    return build(found)


def _wrap(value, where: str):
    """A loaded value back into the AST, so the resolver can walk it.

    The inverse of `build` for data. Positions are zero — a loaded tree has
    none — and errors report the path instead. A number has no source
    spelling any more, so a serializer writes it by its value.
    """
    if isinstance(value, dict):
        return Mapping(0, 0, [Pair(0, 0, key, _wrap(item, where))
                              for key, item in value.items()])
    if isinstance(value, OrderedMultimap):
        return MultiMap(0, 0, [Pair(0, 0, entry.key, _wrap(entry.value, where))
                               for entry in value])
    if isinstance(value, list):
        return Sequence(0, 0, [_wrap(item, where) for item in value])
    if isinstance(value, bool):                  # before int: bool is an int
        return Scalar(0, 0, "bool", value)
    if value is None:
        return Scalar(0, 0, "none", None)
    for kind, types in (("str", str), ("bytes", (bytes, bytearray)),
                        ("int", int), ("float", float)):
        if isinstance(value, types):
            return Scalar(0, 0, kind, value)
    raise _PathAkan(f"a {type(value).__name__} is not yapyon data, so the "
                    f"tree cannot be searched", where)


def _chain_at(root, at, where: str) -> list:
    """The scope chain a hole at `at` would have — the frames `_collect`
    records, innermost first. Lists add no frame, exactly as in a document."""
    chain, node = [], root
    for step in at:
        if isinstance(node, Mapping) and isinstance(step, str):
            key = fold_name(step)
            if key not in node.by_key:
                raise _PathAkan(f"there is no key {key!r} on the path", where)
            chain.insert(0, (node, key))
            node = node.by_key[key]
        elif (isinstance(node, Sequence) and isinstance(step, int)
              and not isinstance(step, bool)):
            if not -len(node.items) <= step < len(node.items):
                raise _PathAkan(f"index {step} is outside a list of "
                                f"{len(node.items)} on the path", where)
            node = node.items[step]
        elif isinstance(node, MultiMap):
            raise _PathAkan("a multimap's keys repeat, so a path cannot pick "
                            "one entry; positional entry access is reserved",
                            where)
        else:
            raise _PathAkan(f"cannot step {step!r} into a "
                            f"{type(node).__name__.lower()} on the path", where)
    return chain
