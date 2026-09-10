"""yapyon reference resolver — v0.1 (SPEC §5.2–5.5)

YAMLちゃうで。やぴょんやぴょん。

Replacement without computation (law 2): every hole names a value that is
already in the document, and the only thing that happens is substitution.

Three rules do all the work:

  * **Nearest wins** (§5.2). A reference's first segment is searched outward
    from the y-string's own position — siblings, then each enclosing mapping
    in turn. Later segments are plain child traversal. `{__ROOT__.x}` skips
    the search. Resolving locally while an outer candidate exists is legal
    but suspicious, so it emits a shiran.
  * **Lexeme, not value** (§5.4). `version: 3.10` splices the characters
    `3.10`, never `3.1`. Only the parser's preserved lexeme makes that
    possible, which is why resolution happens here and not after loading.
  * **The splice matrix** (§5.5). Nothing crosses a type boundary without
    naming the encoding (law 5): b64-spelled bytes reach text as base64,
    b-spelled bytes never do, and text never reaches bytes at all.

Resolution runs to a fixpoint over the completed tree, so chains and forward
references work. A pass that makes no progress means a cycle. Both caps
(depth, rendered size) are load-bearing: chained doubling grows a document
exponentially, and each is loader-overridable.

`yt` literals are not touched. Their holes belong to whatever scope the
consumer supplies at fill time (§6).
"""

from __future__ import annotations

import base64

from .lexer import AkanError, Yakamashiwa
from .parser import Mapping, MultiMap, Node, Scalar, Sequence, YString

MAX_DEPTH = 32                       # §5.3, loader-overridable
MAX_SIZE = 1 << 20                   # §5.3, bytes/codepoints rendered


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
        if node.prefix != "yt":                  # templates are the consumer's
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


# --------------------------------------------------------------------------- #
# Resolver
# --------------------------------------------------------------------------- #
class Resolver:
    def __init__(self, tree: Node, *, max_depth: int = MAX_DEPTH,
                 max_size: int = MAX_SIZE, warn=None):
        self.root = tree
        self.max_depth = max_depth
        self.max_size = max_size
        self._warn = warn
        self.warnings: list[str] = []
        self.rendered = 0
        self._depth: dict[int, int] = {}     # id(resolved Scalar) -> its depth

    # -- diagnostics ---------------------------------------------------------
    def _akan(self, msg: str, at: Node):
        raise AkanError(msg, at.line, at.col)

    def _shiran(self, msg: str, at: Node):
        text = f"shiran: line {at.line}, col {at.col}: {msg}"
        self.warnings.append(text)
        if self._warn is not None:
            self._warn(text)

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
        return self.root

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
                if target.prefix == "yt":                # never resolvable
                    self._akan("cannot splice a template into a string", node)
                pending = True                           # a chain: try later
            targets[ref] = target
        if pending:
            return None

        # Depth is the length of the dependency chain behind this string, not
        # a pass counter: passes depend on the order keys happen to appear,
        # and the same document must resolve the same way either way.
        depth = 1 + max((self._depth.get(id(t), 0) for t in targets.values()),
                        default=0)
        if depth > self.max_depth:
            self._akan(f"resolution exceeded the depth cap "
                       f"({self.max_depth}): this y-string sits at the end of "
                       f"a chain {depth} deep", node)

        to_bytes = node.prefix == "yb"
        pieces = [part if kind == "text"
                  else self._splice(targets[part], node, to_bytes)
                  for kind, part in node.parts]
        value = (b"" if to_bytes else "").join(pieces)
        self.rendered += len(value)
        if self.rendered > self.max_size:
            self._akan(f"document exceeds the rendered-size cap "
                       f"({self.max_size})", node)
        result = Scalar(node.line, node.col, "bytes" if to_bytes else "str",
                        value, prefix="b" if to_bytes else "")
        self._depth[id(result)] = depth
        return result

    # -- §5.5, the splice matrix --------------------------------------------
    def _splice(self, target: Node, at: YString, to_bytes: bool):
        if isinstance(target, (Mapping, Sequence, MultiMap)):
            self._akan("cannot interpolate a list, dict, or multimap into a "
                       "string", at)
        if not isinstance(target, Scalar):
            raise Yakamashiwa(f"unresolved {type(target).__name__} reached "
                              f"the splice step")
        if to_bytes:
            if target.type == "str":
                self._akan("cannot splice text into a byte string; there is "
                           "no implicit encode (spell the bytes you want)", at)
            if target.type == "bytes":
                return target.value
            return self._lexeme(target, at).encode("ascii")
        if target.type == "str":
            return target.value
        if target.type == "bytes":
            if target.prefix == "b64":
                return base64.b64encode(target.value).decode("ascii")
            self._akan("b-spelled bytes have no text form; respell as b64 to "
                       "splice into text", at)
        return self._lexeme(target, at)

    def _lexeme(self, target: Scalar, at: YString) -> str:
        """§5.4: a non-string scalar splices what the author wrote."""
        if not target.lexeme:
            raise Yakamashiwa(f"{target.type} scalar carries no lexeme")
        return target.lexeme

    # -- §5.2, the scope search ---------------------------------------------
    def _lookup(self, ref: str, site: _Site) -> Node:
        segs = ref.split(".")
        if segs[0] == "__ROOT__":
            current, rest = self.root, segs[1:]
        else:
            current, rest = self._search(segs[0], site), segs[1:]
        for seg in rest:
            current = self._child(current, seg, ref, site.node)
        return current

    def _search(self, name: str, site: _Site) -> Node:
        hits = []
        for level, (mapping, branch) in enumerate(site.chain):
            if level == 0 and name == branch:        # not the current key
                continue
            if name in mapping.by_key:
                hits.append((level, mapping))
        if not hits:
            self._akan(f"no value named {name!r} is in scope here",
                       site.node)

        level, mapping = hits[0]                     # nearest wins
        if len(hits) > 1:                            # shiran-on-shadow
            outer_level, outer_map = hits[-1]
            fix = (f"; write {{__ROOT__.{name}}} for the outer one"
                   if outer_level == len(site.chain) - 1 else "")
            self._shiran(
                f"{name!r} resolves to the nearer definition (line "
                f"{mapping.by_key[name].line}) and shadows another (line "
                f"{outer_map.by_key[name].line}){fix}", site.node)
        return mapping.by_key[name]

    def _child(self, node: Node, seg: str, ref: str, at: YString) -> Node:
        if isinstance(node, MultiMap):
            self._akan(f"{{{ref}}} cannot traverse into a multimap; its keys "
                       f"may repeat, so {seg!r} could name more than one "
                       f"value", at)
        if isinstance(node, Mapping):
            if seg not in node.by_key:
                self._akan(f"{{{ref}}}: there is no key {seg!r} here", at)
            return node.by_key[seg]
        self._akan(f"{{{ref}}}: cannot look up {seg!r}, because the value "
                   f"named before it is not a mapping", at)


def resolve(tree: Node, *, max_depth: int = MAX_DEPTH,
            max_size: int = MAX_SIZE, warn=None) -> Node:
    """Resolve every y/ry/yb literal in `tree`, in place. Returns the tree
    (which may itself be replaced, if the whole document was a y-string)."""
    return Resolver(tree, max_depth=max_depth, max_size=max_size,
                    warn=warn).resolve()
