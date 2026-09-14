"""yapyon templates — SPEC §6.

**A `yt` literal is a y-string that is not joined.** Its holes resolve against
the document at parse time by §5.2's ordinary rules, exactly as `y`'s do; the
consumer receives the literal text parts and the resolved values separately
and does its own rendering.

    y  : yt  ::  f-string : t-string

The point is *who escapes, and with what knowledge*. A joined string has lost
which bytes the author wrote and which came from the data, and no care
downstream can recover it:

    user_input: "; rm -rf /"
    cmd: y"echo {user_input}"      -> 'echo ; rm -rf /'    structure gone

Parts keep them separable until a consumer that knows the destination — shell,
registry, SQL, HTML — decides how each value is made safe. Same concern as the
`$VAR` ruling, which argues that pre-parse text substitution *is* injection,
one layer up.

**Carrying is unconstrained; rendering is not.** A hole may carry any value a
document can hold, containers and b-spelled bytes included, because yapyon
does not render it — the consumer that wanted hex rather than base64 can have
hex. §5.5 still governs `render()`, which is the *canonical* joining, and
refuses exactly what a `y` would have refused.

**`render()` is explicit, and there is no `__str__` that joins.** The moment a
convenient implicit rendering exists, people reach for it and the whole
property evaporates — PEP 750 declines to provide one for the same reason. It
exists here because it is also the definition of correctness: rendering a
`yt`'s parts must reproduce what the equivalent `y` produces, which is what
"an unjoined y-string" means, and it is asserted over the corpus.

*(Before 2026-09-14 a `yt` was unresolved and filled later from a mapping the
consumer supplied — `string.Template.substitute`, under a name that pointed at
PEP 750. That model was never argued in canon and its only cited consumer had
been ruled out of scope. `DESIGN_RATIONALE.md` has the history.)*
"""

from __future__ import annotations

from .lexer import AkanError


class Hole:
    """One resolved hole of a template (§5.1's `{...}`).

    * `ref`    — the reference as written, `"mind.dialects[p]"`. The analogue
      of PEP 750's `Interpolation.expression`, and likewise kept because the
      spelling is data: diagnostics and tooling want what the author typed.
    * `value`  — what it resolved to, typed. Any value a document can hold.
    * `lexeme` — the document's spelling of that value, for numbers and
      keywords; `""` for strings and containers, whose value *is* the content.
      Without it `3.10` would reach a consumer as the float `3.1` and could
      never be rendered back faithfully (§5.4).
    * `text`   — the §5.5 canonical rendering, or `None` where §5.5 refuses;
      `why` then says so. Precomputed by the resolver so that the matrix has
      one implementation rather than two.
    """

    __slots__ = ("ref", "value", "lexeme", "text", "why")

    def __init__(self, ref: str, value, lexeme: str = "",
                 text: str | None = None, why: str = ""):
        self.ref, self.value, self.lexeme = ref, value, lexeme
        self.text, self.why = text, why

    def __eq__(self, other):
        return (isinstance(other, Hole) and self.ref == other.ref
                and self.value == other.value and self.lexeme == other.lexeme)

    def __hash__(self):
        return hash((self.ref, self.lexeme))

    def __repr__(self):
        return f"Hole({self.ref!r}, {self.value!r})"


class Template:
    """A resolved `yt` literal: text parts and holes, unjoined.

    `parts` alternates `str` and `Hole`, **totally** — it begins and ends with
    a `str`, and an empty one sits between adjacent holes. So a consumer can
    walk it without special-casing a leading, trailing or doubled hole, and
    `len(strings) == len(holes) + 1` always. PEP 750 does the same, and it is
    worth copying: it removes a whole class of consumer bug.
    """

    __slots__ = ("parts", "line", "col", "source")

    def __init__(self, parts, line: int = 0, col: int = 0,
                 source: str | None = None):
        self.parts = tuple(_normalise(parts))
        self.line, self.col = line, col
        self.source = source          # where the yt literal was written

    # -- the three views -----------------------------------------------------
    @property
    def strings(self) -> tuple:
        """The literal text parts, in order. One more than there are holes."""
        return tuple(p for p in self.parts if isinstance(p, str))

    @property
    def holes(self) -> tuple:
        """Every hole, in order, with repeats kept."""
        return tuple(p for p in self.parts if isinstance(p, Hole))

    @property
    def values(self) -> tuple:
        """What each hole resolved to, in order."""
        return tuple(hole.value for hole in self.holes)

    def __iter__(self):
        """Alternating `str` and `Hole` — what a processing function walks."""
        return iter(self.parts)

    # -- canonical rendering (§5.5) -----------------------------------------
    def render(self) -> str:
        """Join canonically: exactly what the equivalent `y` would produce.

        Explicit by design. A consumer that knows its destination should be
        escaping the values itself; this is for the case that genuinely wants
        the plain string, and for saying what "an unjoined y-string" means.
        """
        out = []
        for part in self.parts:
            if isinstance(part, str):
                out.append(part)
            elif part.text is None:
                raise AkanError(part.why, self.line, self.col, self.source)
            else:
                out.append(part.text)
        return "".join(out)

    # -- niceties ------------------------------------------------------------
    def __eq__(self, other):
        return isinstance(other, Template) and self.parts == other.parts

    def __hash__(self):
        return hash(self.parts)

    def __repr__(self):
        return f"Template({list(self.parts)!r})"


def _normalise(parts) -> list:
    """Force the total alternation: str, Hole, str, Hole, ... str."""
    out: list = []
    for part in parts:
        if isinstance(part, Hole):
            if not out or isinstance(out[-1], Hole):
                out.append("")
            out.append(part)
        elif out and isinstance(out[-1], str):
            out[-1] += part
        else:
            out.append(part)
    if not out or isinstance(out[-1], Hole):
        out.append("")
    return out
