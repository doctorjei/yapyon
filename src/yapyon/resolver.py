"""yapyon reference resolver (SPEC §5.2–5.5)

YAMLちゃうで。やぴょんやぴょん。

Replacement without computation (law 2): every hole names a value that is
already in the document, and the only things that happen are substitution and
the format's named encodings (§5.1.2) — no operators, no control flow.

Three rules do all the work:

  * **Nearest wins** (§5.2). A reference's first segment is searched outward
    from the y-string's own position — siblings, then each enclosing mapping
    in turn. Later steps traverse from there: a key, a list index, or a key
    named by another reference, which resolves in the y-string's scope and
    not in the scope of the node being indexed. `{__ROOT__.x}` skips
    the search. Shadowing an outer candidate is **not** warned about — the
    search is total, so nothing is ambiguous (see `_search`).
  * **The value, as Python writes it** (§5.4). A hole splices `str()` of
    its value, so `0xFF` and `255` splice alike and `3.10` splices as `3.1`
    — the rule of every mainstream language's interpolation, and the only
    one that covers values with no lexeme, such as a call's result.
  * **The splice matrix** (§5.5). Bytes reach text as their repr, `b'…'`,
    which marks the crossing (ehmon 5); text never reaches bytes at all.

Resolution runs to a fixpoint over the completed tree, so chains and forward
references work. A pass that makes no progress means a cycle, and that is an
akan at any depth — the document can never resolve.

The two expansion limits are a different thing and have **two tiers**: past
`MAX_*` (the spec's warn tier) is a shiran and resolution continues; past
`max_depth` / `max_size` (this implementation's ceiling, and what the loader
overrides) is an akan. Chained doubling grows a document exponentially, so the
ceiling is load-bearing; the warn tier is advice.

`yt` literals resolve here too, by exactly these rules — a template is a
y-string that is not *joined* (§6). The resolver stops one step short and
hands the consumer the parts with their resolved values.
"""

from __future__ import annotations

from typing import NamedTuple

from ._digits import decimal_text
from .lexer import (DOLLAR_HINT, AkanError, Ref, Yakamashiwa, fold_name,
                    is_dunder, parse_ref)
from .parser import (Mapping, MultiMap, Node, ResolvedTemplate, Scalar,
                     Sequence, YString)
from .serializers import READS_AST, SERIALIZERS, NotEncodable

# §5.3 defines two tiers, and they are not the same number.
#
#   MAX_* is the SPEC's warn tier. Exceeding it is a `shiran`: the document is
#   expensive, and some implementations will refuse it. It is fixed by the
#   spec, not a parameter -- a consumer does not get to decide what the format
#   calls suspicious.
#
#   REFUSE_* is THIS implementation's ceiling, and is what `loads`/`load`'s
#   `max_depth` / `max_size` arguments set. Exceeding it is an `akan`.
#   The spec declines to fix one ceiling for everyone; it does not invite an
#   implementation to have none. Chained doubling is exponential, so a library
#   parsing untrusted config needs a ceiling or it is a denial-of-service.
#
# Note the ambiguity this costs, accepted knowingly (operator, 2026-09-19):
# module-level MAX_DEPTH is the *warn* tier while the `max_depth` argument is
# the *refusal* ceiling.
MAX_DEPTH = 32                       # §5.3 warn tier (shiran above this)
MAX_SIZE = 1 << 20                   # §5.3 warn tier, codepoints/bytes rendered

REFUSE_FACTOR = 4                    # ceiling sits above the warn tier, so the
REFUSE_DEPTH = REFUSE_FACTOR * MAX_DEPTH   # shiran is reachable by default
REFUSE_SIZE = REFUSE_FACTOR * MAX_SIZE


class _At(NamedTuple):
    """A bare position, where a diagnostic outlives the node that earned it."""
    line: int
    col: int


# --------------------------------------------------------------------------- #
# Sites: an unresolved y-string, its scope chain, and how to replace it
# --------------------------------------------------------------------------- #
class _Site:
    __slots__ = ("node", "chain", "replace")

    def __init__(self, node: YString, chain: list, replace):
        self.node, self.chain, self.replace = node, chain, replace


