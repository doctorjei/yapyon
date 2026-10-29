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

from dataclasses import dataclass

from ._digits import decimal_text
from ._width import text_width
from .parser import (AkanError, Comprehension, Copy, Expression, Mapping, Merge,
                     MultiMap, Node, Pair, Scalar, Sequence, Slot, YString,
                     Yakamashiwa, deferred_message)

INDENT = "  "
WIDTH = 100          # §14.1: a container fits if its line is this wide or less

# Escapes that read better than \xNN, and that GRAMMAR §G4.5 defines.
_SHORT = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


class _Limit:
    def __init__(self, maximum):
        self.maximum, self.used = maximum, 0

    def check(self, size):
        if size > self.maximum - self.used:
            raise ValueError(f"serialized UTF-8 exceeds max_size of "
                             f"{self.maximum} bytes")

    def length(self, text):
        self.check(len(text))
        size = 0
        for start in range(0, len(text), 4096):
            size += len(text[start:start + 4096].encode("utf-8"))
            self.check(size)
        return size

    def line(self, text):
        self.used += self.length(text) + 1
        self.check(0)


def _join(parts, limit=None):
    out, size = [], 0
    for part in parts:
        if isinstance(part, int):
            if limit is not None:
                limit.check(part)
            part = " " * part
        if limit is not None:
            size += limit.length(part)
            limit.check(size)
        out.append(part)
    return "".join(out)


def _pad(level, limit=None):
    size = len(INDENT) * level
    if limit is not None:
        limit.check(size)
    return INDENT * level


def _emit_prepared(node, maximum):
    limit = _Limit(maximum)
    return "".join(line + "\n" for line in _iter_lines(node, 0, None, limit=limit))


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
    node = _record_view(node, source)
    lines = _lines(node, 0, source)
    return "".join(line + "\n" for line in lines)


def _emit_data(node, *, source=None):
    from .parser import children

    node = _record_view(node, source)

    def consume(value):
        if isinstance(value, (Mapping, MultiMap)):
            for pair in value.pairs if isinstance(value, Mapping) else value.entries:
                pair.replace = False
        for child in children(value):
            consume(child)

    consume(node)
    return "".join(line + "\n" for line in _lines(node, 0, source))


def _record_view(node, source):
    import copy
    from .assembly import MergedMapping, project

    node = copy.deepcopy(node)

    def refuse_authored(value):
        from .parser import children
        if isinstance(value, Merge) and value.authored:
            raise AkanError(deferred_message("PIPE", ""), value.line,
                            value.col, value.source or source)
        nested = (value.layers if isinstance(value, MergedMapping) and value.layers
                  else children(value))
        for child in nested:
            refuse_authored(child)

    refuse_authored(node)

    def walk(value):
        if isinstance(value, Merge):
            if value.authored:
                raise AkanError(deferred_message("PIPE", ""), value.line,
                                value.col, value.source or source)
            view = project(value, collections=True)
            if view is value:
                raise AkanError(deferred_message("PIPE", ""), value.line,
                                value.col, value.source or source)
            return walk(view)
        if isinstance(value, MergedMapping):
            value.finish()
            if value.layers:
                for layer in value.layers:
                    walk(layer)
            value.pairs = value.visible_pairs()
        if isinstance(value, (Mapping, MultiMap)) and not isinstance(value, Expression):
            pairs = value.pairs if isinstance(value, Mapping) else value.entries
            for pair in pairs:
                pair.value = walk(pair.value)
        elif isinstance(value, Sequence):
            value.items = [walk(item) for item in value.items]
        return value

    return walk(node)


# --------------------------------------------------------------------------- #
# Scalars
# --------------------------------------------------------------------------- #
def _escaped(value, quote, *, binary=False):
    out = []
    for item in value:
        ch = chr(item) if binary else item
        if ch == "\\":
            part = "\\\\"
        elif ch == quote:
            part = "\\" + quote
        elif ch in _SHORT:
            part = _SHORT[ch]
        elif ord(ch) < 0x20 or ord(ch) == 0x7F or (binary and ord(ch) >= 0x7F):
            part = f"\\x{ord(ch):02x}"
        else:
            part = ch
        out.append(part)
        if len(out) == 1024:
            yield "".join(out)
            out.clear()
    if out:
        yield "".join(out)


def _escape_str(value: str, *, quote: str = '"', limit=None) -> str:
    return _join(_escaped(value, quote), limit)


def _escape_bytes(value: bytes, *, limit=None) -> str:
    """Bytes outside printable ASCII are source escapes, not literal characters."""
    return _join(_escaped(value, '"', binary=True), limit)


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
    start = 0
    while True:
        end = value.find("\n", start)
        line = value[start:] if end < 0 else value[start:end]
        if line and not line.strip():
            return False
        if end < 0:
            return True
        start = end + 1


