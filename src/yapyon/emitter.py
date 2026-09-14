"""Stage 5 (optional): the AST back to yapyon source — a **normalizer**.

`emit(tree)` renders a *record* AST (SPEC §12) as yapyon text. It is a
normalizer, not a round-tripper: the value survives exactly, the spelling is
made canonical, and **comments do not survive** — comment-preserving
round-trip needs a design that does not exist yet.

**It works from the AST, never from loaded values.** That is the whole reason
this module can be correct: `version: 3.10` must come back as `3.10`, and by
the time `loads_record` has returned a `float` the source spelling is gone
(`3.10` and `3.1` are the same float). The parser keeps `Scalar.lexeme` for
numbers and keywords precisely so §5.4 can splice source text, and this
reuses it. Same for bytes, where `Scalar.prefix` says `b` or `b64` — a
value-based emitter would have to guess an encoding and would silently
respell every `b"..."` as base64.

**Canonical spelling** (agreed 2026-09-14, normative once §4 records it):

* double quotes always; the `\"\"\"` block form only when the value contains a
  newline (and only when that is safely expressible — see `_block_ok`)
* escape only what must be escaped — `\\`, `"`, and non-printables — leaving
  UTF-8 literal and readable
* numbers and keywords: the source lexeme, verbatim
* bytes: whichever of `b` / `b64` the document used
* block containers, except that an empty one has no block form and so is
  written flow (`[]`, `{}`)

Normalization therefore *loses spelling but never value*: `r"a\\nb"` comes
back as `"a\\\\nb"` and `'x'` as `"x"`. The property that matters is
`loads_record(emit(parse(s))) == loads_record(s)`, which the tests assert
over the whole corpus.
"""

from __future__ import annotations

import base64

from .parser import (AkanError, Mapping, MultiMap, Node, Pair, Scalar,
                     Sequence, YString, Yakamashiwa)

INDENT = "  "

# Escapes that read better than \xNN, and that §4.2 defines.
_SHORT = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def emit(node: Node, *, source: str | None = None) -> str:
    """Render a record AST as yapyon source text, newline-terminated.

    Raises `AkanError` at the offending prefix if the tree holds a y-family
    literal, matching §12.5's rule: the document is well-formed yapyon, it is
    simply not a record, and there is nothing to normalize.
    """
    lines = _lines(node, 0, source)
    return "".join(line + "\n" for line in lines)