def _collect(node: Node, chain: list, sites: list, replace) -> None:
    """Walk the tree, recording every splice site with its scope chain.

    A frame is `(mapping, branch_key)`, innermost first. Sequences and
    multimaps add no frame: list items have no keys, and a multimap's entry
    keys take no part in the search (§5.2)."""
    if isinstance(node, YString):
        # Every y-family literal is a site, `yt` included: since 2026-09-14 a
        # template resolves against the document like any other, and differs
        # only in not being joined (§6).
        sites.append(_Site(node, chain, replace))
        return
    if isinstance(node, Mapping):
        for pair in node.pairs:
            _collect(pair.value, [(node, pair.key)] + chain, sites,
                     _pair_slot(node, pair))
        return
    if isinstance(node, MultiMap):
        for entry in node.entries:
            _collect(entry.value, chain, sites, _entry_slot(entry))
        return
    if isinstance(node, Sequence):
        for index, item in enumerate(node.items):
            _collect(item, chain, sites, _index_slot(node, index))
        return


def _pair_slot(mapping: Mapping, pair):
    def slot(new):
        pair.value = new
        mapping.by_key[pair.key] = new           # the index must stay fresh:
    return slot                                  # lookups run during resolution


def _entry_slot(entry):
    def slot(new):
        entry.value = new
    return slot


def _index_slot(seq: Sequence, index: int):
    def slot(new):
        seq.items[index] = new
    return slot


def _dollar_hint_for(node, name: str) -> str:
    """`DOLLAR_HINT`, but only when this hole actually follows a `$`.

    An author who wrote `y"${HOME}"` and gets "no value named 'HOME' is in
    scope here" goes hunting for a missing key. The `$` is the clue, and it
    is in the literal's own parts.

    Only the *message* changes. The outcome was already right — an
    unresolved hole is akan either way — and `$` stays an ordinary character.
    """
    for i, (kind, value) in enumerate(node.parts):
        if kind != "hole" or not (value == name
                                  or value.startswith(name + ".")):
            continue
        if i and node.parts[i - 1][0] == "text" \
                and node.parts[i - 1][1].endswith("$"):
            return DOLLAR_HINT
    return ""


