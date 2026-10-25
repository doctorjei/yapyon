"""Stage 5 (optional): the AST back to yapyon source — a **normalizer**.

`emit(tree)` renders a *record* AST (SPEC §12) as yapyon text. It is a
normalizer, not a round-tripper: every value and every spelling survives,
layout is the writer's, and **comments do not survive** — comment-preserving
round-trip needs a design that does not exist yet.

**It works from the AST, never from loaded values.** That is the whole reason
this module can be correct: `version: 3.10` must come back as `3.10`, and by
the time `loads_record` has returned a `float` the source spelling is gone
(`3.10` and `3.1` are the same float). Every literal and every key carries
its lexeme (SPEC §3), and SPEC §4.4 says a writer **must write it** — so
`'x'` stays `'x'`, `r"a\\nb"` stays raw, `0x1f` stays `0x1f`, and `ｎａｍｅ`
stays as written although its identity is `name`.

**Canonical form is for values with no lexeme** — a resolved y-string, a
call's result (§4.4):

* strings in double quotes; the `\"\"\"` block form only when the value
  contains a newline and that is safely expressible (`_block_ok`)
* escape only what must be escaped — `\\`, `"`, and non-printables — leaving
  UTF-8 literal and readable
* numbers and keywords as their text under §5.4
* bytes as `b"..."`

A `\"\"\"` lexeme is **re-indented as a whole**: its continuation lines sit
inside one token and dedent against their own first line (GRAMMAR §G4.4), so
shifting them all by one amount changes no value. Layout is the writer's;
the spelling is the author's.

Block containers throughout, except that an empty one has no block form and
so is written flow (`[]`, `{}`). The property that matters is
`loads_record(emit(parse(s))) == loads_record(s)`, which the tests assert
over the whole corpus, plus that a second emit changes nothing.
"""

from __future__ import annotations

from ._digits import decimal_text
from ._width import text_width
from .parser import (AkanError, Copy, Mapping, MultiMap, Node, Pair, Scalar,
                     Sequence, Slot, YString, Yakamashiwa, deferred_message)

INDENT = "  "
WIDTH = 100          # §14.1: a container fits if its line is this wide or less

# Escapes that read better than \xNN, and that GRAMMAR §G4.5 defines.
_SHORT = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def emit(node: Node, *, source: str | None = None) -> str:
    """Render a record — a `yapyon.Tree`, or a parsed node — as yapyon
    source text, newline-terminated.

    Raises `AkanError` at the offending prefix if the tree holds a y-family
    literal, matching §12.5's rule: the document is well-formed yapyon, it is
    simply not a record, and there is nothing to normalize.
    """
    root = getattr(node, "_root", None)          # a yapyon.Tree
    if root is not None:
        node, source = root, source if source is not None else node.source
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
    """Whether GRAMMAR §G4.4's block form can hold `value` without ambiguity.

    Every emitted content line is prefixed with the anchor, so nothing can
    outdent past it. What the form cannot take:

    * a whitespace-only-but-not-empty line — the anchor would swallow it or
      leave trailing spaces, and GRAMMAR §G4.4 exempts blank lines from the anchor
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

    The newline straight after the delimiter is dropped by GRAMMAR §G4.4, so the first
    content line is the first line of the value; `anchor` spaces come off each
    line after that, and prefixing every line with exactly `anchor` restores
    it. A value ending in a newline puts the closing delimiter on its own
    line, which is why the last element can be the bare anchor.
    """
    anchor = INDENT * (level + 1)
    body = [anchor + line if line else "" for line in value.split("\n")]
    # A value ending in a newline leaves an empty final segment. The closing
    # delimiter must still sit *at* the anchor -- at column 0 it outdents past
    # the string's own indentation, which GRAMMAR §G4.4 makes akan.
    body[-1] = (anchor + '"""') if body[-1] == "" else body[-1] + '"""'
    return ['"""'] + body


