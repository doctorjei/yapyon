"""yapyon reference resolver (SPEC §5.2–5.5)

YAMLちゃうで。やぴょんやぴょん。

Replacement without computation (law 2): every hole names a value that is
already in the document, a variable of the loading process's environment
(`{$NAME}`, `__ENV__`, §5.1.3), or a declared function's result (§13), and
the only things that happen are substitution, the format's named encodings
(§5.1.2), and those calls — no operators, no control flow.

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

from ._digits import REFUSE_DIGITS, decimal_text
from .contract import (BindError, Declared, Lender, ResultError,
                       float_misfit, result_node)
from .environment import (ACCESS_OFF, NOT_FOUND, STANDARD_ENV, EnvValueError,
                          environment)
from .lexer import (DOLLAR_HINT, AkanError, Call, Literal, Ref, Yakamashiwa,
                    fold_name, is_dunder, parse_ref)
from .parser import (Copy, Mapping, MultiMap, Node, Pair, ResolvedTemplate,
                     Scalar, Sequence, YString)
from .serializers import BUILTIN_NAMES, ENV_BUILTIN, SERIALIZERS, YEETED_YT
from .typespec import check, parse_type, show

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


_STANDARD = object()      # Resolver's default: the process env, standard names


def _standard_environment():
    """`loads`' defaults (SPEC §5.1.4): the process environment, read now,
    exposing the standard variables of this environment system."""
    import os
    return environment(os.environ, STANDARD_ENV)


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
                 source: str | None = None, functions=None,
                 max_digits: int = REFUSE_DIGITS, environment=_STANDARD):
        self.root = tree
        self.functions = functions           # a contract.Functions, or None
        # §5.1.3: one snapshot per load, or None when access is off.
        self.environment = (_standard_environment()
                            if environment is _STANDARD else environment)
        self.max_digits = max_digits         # §3.1, for function results
        self._lender = Lender()              # one per load: borrows keep identity
        self.source = source                 # a name for diagnostics, if known
        self.max_depth = max_depth           # §5.3 refusal ceiling, not the
        self.max_size = max_size             # warn tier -- see the constants
        self._warn = warn
        self.warnings: list[str] = []
        self.rendered = 0
        self._depth: dict[int, int] = {}     # id(resolved Scalar) -> its depth
        self._facts: dict[int, tuple] = {}   # id(settled node) -> (node, size,
                                             # depth), for §5.6's copies
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
                    shown = (f"({ref})" if isinstance(site.node, Copy)
                             else f"{{{ref}}}")
                    stuck.append(f"{shown} at line {site.node.line}, col "
                                 f"{site.node.col}")
        self._akan("references never resolve (they form a cycle): "
                   + "; ".join(stuck), deferred[0].node)

    # -- one site ------------------------------------------------------------
    def _try(self, site: _Site):
        """Resolve one y-string, or None to defer it to a later pass."""
        node = site.node
        if isinstance(node, Copy):
            return self._copy(site)
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

    # -- §5.6, copies ----------------------------------------------------------
    def _copy(self, site: _Site):
        """`(ref)`: the value `ref` names — or a call returns, through the
        one call path — copied once it is wholly resolved, or None to
        defer.

        Resolve first, then copy: the copy holds finished values, so nothing
        in it depends on where it lands. It is a copy, never the node itself
        — no node appears in the tree twice (linearity), so a consumer never
        holds one object at two keys. The copy is built from the resolved
        AST, so every literal keeps its lexeme (§3)."""
        node, ref = site.node, site.node.ref
        target = self._lookup(ref, site)
        facts = self._settled(target)
        if facts is None:
            # Something in it is still pending. If that something is this
            # copy, it never will be: say so here rather than as a cycle.
            if target is node or _contains(target, node):
                self._akan(f"({ref}) contains this copy, so the copy would "
                           f"contain itself; name a block that does not "
                           f"contain it", node)
            return None                               # §5.3: wait for it
        size, deep = facts
        depth = 1 + deep
        if depth > self.max_depth:
            self._akan(f"resolution exceeded the depth ceiling "
                       f"({self.max_depth}): this copy sits at the end of a "
                       f"chain {depth} deep -- raise max_depth to accept it",
                       node)
        self._note_depth(depth, node)
        # §5.3: a copy renders what it copies, so a chain of copies doubling
        # its input meets the same ceiling a chain of y-strings does. Judged
        # before the copy is built, so the ceiling bounds the work as well.
        self.rendered += size
        if self.rendered > self.max_size:
            self._akan(f"document exceeds the rendered-size ceiling "
                       f"({self.max_size}) -- raise max_size to accept it",
                       node)
        result = self._clone(target)
        self._depth[id(result)] = depth
        self._facts[id(result)] = (result, size, depth)
        return result

    def _settled(self, node: Node):
        """`(size, depth)` for a subtree with nothing pending, or None.

        Size is what a copy of it adds to §5.3's rendered total: the length
        of every string and bytes value, and one for every other value.
        Depth is `_deep_depth`'s. A settled subtree never changes again —
        only a pending node is ever replaced — so the answer is kept, which
        is what keeps a chain of copies from re-walking what it copies.
        The node itself is kept beside it, so a recycled `id` cannot match."""
        known = self._facts.get(id(node))
        if known is not None and known[0] is node:
            return known[1], known[2]
        if isinstance(node, YString):
            return None
        own = self._depth.get(id(node), 0)
        if isinstance(node, Scalar):
            size = len(node.value) if node.type in ("str", "bytes") else 1
            deep = own
        else:
            children = (_children(node) if not isinstance(node,
                                                          ResolvedTemplate)
                        else [part[2] for part in node.parts
                              if part[0] == "hole"])
            size, deep = 1, own
            for child in children:
                facts = self._settled(child)
                if facts is None:
                    return None
                size, deep = size + facts[0], max(deep, facts[1])
        self._facts[id(node)] = (node, size, deep)
        return size, deep

    def _clone(self, node: Node) -> Node:
        """A fresh copy of a resolved subtree, positions and lexemes kept,
        each node carrying the dependency depth of the one it copies.

        Built field by field rather than through the dataclass constructors:
        a copy can be a million nodes, and §5.3's ceiling admits that much."""
        new = object.__new__(type(node))
        fields = dict(node.__dict__)
        if isinstance(node, Mapping):
            fields["pairs"] = [self._clone_pair(p) for p in node.pairs]
            fields["by_key"] = {p.key: p.value for p in fields["pairs"]}
        elif isinstance(node, MultiMap):
            fields["entries"] = [self._clone_pair(e) for e in node.entries]
        elif isinstance(node, Sequence):
            fields["items"] = [self._clone(item) for item in node.items]
        elif isinstance(node, ResolvedTemplate):
            fields["parts"] = [part if part[0] == "text"
                               else (part[0], part[1], self._clone(part[2]))
                               for part in node.parts]
        elif not isinstance(node, Scalar) or isinstance(node, YString):
            raise Yakamashiwa(f"unresolved {type(node).__name__} reached "
                              f"the copy step")
        new.__dict__ = fields
        depth = self._depth.get(id(node))
        if depth is not None:
            self._depth[id(new)] = depth
        return new

    def _clone_pair(self, pair: Pair) -> Pair:
        new = object.__new__(Pair)
        new.__dict__ = dict(pair.__dict__, value=self._clone(pair.value))
        return new

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
        if parsed.env is not None:                   # §5.1.3: {$NAME}
            return self._env(parsed.env, ref, site, strict=True)
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
            if isinstance(current, YString):
                # Waiting on a y-string mid-walk (a subscript's key, or the
                # value being walked): defer the whole reference, as §5.3's
                # fixpoint does for any target not resolved yet. Judging it
                # now would make the answer depend on document order (trap 4).
                return current
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
    def _call(self, call: Call, ref: str, site: _Site) -> Node:
        """Apply a call (§13.1): its shape first, then its arguments
        inside-out and left to right, then the function.

        Returns the result node — or, where an argument is not resolved yet,
        the `YString` it waits on. `_try` defers on that exactly as it does
        on a hole whose target is unresolved, so a call waits **at every
        level of nesting and every link of a chain**, and two calls waiting
        on each other stall the fixpoint and are reported as §5.3's cycle.
        A new path into the fixpoint must be able to reach every outcome it
        defines, not only success (trap 9)."""
        builtin = self._call_shape(call, ref, site)
        args = []
        for arg in call.args:
            node = self._argument(arg, call, ref, site)
            if isinstance(node, YString):
                return node
            args.append(node)
        kwargs = {}
        for name, arg in call.kwargs:
            node = self._argument(arg, call, ref, site)
            if isinstance(node, YString):
                return node
            kwargs[name] = node
        depth = max(map(self._deep_depth, args + list(kwargs.values())),
                    default=0)
        if builtin is ENV_BUILTIN:
            result = self._env_call(args, kwargs, ref, site)
        elif isinstance(builtin, Declared):
            # §13.1: keywords fill parameters by name, and the function
            # receives every argument in declared order.
            ordered = args + [kwargs[name] for name, _ in
                              builtin.params[len(args):]]
            result = self._declared(builtin, call, ordered, ref, site)
        else:
            result = self._builtin(builtin, call, args[0], kwargs, ref, site)
        self._depth[id(result)] = depth
        return result

    def _call_shape(self, call: Call, ref: str, site: _Site):
        """Name, arity, and keywords — fixed by the call as written, so
        checked before any argument is (§13.5)."""
        seen = set()
        for name, _ in call.kwargs:
            if name in seen:
                self._akan(f"{{{ref}}}: keyword argument {name} is repeated "
                           f"in {call.name}()", site.node)
            seen.add(name)
        if not is_dunder(call.name):
            return self._declared_shape(call, ref, site)
        if call.name == ENV_BUILTIN:
            return self._env_shape(call, ref, site)
        builtin = SERIALIZERS.get(call.name)
        if builtin is None:
            self._akan(f"{{{ref}}}: there is no built-in named {call.name}(); "
                       f"yapyon defines "
                       f"{', '.join(n + '()' for n in BUILTIN_NAMES)}",
                       site.node)
        if len(call.args) != 1:
            self._akan(f"{{{ref}}}: {call.name}() takes one argument "
                       f"({builtin.takes}), not {len(call.args)}", site.node)
        for name, _ in call.kwargs:
            if name not in builtin.keywords:
                offer = (f"it takes {', '.join(builtin.keywords)}"
                         if builtin.keywords else "it takes none")
                self._akan(f"{{{ref}}}: {call.name}() has no keyword "
                           f"argument {name}; {offer}", site.node)
        return builtin

    # -- §5.1.3 the environment ------------------------------------------------
    def _env_shape(self, call: Call, ref: str, site: _Site) -> str:
        """`__ENV__(var_name, fallback=None)`: one or two positional
        arguments, and `fallback` by keyword if not by position."""
        given = len(call.args) + len(call.kwargs)
        for name, _ in call.kwargs:
            if name != "fallback":
                self._akan(f"{{{ref}}}: __ENV__() has no keyword argument "
                           f"{name}; it takes fallback", site.node)
            if len(call.args) > 1:
                self._akan(f"{{{ref}}}: __ENV__()'s fallback is given by "
                           f"position and again by keyword", site.node)
        if not call.args or given > 2:
            self._akan(f"{{{ref}}}: __ENV__() takes a variable name and an "
                       f"optional fallback, not {given} argument"
                       f"{'' if given == 1 else 's'}", site.node)
        return ENV_BUILTIN

    def _env_call(self, args: list, kwargs: dict, ref: str,
                  site: _Site) -> Node:
        """The variable's value, or the fallback when it is not found. The
        fallback was resolved with the other arguments, used or not."""
        miss = check(args[0], _signature("str"))
        if miss is not None:
            self._akan(f"{{{ref}}}: __ENV__()'s var_name takes str, not "
                       f"{miss.found}", miss.node)
        fallback = args[1] if len(args) > 1 else kwargs.get("fallback")
        if fallback is None:
            fallback = Scalar(site.node.line, site.node.col, "none", None)
        found = self._env(args[0].value, ref, site, strict=False)
        return fallback if found is None else found

    def _env(self, name: str, ref: str, site: _Site, *, strict: bool):
        """The one lookup behind `{$NAME}` and `__ENV__` (§5.1.3). Not found
        is akan when strict and None otherwise; access off is akan always —
        a fallback answers "not set", never "not allowed"."""
        if self.environment is None:
            self._akan(f"{{{ref}}}: {ACCESS_OFF}", site.node)
        try:
            value = self.environment.get(name)
        except EnvValueError as exc:
            self._akan(f"{{{ref}}}: {exc}", site.node)
        if value is None:
            if strict:
                self._akan(f"{{{ref}}}: ${name} {NOT_FOUND}", site.node)
            return None
        return Scalar(site.node.line, site.node.col, "str", value)

    def _declared_shape(self, call: Call, ref: str, site: _Site) -> Declared:
        declared = None if self.functions is None else \
            self.functions.get(call.name)
        if declared is None:
            where = ("no contract was given to the loader"
                     if self.functions is None else "the contract does not "
                     "declare it")
            self._akan(f"{{{ref}}}: {call.name}() is not a built-in, and "
                       f"{where} (SPEC §13.2)", site.node)
        params = [name for name, _ in declared.params]
        names = ", ".join(params)
        count = len(params)
        if len(call.args) > count or (not call.kwargs
                                      and len(call.args) != count):
            by = " by position" if call.kwargs else ""
            self._akan(f"{{{ref}}}: {call.name}() takes {count} argument"
                       f"{'' if count == 1 else 's'} ({names}), not "
                       f"{len(call.args)}{by}", site.node)
        positional = set(params[:len(call.args)])
        for name, _ in call.kwargs:
            if name not in params:
                self._akan(f"{{{ref}}}: {call.name}() has no parameter "
                           f"{name}; it takes {names}", site.node)
            if name in positional:
                self._akan(f"{{{ref}}}: {call.name}()'s parameter {name} is "
                           f"given by position and again by keyword",
                           site.node)
        given = positional | {name for name, _ in call.kwargs}
        missing = [name for name in params if name not in given]
        if missing:
            self._akan(f"{{{ref}}}: {call.name}() is missing "
                       f"{'parameter' if len(missing) == 1 else 'parameters'} "
                       f"{', '.join(missing)} (it takes {names})", site.node)
        return declared

    def _declared(self, declared: Declared, call: Call, args: list,
                  ref: str, site: _Site) -> Node:
        """A declared function (§13.2–§13.5): every argument checked deep
        against its parameter, the code found and called with borrows, and
        its result checked against `returns` and made fresh data. A failure
        is akan naming the function — never a host traceback."""
        values = []
        for (pname, ptype), node in zip(declared.params, args):
            template = _template_in(node)
            miss = check(node, ptype)
            if template is not None or miss is not None:
                where = template if template is not None else miss.node
                found = "a template" if template is not None else miss.found
                inner = ("" if where is node or miss is None else
                         f"; here it wants {show(miss.wanted)}")
                self._akan(f"{{{ref}}}: {call.name}()'s parameter {pname} "
                           f"takes {show(ptype)}{inner}, not {found}", where)
            misfit = float_misfit(node, ptype)
            if misfit is not None:
                self._akan(f"{{{ref}}}: {call.name}()'s parameter {pname} "
                           f"takes a float, and this int has none (it is "
                           f"outside the float range)", misfit)
            values.append(self._lender.value(node, ptype))
        try:
            code = self.functions.code(declared)
        except BindError as exc:
            self._akan(f"{{{ref}}}: {exc}", site.node)
        try:
            result = code(*values)
        except Exception as exc:                 # §13.5: never a traceback
            self._akan(f"{{{ref}}}: {call.name}() failed: "
                       f"{type(exc).__name__}: {exc}", site.node)
        try:
            return result_node(result, declared.returns, site.node,
                               max_digits=self.max_digits,
                               warn=lambda m: self._shiran(
                                   f"{{{ref}}}: {call.name}() {m}", site.node))
        except ResultError as exc:
            self._akan(f"{{{ref}}}: {call.name}() {exc}", site.node)

    def _argument(self, arg, call: Call, ref: str, site: _Site) -> Node:
        """One argument's value: a literal, a nested call's result, a key,
        or a **borrow** — the node a reference names, lent as it is (§13.1).
        A borrow is ready only when nothing in its subtree is pending."""
        if isinstance(arg, Literal):
            return _literal_node(arg, site.node)
        if arg.call is not None:
            return self._call(arg.call, ref, site)
        if arg.key:
            return self._key_of(arg, ref, site)
        node = self._lookup_parsed(arg, ref, site)
        if _contains(node, site.node):
            # §13.1: an argument may not contain the call site. For an anchor
            # the grammar already refuses it; any other reference is checked
            # here, when it resolves, and the akan still lands at parse.
            self._akan(f"{{{ref}}}: {arg.text} contains this hole, so "
                       f"{call.name}() would need the value it is computing; "
                       f"name a block that does not contain it", site.node)
        pending = _pending(node)
        return pending if pending is not None else node

    def _builtin(self, builtin, call: Call, target: Node, kwargs: dict,
                 ref: str, site: _Site) -> Node:
        """A built-in (§5.1.2): type-check, then write. A `yt` anywhere in the
        argument draws §5.1.2's one message, shared with `expand_record`."""
        template = _template_in(target)
        if template is not None:
            self._akan(f"{{{ref}}}: {YEETED_YT}", template)
        miss = check(target, _signature(builtin.takes))
        if miss is not None:
            note = (f" -- {builtin.note}"
                    if builtin.note and miss.node is target else "")
            self._akan(f"{{{ref}}}: {call.name}() takes {show(miss.wanted)}, "
                       f"not {miss.found}{note}", miss.node)
        options = {}
        for name, node in kwargs.items():
            wanted, _ = builtin.keywords[name]
            miss = check(node, _signature(wanted))
            if miss is not None:
                self._akan(f"{{{ref}}}: {call.name}()'s {name} takes "
                           f"{show(miss.wanted)}, not {miss.found}", miss.node)
            options[name] = node.value
        pending = _pending(target)
        if pending is not None:
            # Unreachable while `_argument` waits for the whole subtree, and
            # kept so that a change there fails loudly rather than as the
            # wrong diagnosis (trap 9).
            raise Yakamashiwa(f"{call.name}() reached an unresolved node "
                              f"after its argument was judged ready")
        text = builtin.write(target, warn=lambda m: self._shiran(
            f"{{{ref}}}: {m}", site.node), **options)
        return Scalar(site.node.line, site.node.col, "str", text)

    def _deep_depth(self, node: Node) -> int:
        """The longest dependency chain behind anything in `node` (§5.3):
        an argument borrowed whole carries the chains of what it holds."""
        best = self._depth.get(id(node), 0)
        for child in _children(node):
            best = max(best, self._deep_depth(child))
        return best

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
            if isinstance(key, YString):
                return key
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
        if isinstance(target, YString):
            return target                            # not resolved yet
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


