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

from .lexer import AkanError


class Template:
    """An unfilled yt literal.  `parts` alternates ("text", str) and
    ("hole", "a.b"), exactly as the lexer scanned it."""

    __slots__ = ("parts", "line", "col")

    def __init__(self, parts, line: int = 0, col: int = 0):
        self.parts = list(parts)
        self.line, self.col = line, col

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
        raise AkanError(msg, self.line, self.col)

    def _lookup(self, ref: str, scope: dict):
        segs = ref.split(".")
        if segs[0] == "__ROOT__":
            # One definition, no special case: __ROOT__ anchors at the root of
            # whatever scope resolves the hole — the document for a y-string,
            # the supplied scope here. Against a flat scope it degenerates to
            # an ordinary lookup, which is harmless.
            segs = segs[1:]
            if not segs:
                return scope
        if segs[0] not in scope:
            self._akan(f"unbound hole {{{ref}}}: nothing named {segs[0]!r} "
                       f"was supplied")
        current = scope[segs[0]]
        for seg in segs[1:]:
            try:
                current = current[seg]
            except (TypeError, IndexError):
                self._akan(f"{{{ref}}}: cannot look up {seg!r}, because the "
                           f"value named before it is not a mapping")
            except KeyError:
                self._akan(f"{{{ref}}}: there is no key {seg!r} here")
        return current

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