def _block_lines(value: str, level: int, limit=None) -> list[str]:
    """`key: \"\"\"` opened inline, content anchored one level deeper.

    The newline straight after the delimiter is dropped by GRAMMAR §G4.4, so the first
    content line is the first line of the value; `anchor` spaces come off each
    line after that, and prefixing every line with exactly `anchor` restores
    it. A value ending in a newline puts the closing delimiter on its own
    line, which is why the last element can be the bare anchor.
    """
    anchor = _pad(level + 1, limit)
    body, size = ['"""'], 4
    start = 0
    while True:
        end = value.find("\n", start)
        last = end < 0
        text = value[start:] if last else value[start:end]
        line = _join((anchor, _escape_str(text, limit=limit)), limit) if text else ""
        if last:
            line = _join((line or anchor, '"""'), limit)
        if limit is not None:
            size += limit.length(line) + 1
            limit.check(size)
        body.append(line)
        if last:
            return body
        start = end + 1


def _scalar(node: Scalar, limit=None) -> str:
    """Canonical form (§4.4), for a scalar that has no lexeme."""
    if node.type == "int":                    # §3.1: never the host's limit
        return decimal_text(node.value)
    if node.type in ("float", "bool", "none"):
        return repr(node.value)
    if node.type == "bytes":
        return _join(('b"', _escape_bytes(node.value, limit=limit), '"'), limit)
    if node.type == "str":
        return _join(('"', _escape_str(node.value, limit=limit), '"'), limit)
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
            unresolved: bool = False, limit=None) -> list[str] | None:
    """The value as it appears after `key: ` or `- `, or None if it needs a
    block of its own. A list, because a block string spans lines."""
    if isinstance(node, (Merge, Comprehension)) and unresolved:
        return None
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
            return _block_lines(node.value, level, limit)
        return [_scalar(node, limit)]
    if _is_empty(node):
        return [_empty(node)]
    return None


def flat(node: Node) -> bool:
    """§14.1's sequence test, without consuming the host recursion stack."""
    pending = [iter((node,))]
    while pending:
        try:
            value = next(pending[-1])
        except StopIteration:
            pending.pop()
            continue
        if isinstance(value, (Mapping, MultiMap)):
            return False
        if isinstance(value, Sequence):
            pending.append(iter(value.items))
    return True


def _flow(node: Node, source: str | None, *, unresolved=False, limit=None):
    if not isinstance(node, Sequence) or not node.items:
        return None
    parts, width, size = [], 0, 0
    pending = [("value", node)]
    while pending:
        kind, value = pending.pop()
        if kind == "items":
            iterator, first = value
            try:
                child = next(iterator)
            except StopIteration:
                text = "]"
            else:
                pending.append(("items", (iterator, False)))
                pending.append(("value", child))
                text = "" if first else ", "
        elif isinstance(value, Sequence):
            text = "["
            pending.append(("items", (iter(value.items), True)))
        elif isinstance(value, (Mapping, MultiMap)):
            return None
        else:
            lines = _inline(value, 0, source, unresolved=unresolved, limit=limit)
            if lines is None or len(lines) != 1:
                return None
            text = lines[0]
        width += text_width(text)
        if width > WIDTH:
            return None
        if limit is not None:
            size += limit.length(text)
            if size > limit.maximum - limit.used:
                return None
        parts.append(text)
    return _join(parts, limit)


def _fits(line: str) -> bool:
    return text_width(line) <= WIDTH


@dataclass
class _At:
    node: Node
    level: int
    marker: object = None


class _Marker:
    def __init__(self, pad, marker, level):
        self.column = len(pad) if isinstance(pad, str) else pad
        self.marker = marker
        self.base, self.first = len(INDENT) * (level + 1), True
        self.parent = None


def _marked_line(line, markers, limit):
    if markers is None:
        return line
    if limit is not None:
        limit.check(markers.base)
    prefix = [" "] * markers.base
    here = markers
    while here is not None:
        if here.first:
            prefix[here.column:here.column + len(here.marker)] = here.marker
            here.first = False
        here = here.parent
    return _join(("".join(prefix), line[markers.base:]), limit)


def _iter_lines(node, level, source, *, unresolved=False, limit=None):
    pending = [(iter(_plan_lines(node, level, source, unresolved, limit)), None)]
    while pending:
        iterator, markers = pending[-1]
        try:
            event = next(iterator)
        except StopIteration:
            pending.pop()
            continue
        if isinstance(event, _At):
            nested = markers
            if event.marker is not None:
                event.marker.parent = markers
                nested = event.marker
            pending.append((iter(_plan_lines(event.node, event.level, source,
                                             unresolved, limit)), nested))
            continue
        event = _marked_line(event, markers, limit)
        if limit is not None:
            limit.line(event)
        yield event


def _lines(node: Node, level: int, source: str | None, *, unresolved=False):
    return list(_iter_lines(node, level, source, unresolved=unresolved))