def _scalar(node: Scalar) -> str:
    """Canonical form (§4.4), for a scalar that has no lexeme."""
    if node.type == "int":                    # §3.1: never the host's limit
        return decimal_text(node.value)
    if node.type in ("float", "bool", "none"):
        return repr(node.value)
    if node.type == "bytes":
        return 'b"' + _escape_bytes(node.value) + '"'
    if node.type == "str":
        return '"' + _escape_str(node.value) + '"'
    raise Yakamashiwa(f"cannot emit scalar of type {node.type!r}")


def _lexeme_lines(lexeme: str, level: int) -> list[str]:
    """The author's spelling, laid out at `level`. Continuation lines of
    multiline literals/references shift together, preserving each string's
    content-relative anchor (GRAMMAR §G4.4). Whitespace-only lines are blank
    to the scanner, and stay blank."""
    first, *rest = lexeme.split("\n")
    if not rest:
        return [first]
    widths = [len(line) - len(line.lstrip(" ")) for line in rest if line.strip()]
    anchor = min(widths) if widths else 0
    pad = INDENT * (level + 1)
    return [first] + [pad + line[anchor:] if line.strip() else ""
                      for line in rest]


# --------------------------------------------------------------------------- #
# Containers
# --------------------------------------------------------------------------- #
def _empty(node: Node) -> str:
    """The flow spelling of an empty container: `[]`, `{}`, or `{+}` for a
    multimap, which has no other form when it holds nothing (GRAMMAR §G6)."""
    if isinstance(node, Sequence):
        return "[]"
    return "{+}" if isinstance(node, MultiMap) else "{}"


def _is_empty(node: Node) -> bool:
    return ((isinstance(node, Mapping) and not node.pairs)
            or (isinstance(node, Sequence) and not node.items)
            or (isinstance(node, MultiMap) and not node.entries))


def _inline(node: Node, level: int, source: str | None, *,
            unresolved: bool = False) -> list[str] | None:
    """The value as it appears after `key: ` or `- `, or None if it needs a
    block of its own. A list, because a block string spans lines."""
    from .parser import Expression
    if isinstance(node, Expression):
        if unresolved:
            from ._expressions import source as expression_source
            return _lexeme_lines(expression_source(node), level)
        raise AkanError(deferred_message("FOR", ""), node.line, node.col,
                        node.source or source)
    if isinstance(node, YString):
        if unresolved:
            if not node.lexeme:
                raise Yakamashiwa("an unresolved expression has no source lexeme")
            return _lexeme_lines(node.lexeme, level)
        raise AkanError(
            deferred_message("COPY" if isinstance(node, Copy) else "",
                             node.prefix),
            node.line, node.col, source)
    if isinstance(node, Slot):
        message = ("a slot must be attached to a dictionary key; it cannot "
                   "be written as a standalone value (GRAMMAR §G6)"
                   if unresolved else deferred_message("LABEL", ""))
        raise AkanError(message, node.line, node.col, node.source or source)
    if isinstance(node, Scalar):
        if node.lexeme:
            return _lexeme_lines(node.lexeme, level)
        if node.type == "str" and _block_ok(node.value):
            return _block_lines(node.value, level)
        return [_scalar(node)]
    if _is_empty(node):
        return [_empty(node)]
    return None


def flat(node: Node) -> bool:
    """Holds no mapping or multimap at any depth: §14.1's test for a
    sequence that may take a one-line form in YAML and yapyon."""
    if isinstance(node, (Mapping, MultiMap)):
        return False
    if isinstance(node, Sequence):
        return all(map(flat, node.items))
    return True


def _flow(node: Node, source: str | None, *, unresolved: bool = False) -> str | None:
    """A flat, non-empty sequence on one line, or None where it has no
    one-line form (a multi-line lexeme, a mapping somewhere inside)."""
    if not (isinstance(node, Sequence) and node.items and flat(node)):
        return None
    parts = []
    for item in node.items:
        if isinstance(item, Sequence):
            text = "[]" if not item.items else _flow(item, source, unresolved=unresolved)
        else:
            lines = _inline(item, 0, source, unresolved=unresolved)
            text = lines[0] if lines is not None and len(lines) == 1 else None
        if text is None:
            return None
        parts.append(text)
    return "[" + ", ".join(parts) + "]"


def _fits(line: str) -> bool:
    return text_width(line) <= WIDTH