# --------------------------------------------------------------------------- #
# Resolver
# --------------------------------------------------------------------------- #
class Resolver:
    def __init__(self, tree: Node, *, max_depth: int = REFUSE_DEPTH,
                 max_size: int = REFUSE_SIZE, warn=None,
                 source: str | None = None):
        self.root = tree
        self.source = source                 # a name for diagnostics, if known
        self.max_depth = max_depth           # §5.3 refusal ceiling, not the
        self.max_size = max_size             # warn tier -- see the constants
        self._warn = warn
        self.warnings: list[str] = []
        self.rendered = 0
        self._depth: dict[int, int] = {}     # id(resolved Scalar) -> its depth
        # Deepest chain seen, as (depth, line, col). Kept so the warn-tier
        # shiran can be reported once, at a position that does not depend on
        # the order sites happen to resolve in -- see `_note_depth`.
        self._deepest: tuple[int, int, int] | None = None

    # -- diagnostics ---------------------------------------------------------
    def _akan(self, msg: str, at: Node):
        raise AkanError(msg, at.line, at.col, self.source)

    def _shiran(self, msg: str, at: Node):
        where = (f"line {at.line}, col {at.col}" if self.source is None
                 else f"{self.source}:{at.line}:{at.col}")
        text = f"shiran: {where}: {msg}"
        self.warnings.append(text)
        if self._warn is not None:
            self._warn(text)

    def _note_depth(self, depth: int, at: Node) -> None:
        """Remember the deepest chain, for one end-of-run shiran.

        Deepest wins; ties go to the earliest position in the document. Both
        tie-breaks are on the *document*, never on resolution order -- a site
        resolves whenever its targets happen to be ready, so "the first one to
        cross" would name a different line depending on how the document was
        arranged. That is trap 4, and it is a format bug here, not a style one.
        """
        here = (depth, at.line, at.col)
        if self._deepest is None:
            self._deepest = here
            return
        best_depth, best_line, best_col = self._deepest
        if depth > best_depth or (depth == best_depth
                                  and (at.line, at.col) < (best_line, best_col)):
            self._deepest = here

    # -- driver --------------------------------------------------------------
    def resolve(self) -> Node:
        holder = [self.root]
        sites: list[_Site] = []
        _collect(self.root, [], sites, lambda new: holder.__setitem__(0, new))

        while sites:
            deferred, progress = [], False
            for site in sites:
                value = self._try(site)
                if value is None:
                    deferred.append(site)
                else:
                    site.replace(value)
                    progress = True
            if deferred and not progress:
                self._akan_stuck(deferred)
            sites = deferred
        self.root = holder[0]
        self._warn_tier()
        return self.root

    def _warn_tier(self) -> None:
        """§5.3's warn tier: one shiran each, after the run, or none.

        Deliberately not raised inline. Both quantities are properties of the
        whole document -- the deepest chain, the total rendered -- so reporting
        the first site to cross would name whichever one the fixpoint reached
        first, and that is resolution order. Reported here, the position and
        the number are the same for the same bytes.

        Neither fix changes what the document means: shorten the chain, or
        raise the consumer's ceiling. That is what keeps these on the right
        side of the shiran bar.
        """
        if self._deepest is not None and self._deepest[0] > MAX_DEPTH:
            depth, line, col = self._deepest
            self._shiran(
                f"a dependency chain {depth} deep passes §5.3's warn "
                f"threshold ({MAX_DEPTH}); this document is costly to resolve "
                f"and an implementation may refuse it -- shorten the chain, or "
                f"raise max_depth where it is loaded",
                _At(line, col))
        if self.rendered > MAX_SIZE:
            self._shiran(
                f"the document renders {self.rendered} units, passing §5.3's "
                f"warn threshold ({MAX_SIZE}); an implementation may refuse it "
                f"-- raise max_size where it is loaded",
                self.root)

    def _akan_stuck(self, deferred: list):
        """§5.3: no progress with references remaining is a cycle."""
        stuck = []
        for site in deferred:
            for kind, ref in site.node.parts:
                if kind == "hole":
                    stuck.append(f"{{{ref}}} at line {site.node.line}, col "
                                 f"{site.node.col}")
        self._akan("references never resolve (they form a cycle): "
                   + "; ".join(stuck), deferred[0].node)

    # -- one site ------------------------------------------------------------
    def _try(self, site: _Site):
        """Resolve one y-string, or None to defer it to a later pass."""
        node = site.node
        targets, pending = {}, False
        for kind, ref in node.parts:
            if kind != "hole":
                continue
            target = self._lookup(ref, site)             # akan: name not found
            if isinstance(target, YString):
                pending = True                           # a chain: try later
            elif isinstance(target, ResolvedTemplate):
                # A template is not a value a string can absorb, and joining
                # one would throw away the parts it exists to preserve.
                self._akan("cannot splice a template into a string", node)
            targets[ref] = target
        if pending:
            return None

        # Depth is the length of the dependency chain behind this string, not
        # a pass counter: passes depend on the order keys happen to appear,
        # and the same document must resolve the same way either way.
        depth = 1 + max((self._depth.get(id(t), 0) for t in targets.values()),
                        default=0)
        if depth > self.max_depth:
            self._akan(f"resolution exceeded the depth ceiling "
                       f"({self.max_depth}): this y-string sits at the end of "
                       f"a chain {depth} deep -- raise max_depth to accept it",
                       node)
        self._note_depth(depth, node)

        if node.prefix == "yt":
            # §6: resolve exactly as `y` does, then stop short of the join.
            # No size accounting -- nothing is rendered here, and whether the
            # consumer ever renders is its business.
            result = ResolvedTemplate(
                node.line, node.col,
                [("text", part) if kind == "text"
                 else ("hole", part, targets[part])
                 for kind, part in node.parts])
            self._depth[id(result)] = depth
            site.replace(result)
            return result

        to_bytes = node.prefix == "yb"
        pieces = [part if kind == "text"
                  else self._splice(targets[part], node, to_bytes)
                  for kind, part in node.parts]
        value = (b"" if to_bytes else "").join(pieces)
        self.rendered += len(value)
        if self.rendered > self.max_size:
            self._akan(f"document exceeds the rendered-size ceiling "
                       f"({self.max_size}) -- raise max_size to accept it",
                       node)
        result = Scalar(node.line, node.col, "bytes" if to_bytes else "str",
                        value, prefix="b" if to_bytes else "")
        self._depth[id(result)] = depth
        return result

    # -- §5.5, the splice matrix --------------------------------------------
    def _splice(self, target: Node, at: YString, to_bytes: bool):
        """The matrix, with a position attached. `splice_text` holds the rule
        itself; this only turns a refusal into an akan at the right place."""
        if not to_bytes:
            text, why = splice_text(target)
            if why:
                self._akan(why, at)
            return text
        if isinstance(target, (Mapping, Sequence, MultiMap)):
            self._akan("cannot interpolate a list, dict, or multimap into a "
                       "string", at)
        if not isinstance(target, Scalar):
            raise Yakamashiwa(f"unresolved {type(target).__name__} reached "
                              f"the splice step")
        if target.type == "str":
            self._akan("cannot splice text into a byte string; there is "
                       "no implicit encode (spell the bytes you want)", at)
        if target.type == "bytes":
            return target.value
        return _text(target).encode("ascii")


    def _lookup(self, ref: str, site: _Site) -> Node:
        """Walk a parsed reference (GRAMMAR §G5) from its anchor to its target.

        `a.b` is sugar for `a["b"]`, so both arrive here as the same step and
        the equivalence needs no separate code path.
        """
        parsed = parse_ref(ref)
        if parsed.key:                               # §5.1.1: names a position
            return self._key_of(parsed, ref, site)
        if parsed.call is not None:                  # §13.1: a call
            return self._call(parsed.call, ref, site)
        return self._lookup_parsed(parsed, ref, site)

    def _lookup_parsed(self, parsed: Ref, ref: str, site: _Site) -> Node:
        """The anchor-then-steps walk, given an already-parsed reference.

        Split out so a serializer can reach the value it encodes without
        re-parsing, and without a second copy of the traversal."""
        steps = list(parsed.steps)
        if parsed.root:
            current = self.root
        elif parsed.parents:
            current = self._climb(parsed.parents, ref, site)
        else:
            if not steps or steps[0][0] != "key":
                raise Yakamashiwa(f"reference {ref!r} does not begin with a "
                                  f"name")
            current = self._search(steps.pop(0)[1], site)
        for step in steps:
            current = self._step(current, step, ref, site)
        return current

    # -- §5.1.1's relative anchors ----------------------------------------------
    #
    # `site.chain` is `[(mapping, key), ...]` innermost first, where entry 0 is
    # the mapping directly holding this pair and the key is the pair's own.
    # `__PARENT__` climbs **that** chain — the same one §5.2 searches — so
    # sequence and multimap levels are transparent to it exactly as they are to
    # the scope search. One notion of nesting, not two: a second one would be
    # the drift trap, and a list has no key for `__KEY__` to report anyway.
    def _climb(self, hops: int, ref: str, site: _Site) -> Node:
        if hops > len(site.chain):
            self._akan(f"{{{ref}}}: {self._too_far(hops, site)}", site.node)
        return site.chain[hops - 1][0]

    def _key_of(self, parsed: Ref, ref: str, site: _Site) -> Node:
        """`__KEY__`: the key of the pair this hole sits in, or of an
        enclosing one. A key is always a UAX #31 identifier, so it is
        closure-safe as text by construction (§5.5); into a `yb` it is
        text→bytes and the ordinary law-5 akan catches it with no special
        case here."""
        if parsed.parents >= len(site.chain):
            self._akan(f"{{{ref}}}: {self._too_far(parsed.parents + 1, site)}",
                       site.node)
        name = site.chain[parsed.parents][1]
        return Scalar(site.node.line, site.node.col, "str", name)

    # -- §13.1 calls ----------------------------------------------------------
    def _call(self, call, ref: str, site: _Site) -> Node:
        """Apply a call. **Interim (build stage 1):** only the 0.2 shape —
        one serializer applied to a path, no keywords — resolves; every
        other call the grammar now admits akans until stage 6 builds §13.1."""
        if is_dunder(call.name) and call.name not in SERIALIZERS:
            self._akan(f"{{{ref}}}: there is no built-in named {call.name}(); "
                       f"yapyon defines "
                       f"{', '.join(n + '()' for n in SERIALIZERS)}", site.node)
        target = call.args[0] if len(call.args) == 1 else None
        if (not is_dunder(call.name) or call.kwargs
                or not isinstance(target, Ref) or target.call is not None
                or target.key):
            self._akan(f"{{{ref}}}: this call is well-formed, but calls other "
                       f"than a serializer on a path are not built yet",
                       site.node)
        return self._serialize(call.name, target, ref, site)

    # -- §5.1.2 named serializers -------------------------------------------
    def _serialize(self, serializer: str, parsed: Ref, ref: str,
                   site: _Site) -> Node:
        """`{cfg.__AS_JSON__()}` — the author naming a container's encoding.

        A serializer is a built-in function (§5.1.2); stage 6 of the 0.3.0
        build moves this onto §13.1's one call path. Until then it is
        reached only through `_call`'s interim shape."""
        target = self._lookup_parsed(parsed, ref, site)
        if not isinstance(target, (Mapping, Sequence, MultiMap)):
            self._akan(f"{{{ref}}}: {serializer}() encodes a list or a "
                       f"mapping; applying one to a single value is reserved",
                       site.node)
        try:
            if serializer in READS_AST:
                text = SERIALIZERS[serializer](_settled(target))
            else:
                text = SERIALIZERS[serializer](_plain(target))
        except _NotYet as pending:
            # Hand the unresolved node back: `_try` defers on a YString, so
            # this rejoins the ordinary fixpoint instead of pre-empting it.
            return pending.node
        except NotEncodable as exc:
            self._akan(f"{{{ref}}}: {exc}", site.node)
        return Scalar(site.node.line, site.node.col, "str", text)

    def _too_far(self, hops: int, site: _Site) -> str:
        depth = len(site.chain)
        return (f"{hops} levels up from here is past the document root, which "
                f"is {depth} level{'' if depth == 1 else 's'} away and has no "
                f"key of its own")

    def _step(self, node: Node, step, ref: str, site: _Site) -> Node:
        """One traversal step: a key, an integer index, or a key named by
        another reference."""
        kind, payload = step
        if kind == "ref":
            # The inner reference resolves in the scope of the *y-string*,
            # not of the node being indexed. `{mind.dialects[protocol]}`
            # means "the entry named by *my* protocol".
            key = self._subscript_value(payload, ref, site)
            # A resolved key is whatever it resolved to: an int indexes a
            # list, exactly as a literal one would. The two spellings of a
            # subscript must not disagree about what the value means.
            if isinstance(key, int):
                return self._index(node, key, ref, site.node)
            return self._child(node, key, ref, site.node, spelled_out=False)
        if kind == "index":
            return self._index(node, payload, ref, site.node)
        return self._child(node, payload, ref, site.node, spelled_out=True)

    def _subscript_value(self, inner: Ref, ref: str, site: _Site):
        """Resolve `[someref]` to the key it names."""
        target = self._lookup(inner.text, site)
        if not isinstance(target, Scalar):
            self._akan(f"{{{ref}}}: the subscript {{{inner.text}}} must name "
                       f"a string or a number to use as a key, not a "
                       f"container", site.node)
        if target.type == "str":
            # A resolved key means what a written one means, so it is folded
            # the same way (SPEC §7): `p: "ｎａｍｅ"` then `{d[p]}` finds `name`.
            return fold_name(target.value)
        if target.type == "int":
            return target.value
        self._akan(f"{{{ref}}}: the subscript {{{inner.text}}} names a "
                   f"{target.type}, which is not a key", site.node)

    def _index(self, node: Node, i: int, ref: str, at: YString) -> Node:
        if isinstance(node, MultiMap):
            self._akan(f"{{{ref}}}: index a multimap's key view, not the "
                       f"multimap — positional entry access is reserved", at)
        if not isinstance(node, Sequence):
            self._akan(f"{{{ref}}}: cannot index {i}, because the value "
                       f"named before it is not a list", at)
        # A negative index counts from the end, as in Python. The range check
        # covers both ends, since a subscript reference can deliver any int.
        if i >= len(node.items):
            self._akan(f"{{{ref}}}: index {i} is past the end of a list of "
                       f"{len(node.items)}", at)
        if i < -len(node.items):
            self._akan(f"{{{ref}}}: index {i} is before the start of a list "
                       f"of {len(node.items)}", at)
        return node.items[i]

    def _child(self, node: Node, seg, ref: str, at: YString,
               spelled_out: bool = True) -> Node:
        if isinstance(seg, int):
            self._akan(f"{{{ref}}}: {seg} is a number, and only a list takes "
                       f"one — write a key here", at)
        if isinstance(node, MultiMap):
            # §7.1 by-key traversal is a LIST VIEW: every value filed under
            # that key, in order. Nothing is picked, so nothing is guessed —
            # 0 entries give an empty list, N give N.
            items = [entry.value for entry in node.entries if entry.key == seg]
            return Sequence(node.line, node.col, items)
        if isinstance(node, Mapping):
            if seg not in node.by_key:
                self._akan(f"{{{ref}}}: there is no key {seg!r} here", at)
            return node.by_key[seg]
        if isinstance(node, Sequence):
            self._akan(f"{{{ref}}}: cannot look up {seg!r} in a list; index "
                       f"it with brackets instead", at)
        self._akan(f"{{{ref}}}: cannot look up {seg!r}, because the value "
                   f"named before it is not a mapping", at)

    def _search(self, name: str, site: _Site) -> Node:
        hits = []
        for level, (mapping, branch) in enumerate(site.chain):
            if level == 0 and name == branch:        # not the current key
                continue
            if name in mapping.by_key:
                hits.append((level, mapping))
        if not hits:
            self._akan(f"no value named {name!r} is in scope here"
                       f"{_dollar_hint_for(site.node, name)}", site.node)

        # Nearest wins (SPEC §5.2). Shadowing an outer definition is NOT
        # warned about: the rule is total and deterministic, so there is
        # nothing ambiguous to report, and a warning here would fire on
        # correct layered config while naming a "fix" ({__ROOT__.x}) that
        # changes the resolved value. Removed 2026-09-14; see
        # DESIGN_RATIONALE.md's diagnostics-register section.
        level, mapping = hits[0]
        return mapping.by_key[name]


