"""yapyon templates — v0.1 (SPEC §6)

A `yt"..."` literal produces a Template: literal string parts and named
holes, handed to the consumer unfilled. The document never fills it — the
hole names belong to whatever scope the consumer supplies, which is exactly
why `yt` is spelled in the y namespace rather than borrowed from Python's
`t` (law 6: an f/t string's meaning depends on an enclosing program, and a
data file has none).

Fill-time conversions are normative for conforming renderers (§6). Note that
they are *not* §5.4's lexeme rule: by fill time the lexeme is long gone, so a
float fills as its shortest round-trip decimal rather than as written.

Bytes are **akan** at fill, which is where a template parts company with a
document. The bridge law exists because a document author has no code to run,
so `b64"..."` must be spelled as a literal. A consumer is code: it can call
whichever encoder it means, and picking base64 on its behalf is silently
wrong for anyone who wanted hex or url-safe. Float stays canonical for the
opposite reason — shortest round-trip is the only faithful rendering of a
float, while bytes have many equally valid ones.
"""

from __future__ import annotations

from .lexer import AkanError, parse_ref
from .multimap import OrderedMultimap


class Template:
    """An unfilled yt literal.  `parts` alternates ("text", str) and
    ("hole", "a.b"), exactly as the lexer scanned it."""

    __slots__ = ("parts", "line", "col", "source")

    def __init__(self, parts, line: int = 0, col: int = 0,
                 source: str | None = None):
        self.parts = list(parts)
        self.line, self.col = line, col
        self.source = source          # where the yt literal was written, if known

    @property
    def holes(self) -> tuple:
        """Every hole reference, in order, with repeats kept."""
        return tuple(ref for kind, ref in self.parts if kind == "hole")

    def fill(self, values=None, /, **kwargs) -> str:
        """Render against a supplied scope.  Unbound holes are akan (§6)."""
        scope = dict(values or {})
        scope.update(kwargs)
        return "".join(
            part if kind == "text" else self._render(self._lookup(part, scope),
                                                     part)
            for kind, part in self.parts)

    # -- internals -----------------------------------------------------------
    def _akan(self, msg: str):
        raise AkanError(msg, self.line, self.col, self.source)

    def _lookup(self, ref: str, scope: dict):
        """Walk a parsed reference (§5.1) through the supplied scope.

        The same `parse_ref` the lexer validated with and the resolver
        traverses with — one grammar, three users, so `a.b` and `a["b"]`
        cannot come to mean different things here than in a document.
        """
        # One definition of __ROOT__: it anchors at the root of whatever
        # scope resolves the hole, which here *is* the supplied scope. So
        # {x} and {__ROOT__.x} take the same path and give the same akan —
        # no special case, and none of the drift a second one would invite.
        parsed = parse_ref(ref)
        steps = list(parsed.steps)
        current = scope
        if steps and steps[0][0] == "key":
            first = steps.pop(0)[1]
            if first not in current:
                self._akan(f"unbound hole {{{ref}}}: nothing named {first!r} "
                           f"was supplied")
            current = current[first]
        for step in steps:
            current = self._walk(current, step, ref, scope)
        return current

    def _walk(self, current, step, ref: str, scope: dict):
        kind, payload = step
        if kind == "ref":
            payload = self._subscript_key(payload, ref, scope)
            kind = "index" if isinstance(payload, int) else "key"
        if kind == "index":
            if isinstance(current, OrderedMultimap):
                self._akan(f"{{{ref}}}: index a multimap's key view, not the "
                           f"multimap — positional entry access is reserved")
            if isinstance(current, str) or not isinstance(current, (list,
                                                                    tuple)):
                self._akan(f"{{{ref}}}: cannot index {payload}, because the "
                           f"value named before it is not a list")
            if payload >= len(current):
                self._akan(f"{{{ref}}}: index {payload} is past the end of a "
                           f"list of {len(current)}")
            return current[payload]
        if isinstance(current, OrderedMultimap):
            # §7.1 by-key traversal is a list view, exactly as in a document.
            # `mm[k].values()`, not `mm.get(k)` — the latter hands back Entry
            # objects, which are the container's business and not the
            # document's.
            return list(current[payload].values())
        try:
            return current[payload]
        except (TypeError, IndexError):
            self._akan(f"{{{ref}}}: cannot look up {payload!r}, because the "
                       f"value named before it is not a mapping")
        except KeyError:
            self._akan(f"{{{ref}}}: there is no key {payload!r} here")

    def _subscript_key(self, inner, ref: str, scope: dict):
        """`[someref]` names a key; resolve it in the *supplied* scope."""
        key = self._lookup(inner.text, scope)
        if isinstance(key, bool) or not isinstance(key, (str, int)):
            self._akan(f"{{{ref}}}: the subscript {{{inner.text}}} must name "
                       f"a string or a number to use as a key")
        return key

    def _render(self, value, ref: str) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, bool):        # before int: bool subclasses int
            return "True" if value else "False"
        if value is None:
            return "None"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return repr(value)             # shortest round-trip (§6)
        if isinstance(value, (bytes, bytearray)):
            self._akan(f"cannot fill {{{ref}}} with bytes; name the encoding "
                       f"you want (base64, hex, url-safe) and pass the text — "
                       f"a consumer has code, so yapyon will not choose one")
        self._akan(f"cannot fill {{{ref}}} with a {type(value).__name__}; a "
                   f"template takes text, numbers, bools, or None")

    # -- niceties ------------------------------------------------------------
    def __eq__(self, other):
        return isinstance(other, Template) and self.parts == other.parts

    def __hash__(self):
        return hash(tuple(map(tuple, self.parts)))

    def __repr__(self):
        return f"Template({self.parts!r})"