def _lines(node: Node, level: int, source: str | None, *,
           unresolved: bool = False) -> list[str]:
    pad = INDENT * level
    from .parser import Expression
    if isinstance(node, Expression):
        inline = _inline(node, level, source, unresolved=unresolved)
        return [pad + inline[0]] + inline[1:]
    flow = _flow(node, source, unresolved=unresolved)
    if flow is not None and _fits(pad + flow):
        return [pad + flow]
    if _is_empty(node):
        # An empty container has no block spelling (§4.4), at the root as
        # anywhere else: with no lines at all, `{}` came back as an empty
        # document, which is akan.
        return [pad + _empty(node)]
    if isinstance(node, Mapping):
        return _pairs(node.pairs, pad, level, source, marker="", unresolved=unresolved)
    if isinstance(node, MultiMap):
        return _pairs(node.entries, pad, level, source, marker="+ ", unresolved=unresolved)
    if isinstance(node, Sequence):
        out = []
        for item in node.items:
            out.extend(_marked(item, pad, level, source, marker="- ", unresolved=unresolved))
        return out
    inline = _inline(node, level, source, unresolved=unresolved)
    if inline is None:
        raise Yakamashiwa(f"cannot emit node {type(node).__name__}")
    return [pad + inline[0]] + inline[1:]


def _pairs(pairs: list[Pair], pad: str, level: int, source: str | None,
           marker: str, *, unresolved: bool = False) -> list[str]:
    out = []
    for pair in pairs:
        value, label = pair.value, ""
        if unresolved and isinstance(value, Slot):
            label = value.lexeme or "<" + ".".join(value.label) + ">"
            value = value.layers[0]
        inline = _inline(value, level, source, unresolved=unresolved)
        if isinstance(pair.key, YString) and not unresolved:
            raise AkanError(deferred_message("YKEY", pair.key.prefix),
                            pair.line, pair.col, pair.source or source)
        spelling = pair.lexeme or (pair.key if pair.named else
                    _scalar(Scalar(pair.line, pair.col, "str", pair.key)))
        key_lines = _lexeme_lines(spelling, level + (1 if marker else 0))
        if len(key_lines) > 1:
            out.append(f"{pad}{marker}{key_lines[0]}")
            out.extend(key_lines[1:-1])
            head = key_lines[-1] + label + ":"
        else:
            head = f"{pad}{marker}{key_lines[0]}{label}:"
        flow = _flow(value, source, unresolved=unresolved)
        if flow is not None and _fits(f"{head} {flow}"):
            inline = [flow]
        if inline is None:                       # a block of its own
            out.append(head)
            # A `+ ` marker pushes its key to marker column + 2 (GRAMMAR §G3 anchors
            # the frame there), so a block under that key must clear the
            # key's column, not the multimap's own indentation.
            out.extend(_lines(value, level + (2 if marker else 1),
                              source, unresolved=unresolved))
        else:
            out.append(f"{head} {inline[0]}")
            out.extend(inline[1:])
    return out


def _marked(item: Node, pad: str, level: int, source: str | None,
            marker: str, *, unresolved: bool = False) -> list[str]:
    """A `- ` item. A container opens on the marker line and its remaining
    lines align at marker column + 2, which is where GRAMMAR §G3 anchors the frame."""
    inline = _inline(item, level, source, unresolved=unresolved)
    flow = _flow(item, source, unresolved=unresolved)
    if flow is not None and _fits(f"{pad}{marker}{flow}"):
        inline = [flow]
    if inline is not None:
        return [f"{pad}{marker}{inline[0]}"] + inline[1:]
    inner = _lines(item, level + 1, source, unresolved=unresolved)
    shift = len(pad) + len(marker)
    first = inner[0][len(INDENT) * (level + 1):]
    return [f"{pad}{marker}{first}"] + [" " * shift + line[len(INDENT) * (level + 1):]
                                        for line in inner[1:]]


# No `__main__` here on purpose: `python -m yapyon.record` is the one CLI that
# renders a record, and it runs the §12 token check as well. Two entry points
# reaching the same output by different routes is how the refusal position
# would come to disagree with `loads_record`'s.