class _NotYet(Exception):
    """A serializer's target still holds an unresolved y-string.

    Distinct from `NotEncodable`, which is permanent. This one means "ask me
    again next pass", and carries the offending node so the caller can hand it
    back to the fixpoint — which already knows how to defer on a `YString` and
    how to call a stall a cycle.
    """

    def __init__(self, node: Node):
        self.node = node


def _settled(node: Node) -> Node:
    """The subtree itself, once nothing in it is still waiting or deferred.

    `_plain`'s twin for the writers that read the AST (`READS_AST`): the same
    two outcomes, *not yet* and *never*, so a cycle through `__AS_YAPYON__()`
    is still reported as the cycle it is (trap 9). The only thing this
    encoding cannot carry is a `yt`, for the reason `expand_record` refuses
    one: a record's leaves are literals, and a template delivered in parts is
    not one. Joining it would make yapyon render what §6 leaves to the
    consumer.
    """
    if isinstance(node, YString):
        raise _NotYet(node)
    if isinstance(node, ResolvedTemplate):
        raise NotEncodable("a `yt` delivers its parts unjoined (§6) and a "
                           "record's leaves must all be literals, so there is "
                           "no yapyon record form for a template")
    if isinstance(node, Mapping):
        for pair in node.pairs:
            _settled(pair.value)
    elif isinstance(node, MultiMap):
        for pair in node.entries:
            _settled(pair.value)
    elif isinstance(node, Sequence):
        for item in node.items:
            _settled(item)
    return node