def _plan_lines(node, level, source, unresolved, limit):
    pad = _pad(level, limit) if unresolved else len(INDENT) * level
    if unresolved and isinstance(node, Merge):
        from ._expressions import source as expression_source
        operands, value = [], node
        while isinstance(value, Merge):
            operands.append(value.args[1])
            value = value.args[0]
        operands.append(value)
        for index, operand in enumerate(reversed(operands)):
            if index:
                yield _join((pad, "|"), limit)
            if index and isinstance(operand, Merge):
                lines = _lexeme_lines(expression_source(operand), level)
                yield _join((pad, lines[0]), limit)
                yield from lines[1:]
            else:
                yield _At(operand, level)
        return
    if unresolved and isinstance(node, Comprehension):
        from ._expressions import source as expression_source
        iterable, body, predicate, key = node.args
        if node.kind == "list":
            yield from _marked_plan(body, pad, level, source, "- ", unresolved, limit)
        else:
            head = pad + ("+ " if node.kind == "multimap" else "") + expression_source(key)
            head += ":=" if getattr(node, "replace", False) else ":"
            inline = _inline(body, level, source, unresolved=True, limit=limit)
            if inline is None:
                yield head
                yield _At(body, level + (2 if node.kind == "multimap" else 1))
            else:
                yield head + " " + inline[0]
                yield from inline[1:]
        yield pad + "for " + ", ".join(getattr(node, "binding_lexemes", node.names)) + " in " + expression_source(iterable)
        if predicate is not None:
            yield pad + "if " + expression_source(predicate)
        return
    if isinstance(node, Expression):
        inline = _inline(node, level, source, unresolved=unresolved, limit=limit)
        yield _join((pad, inline[0]), limit)
        yield from inline[1:]
        return
    flow = _flow(node, source, unresolved=unresolved, limit=limit)
    if flow is not None and _fits(_join((pad, flow), limit)):
        yield _join((pad, flow), limit)
    elif _is_empty(node):
        yield _join((pad, _empty(node)), limit)
    elif isinstance(node, (Mapping, MultiMap)):
        pairs = node.pairs if isinstance(node, Mapping) else node.entries
        marker = "" if isinstance(node, Mapping) else "+ "
        yield from _pair_plan(pairs, pad, level, source, marker, unresolved, limit)
    elif isinstance(node, Sequence):
        for item in node.items:
            yield from _marked_plan(item, pad, level, source, "- ", unresolved, limit)
    else:
        inline = _inline(node, level, source, unresolved=unresolved, limit=limit)
        if inline is None:
            raise Yakamashiwa(f"cannot emit node {type(node).__name__}")
        yield _join((pad, inline[0]), limit)
        yield from inline[1:]


def _pair_plan(pairs, pad, level, source, marker, unresolved, limit):
    for pair in pairs:
        value, label = pair.value, ""
        if unresolved and isinstance(value, Slot):
            label = value.lexeme or "<" + ".".join(value.label) + ">"
            value = value.layers[0]
        inline = _inline(value, level, source, unresolved=unresolved, limit=limit)
        if isinstance(pair.key, YString) and not unresolved:
            raise AkanError(deferred_message("YKEY", pair.key.prefix),
                            pair.line, pair.col, pair.source or source)
        spelling = pair.lexeme or (pair.key if pair.named else
                    _scalar(Scalar(pair.line, pair.col, "str", pair.key), limit))
        key_lines = _lexeme_lines(spelling, level + (1 if marker else 0))
        separator = ":=" if pair.replace else ":"
        if len(key_lines) > 1:
            yield _join((pad, marker, key_lines[0]), limit)
            yield from key_lines[1:-1]
            head = _join((key_lines[-1], label, separator), limit)
        else:
            head = _join((pad, marker, key_lines[0], label, separator), limit)
        flow = _flow(value, source, unresolved=unresolved, limit=limit)
        if flow is not None and _fits(_join((head, " ", flow), limit)):
            inline = [flow]
        if inline is None:
            yield head
            yield _At(value, level + (2 if marker else 1))
        else:
            yield _join((head, " ", inline[0]), limit)
            yield from inline[1:]


def _marked_plan(item, pad, level, source, marker, unresolved, limit):
    inline = _inline(item, level, source, unresolved=unresolved, limit=limit)
    flow = _flow(item, source, unresolved=unresolved, limit=limit)
    if flow is not None and _fits(_join((pad, marker, flow), limit)):
        inline = [flow]
    if inline is not None:
        yield _join((pad, marker, inline[0]), limit)
        yield from inline[1:]
    else:
        yield _At(item, level + 1, _Marker(pad, marker, level))


# No `__main__` here on purpose: `python -m yapyon.record` is the one CLI that
# renders a record, and it runs the §12 token check as well. Two entry points
# reaching the same output by different routes is how the refusal position
# would come to disagree with `loads_record`'s.
