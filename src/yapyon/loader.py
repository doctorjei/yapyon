"""yapyon loader

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

from ._digits import REFUSE_DIGITS
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
          max_size: int = REFUSE_SIZE, max_digits: int = REFUSE_DIGITS,
          source: str | None = None):
    """Load a document from text.

    `source` names the text for diagnostics — pass it when the caller knows
    where the bytes came from, and every akan reports `name:line:col`.
    `max_depth`, `max_size`, and `max_digits` are this implementation's
    refusal ceilings (SPEC §5.3, §3.1); past the spec's warn thresholds a
    document draws shiran, past these it is akan.
    """
    lexer = Lexer(text, source=source, max_digits=max_digits)
    parser = Parser(lexer.tokenize(), lexer.warnings, source=source)
    tree = parser.parse()
    if warn is not None:
        for message in parser.warnings:
            warn(message)
    return build(resolve(tree, warn=warn, max_depth=max_depth,
                         max_size=max_size, source=source), source)


def load(fp, *, warn=None, max_depth: int = REFUSE_DEPTH,
         max_size: int = REFUSE_SIZE, max_digits: int = REFUSE_DIGITS,
         source: str | None = None):
    """Load a document from an open file (text mode, UTF-8).

    `source` defaults to the file's own name when it has one, so reading a
    file gets located diagnostics without the caller asking.
    """
    return loads(fp.read(), warn=warn, max_depth=max_depth,
                 max_size=max_size, max_digits=max_digits,
                 source=_name_of(fp, source))


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


def loads_record(text: str, *, warn=None, max_digits: int = REFUSE_DIGITS,
                 source: str | None = None):
    """Load a yapyon record from text — the fixed, literal-only form.

    A separate function rather than `loads(..., record=True)`: it reads
    better at call sites, and it keeps the safe path from being one keyword
    argument away from the unsafe one.

    The record check runs *after* the parse, so that a document which is not
    yapyon at all reports that first. A record is a strict subset of yapyon;
    asking whether something belongs to the subset is only meaningful once it
    belongs to the set.
    """
    lexer = Lexer(text, source=source, max_digits=max_digits)
    tokens = lexer.tokenize()
    parser = Parser(tokens, lexer.warnings, source=source)
    tree = parser.parse()
    _refuse_deferred(tokens, source)
    if warn is not None:
        for message in parser.warnings:
            warn(message)
    return build(tree, source)


def load_record(fp, *, warn=None, max_digits: int = REFUSE_DIGITS,
                source: str | None = None):
    """Load a record from an open file (text mode, UTF-8)."""
    return loads_record(fp.read(), warn=warn, max_digits=max_digits,
                        source=_name_of(fp, source))


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

    def _key_of(self, parsed, ref, site):
        # Standing *at* a node is not standing in one of its pairs, so the
        # innermost frame has no key of its own for `__KEY__` to report.
        # `__PARENT__.__KEY__` — the node's own key — still works.
        if (parsed.parents < len(site.chain)
                and site.chain[parsed.parents][1] is None):
            self._akan(f"{{{ref}}}: you are at a node, not at one of its "
                       f"keys, so there is no key here to name; "
                       f"{{__PARENT__.__KEY__}} is this node's own key",
                       site.node)
        return super()._key_of(parsed, ref, site)


def lookup(tree, current, ref: str):
    """Resolve `ref` the way a hole written inside `current` would.

    `tree` is what `loads` returns — or several such trees a consumer has
    assembled into one — and `current` is a mapping, list or multimap the
    consumer is holding from inside it: `lookup(tree, tree["harness"],
    "protocol")`. The search starts at `current`, its own keys first, then
    outward through its ancestors, nearest winning (§5.2). A plain dict
    does not know its parents, which is why the tree comes too.

    `ref` is a hole's interior in full (GRAMMAR §G5): `mind.dialects[p]`,
    `__ROOT__.a`, `__PARENT__.b`, `xs[-1]`, a serializer. `__PARENT__` is
    `current` itself, as it is for a hole sitting in it, so
    `__PARENT__.__KEY__` is `current`'s own key. A bare `__KEY__` is
    refused: standing at a node is not standing in one of its pairs.
    Returns the value named, as `loads` would have built it.

    **This is the resolver's search, not a second implementation of it.**
    The tree is wrapped back into the AST and the resolver's own lookup runs
    from a site built at `current`, so a document hole and this function
    cannot disagree about what a reference means.

    `current` is found by identity. It must be in `tree` exactly once: a
    node placed in two spots has two answers to "where am I".
    """
    if not isinstance(current, (dict, list, OrderedMultimap)):
        raise _PathAkan("current must be a mapping, list or multimap taken "
                        f"from the tree, not a {type(current).__name__}",
                        "the root")
    hits: list = []
    root = _wrap(tree, current, [], [], hits)
    if not hits:
        raise _PathAkan("current is not a node of this tree", "the root")
    if len(hits) > 1:
        raise _PathAkan("current appears in the tree more than once, so "
                        "where it is has no single answer",
                        " and ".join(_where(path) for _, _, path in hits))
    node, chain, path = hits[0]
    if isinstance(node, Mapping):
        chain = [(node, None)] + chain           # a hole inside it: no own key
    where = _where(path)
    probe = YString(0, 0, "y", [("hole", ref)])
    try:
        found = _PathResolver(root, where)._lookup(
            ref, _Site(probe, chain, None))
    except RefError as exc:
        raise _PathAkan(f"{{{ref}}}: {exc}", where) from None
    return build(found)


def _where(path) -> str:
    return ".".join(str(step) for step in path) or "the root"


def _wrap(value, current, chain: list, path: list, hits: list):
    """A loaded value back into the AST, so the resolver can walk it — and,
    on the way, every place `current` sits, with the scope chain a hole
    there would have (the frames `resolver._collect` records).

    The inverse of `build` for data. Positions are zero — a loaded tree has
    none — and errors report the path instead. A number has no source
    spelling any more, so a serializer writes it by its value.
    """
    if isinstance(value, dict):
        node = Mapping(0, 0, [])
        for key, item in value.items():
            child = _wrap(item, current, [(node, key)] + chain, path + [key],
                          hits)
            node.pairs.append(Pair(0, 0, key, child))
            node.by_key[key] = child
    elif isinstance(value, OrderedMultimap):
        # A multimap's entry keys take no part in the search (§5.2), so its
        # entries add no frame — exactly as in a document.
        node = MultiMap(0, 0, [])
        for i, entry in enumerate(value):
            node.entries.append(Pair(0, 0, entry.key, _wrap(
                entry.value, current, chain, path + [f"+{i}"], hits)))
    elif isinstance(value, list):
        node = Sequence(0, 0, [_wrap(item, current, chain, path + [i], hits)
                               for i, item in enumerate(value)])
    elif isinstance(value, bool):                # before int: bool is an int
        node = Scalar(0, 0, "bool", value)
    elif value is None:
        node = Scalar(0, 0, "none", None)
    else:
        for kind, types in (("str", str), ("bytes", (bytes, bytearray)),
                            ("int", int), ("float", float)):
            if isinstance(value, types):
                node = Scalar(0, 0, kind, value)
                break
        else:
            raise _PathAkan(f"a {type(value).__name__} is not yapyon data, "
                            f"so the tree cannot be searched", _where(path))
    if value is current:
        hits.append((node, chain, path))
    return node