def _plain(node: Node):
    """A resolved subtree as plain Python, for a serializer to encode.

    Deliberately *not* `loader.build`: this refuses a multimap, which build
    accepts, because none of the target formats can carry repeated keys — and
    it must refuse rather than let an encoder improvise. A small walker over
    four node kinds, not a second loader.

    Numbers arrive as values, so each format encodes them by **its own**
    rules: inside JSON `3.10` and `3.1` are one number. Only a yapyon
    writer keeps lexemes (§4.4), which is why `__AS_YAPYON__` reads the AST.
    """
    if isinstance(node, Mapping):
        return {pair.key: _plain(pair.value) for pair in node.pairs}
    if isinstance(node, Sequence):
        return [_plain(item) for item in node.items]
    if isinstance(node, MultiMap):
        raise NotEncodable("a multimap's keys repeat and none of these "
                           "formats can hold that, so there is no faithful "
                           "encoding; serialize the entries you mean")
    if isinstance(node, Scalar):
        return node.value
    if isinstance(node, YString):
        # *Not* unencodable — merely not resolved yet. Saying "cannot be
        # serialized" here reports the wrong problem: the container may be
        # perfectly encodable one pass later, and if it never is, the honest
        # diagnosis is §5.3's cycle, naming every stuck reference. Two calls
        # whose arguments hold each other are the case that needs this.
        raise _NotYet(node)
    raise NotEncodable(f"a {type(node).__name__} cannot be serialized")