# --------------------------------------------------------------------------- #
# Scalars
# --------------------------------------------------------------------------- #
def _escape_str(value: str, *, quote: str = '"') -> str:
    out = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == quote:
            out.append("\\" + quote)
        elif ch in _SHORT:
            out.append(_SHORT[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)                       # UTF-8 stays readable
    return "".join(out)


def _escape_bytes(value: bytes) -> str:
    """`b"..."` holds *source characters*, so every non-ASCII byte must be an
    escape — the literal-character rule the lexer enforces (and that a shared
    emit path once broke for `b"\\x89PNG"`)."""
    out = []
    for byte in value:
        ch = chr(byte)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch in _SHORT:
            out.append(_SHORT[ch])
        elif 0x20 <= byte < 0x7F:
            out.append(ch)
        else:
            out.append(f"\\x{byte:02x}")
    return "".join(out)


def _block_ok(value: str) -> bool:
    """Whether §4.1's block form can hold `value` without ambiguity.

    Every emitted content line is prefixed with the anchor, so nothing can
    outdent past it. What the form cannot take:

    * a whitespace-only-but-not-empty line — the anchor would swallow it or
      leave trailing spaces, and §4.1 exempts blank lines from the anchor
      test, so the two readings differ
    * `\"\"\"` in the content, or a trailing `"`, either of which would run
      into the closing delimiter
    """
    if "\n" not in value or '"""' in value or value.endswith('"'):
        return False
    return not any(line != "" and line.strip() == ""
                   for line in value.split("\n"))


def _block_lines(value: str, level: int) -> list[str]:
    """`key: \"\"\"` opened inline, content anchored one level deeper.

    The newline straight after the delimiter is dropped by §4.1, so the first
    content line is the first line of the value; `anchor` spaces come off each
    line after that, and prefixing every line with exactly `anchor` restores
    it. A value ending in a newline puts the closing delimiter on its own
    line, which is why the last element can be the bare anchor.
    """
    anchor = INDENT * (level + 1)
    body = [anchor + line if line else "" for line in value.split("\n")]
    # A value ending in a newline leaves an empty final segment. The closing
    # delimiter must still sit *at* the anchor -- at column 0 it outdents past
    # the string's own indentation, which §4.1 makes akan.
    body[-1] = (anchor + '"""') if body[-1] == "" else body[-1] + '"""'
    return ['"""'] + body


def _scalar(node: Scalar) -> str:
    if node.type in ("int", "float", "bool", "none"):
        # §5.4's lexeme, verbatim: `3.10` is not `3.1`.
        return node.lexeme or repr(node.value)
    if node.type == "bytes":
        if node.prefix == "b64":
            return 'b64"' + base64.b64encode(node.value).decode("ascii") + '"'
        return 'b"' + _escape_bytes(node.value) + '"'
    if node.type == "str":
        return '"' + _escape_str(node.value) + '"'
    raise Yakamashiwa(f"cannot emit scalar of type {node.type!r}")


# --------------------------------------------------------------------------- #
# Containers
# --------------------------------------------------------------------------- #
def _is_empty(node: Node) -> bool:
    return ((isinstance(node, Mapping) and not node.pairs)
            or (isinstance(node, Sequence) and not node.items)
            or (isinstance(node, MultiMap) and not node.entries))


def _inline(node: Node, level: int, source: str | None) -> list[str] | None:
    """The value as it appears after `key: ` or `- `, or None if it needs a
    block of its own. A list, because a block string spans lines."""
    if isinstance(node, YString):
        raise AkanError(
            f"a record's leaves must all be literals; a {node.prefix}-string "
            f"defers its value (load with yapyon.loads for the full form)",
            node.line, node.col, source)
    if isinstance(node, Scalar):
        if node.type == "str" and _block_ok(node.value):
            return _block_lines(node.value, level)
        return [_scalar(node)]
    if _is_empty(node):
        return ["[]" if isinstance(node, Sequence) else "{}"]
    return None


def _lines(node: Node, level: int, source: str | None) -> list[str]:
    pad = INDENT * level
    if isinstance(node, Mapping):
        return _pairs(node.pairs, pad, level, source, marker="")
    if isinstance(node, MultiMap):
        return _pairs(node.entries, pad, level, source, marker="+ ")
    if isinstance(node, Sequence):
        out = []
        for item in node.items:
            out.extend(_marked(item, pad, level, source, marker="- "))
        return out
    inline = _inline(node, level, source)
    if inline is None:
        raise Yakamashiwa(f"cannot emit node {type(node).__name__}")
    return [pad + inline[0]] + inline[1:]


def _pairs(pairs: list[Pair], pad: str, level: int, source: str | None,
           marker: str) -> list[str]:
    out = []
    for pair in pairs:
        inline = _inline(pair.value, level, source)
        head = f"{pad}{marker}{pair.key}:"
        if inline is None:                       # a block of its own
            out.append(head)
            # A `+ ` marker pushes its key to marker column + 2 (§2 anchors
            # the frame there), so a block under that key must clear the
            # key's column, not the multimap's own indentation.
            out.extend(_lines(pair.value, level + (2 if marker else 1),
                              source))
        else:
            out.append(f"{head} {inline[0]}")
            out.extend(inline[1:])
    return out


def _marked(item: Node, pad: str, level: int, source: str | None,
            marker: str) -> list[str]:
    """A `- ` item. A container opens on the marker line and its remaining
    lines align at marker column + 2, which is where §2 anchors the frame."""
    inline = _inline(item, level, source)
    if inline is not None:
        return [f"{pad}{marker}{inline[0]}"] + inline[1:]
    inner = _lines(item, level + 1, source)
    shift = len(pad) + len(marker)
    first = inner[0][len(INDENT) * (level + 1):]
    return [f"{pad}{marker}{first}"] + [" " * shift + line[len(INDENT) * (level + 1):]
                                        for line in inner[1:]]


# No `__main__` here on purpose: `python -m yapyon.record` is the one CLI that
# renders a record, and it runs the §12 token check as well. Two entry points
# reaching the same output by different routes is how the refusal position
# would come to disagree with `loads_record`'s.