def _children(node: Node) -> list:
    if isinstance(node, Mapping):
        return [pair.value for pair in node.pairs]
    if isinstance(node, MultiMap):
        return [entry.value for entry in node.entries]
    if isinstance(node, Sequence):
        return list(node.items)
    return []


def _pending(node: Node) -> YString | None:
    """The first unresolved y-string in `node`'s subtree, or None."""
    if isinstance(node, YString):
        return node
    for child in _children(node):
        found = _pending(child)
        if found is not None:
            return found
    return None


def _contains(node: Node, target: Node) -> bool:
    """Is `target` inside `node` — by identity, since a borrow is the node?"""
    return any(child is target or _contains(child, target)
               for child in _children(node))


def _template_in(node: Node) -> ResolvedTemplate | None:
    if isinstance(node, ResolvedTemplate):
        return node
    for child in _children(node):
        found = _template_in(child)
        if found is not None:
            return found
    return None


_SIGNATURES: dict[str, tuple] = {}


def _signature(text: str):
    """A built-in's parameter type, parsed once."""
    if text not in _SIGNATURES:
        _SIGNATURES[text] = parse_type(text)
    return _SIGNATURES[text]


def _literal_node(literal: Literal, at: Node) -> Scalar:
    """A literal argument as the node it would be as a value. It has no
    position of its own inside the hole, so it takes the hole's."""
    tok = literal.token
    kind = {"STRING": "str", "BYTES": "bytes", "INT": "int",
            "FLOAT": "float"}.get(tok.kind)
    if kind is None:
        kind = "bool" if isinstance(tok.value, bool) else "none"
    return Scalar(at.line, at.col, kind, tok.value, lexeme=literal.lexeme,
                  prefix=tok.prefix)


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
            source: str | None = None, functions=None,
            max_digits: int = REFUSE_DIGITS, environment=_STANDARD) -> Node:
    """Resolve every y/ry/yb literal in `tree`, in place. Returns the tree
    (which may itself be replaced, if the whole document was a y-string).

    `max_depth` / `max_size` are the **refusal ceiling**, not §5.3's warn
    tier: past them is an akan, past `MAX_DEPTH` / `MAX_SIZE` is a shiran.
    """
    return Resolver(tree, max_depth=max_depth, max_size=max_size,
                    warn=warn, source=source, functions=functions,
                    max_digits=max_digits,
                    environment=environment).resolve()