def _text(target: Scalar) -> str:
    """§5.4: a scalar splices its **value**, as Python's `str()` writes it.

    Python's own rules are the definition, not an approximation of it: an
    `int` in decimal, a `float` as its shortest round-tripping `repr`
    (positional for exponents −4 … 15, else `1e+16`), `True`/`False`/
    `None`, and bytes as their `repr`, `b'…'` — the marker of a crossing
    (ehmon 5). Equal values splice as equal text, whatever their spelling:
    `0xFF` and `255` both give `255`, `3.10` gives `3.1`."""
    if target.type == "str":
        return target.value
    if target.type == "bytes":
        return repr(target.value)
    if target.type == "int":                  # §3.1: never the host's limit
        return decimal_text(target.value)
    return str(target.value)


def splice_text(target: Node) -> tuple[str | None, str]:
    """§5.5 for the text direction: `(text, "")`, or `(None, why)`.

    **The one implementation of the matrix.** The resolver calls it to splice
    into a `y` string, where a refusal is an akan at parse; `Template.render`
    reaches the same answer through the text precomputed here, so a `yt`
    cannot come to disagree with the `y` it is supposed to be an unjoined
    version of. Two copies of this would drift — they have before (trap 5).

    A refusal is returned rather than raised because the two callers want it
    at different moments: a `y` is always rendered, so it akans at parse; a
    `yt` is rendered only if the consumer asks, so it must be able to *carry*
    a value it could never join.
    """
    if isinstance(target, (Mapping, Sequence, MultiMap)):
        return None, ("cannot interpolate a list, dict, or multimap into a "
                      "string")
    if not isinstance(target, Scalar):
        raise Yakamashiwa(f"unresolved {type(target).__name__} reached "
                          f"the splice step")
    return _text(target), ""

    # -- §5.2, the scope search ---------------------------------------------


def resolve(tree: Node, *, max_depth: int = REFUSE_DEPTH,
            max_size: int = REFUSE_SIZE, warn=None,
            source: str | None = None) -> Node:
    """Resolve every y/ry/yb literal in `tree`, in place. Returns the tree
    (which may itself be replaced, if the whole document was a y-string).

    `max_depth` / `max_size` are the **refusal ceiling**, not §5.3's warn
    tier: past them is an akan, past `MAX_DEPTH` / `MAX_SIZE` is a shiran.
    """
    return Resolver(tree, max_depth=max_depth, max_size=max_size,
                    warn=warn, source=source).resolve()
