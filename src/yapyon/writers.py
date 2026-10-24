"""JSON, YAML, and TOML output, exactly — SPEC §14.

Each writer reads the **resolved AST**, not plain values: a lexeme decides
what a value needs beside it (`0xff` is 255 plus an `@_lexemes` entry; bytes
keep the spelling the author chose), and a value with none — a resolved
y-string, a call's result — takes its canonical form (§4.4). The resolver
hands a writer only a subtree with nothing pending and no template in it.

**Approximate, never refuse** (§5.1.2). Where a format cannot carry a value
directly the writer uses the format's own mechanisms first — JSON-LD shapes
and I-JSON in JSON, `%TAG` handles onto YAML's standard tags — so a reader
that knows §14 recovers the yapyon value and one that does not still gets
correct plain data. No marker carries yapyon's name.

**Layout is §14.1's**: a container that fits within 100 columns on its
line, by the pinned width table, is written on one line; otherwise one
member per line, two spaces deeper, outermost first. Which containers may
take a one-line form depends on the format.
"""

from __future__ import annotations

import base64
import json

from ._digits import decimal_text
from ._width import text_width
from .emitter import WIDTH, _escape_bytes
from .emitter import flat as _flat
from .parser import Mapping, MultiMap, Node, Scalar, Sequence

_I64 = (-(1 << 63), (1 << 63) - 1)
_RADIX_LETTERS = "xXoObBqQzZ"


# --------------------------------------------------------------------------- #
# What a node says about itself
# --------------------------------------------------------------------------- #
def _radix(node: Scalar) -> str:
    """The radix letter of a non-decimal integer's lexeme (`x o b q z`),
    or "" for a decimal one or a value with no lexeme."""
    text = node.lexeme.lstrip("+-")
    if len(text) > 1 and text[0] == "0" and text[1] in _RADIX_LETTERS:
        return text[1].lower()
    return ""


def _bytes_lexeme(node: Scalar) -> str:
    """Bytes as yapyon source: the lexeme, or `b"..."` with none (§4.4)."""
    return node.lexeme or 'b"' + _escape_bytes(node.value) + '"'


def _lexeme_body(lexeme: str) -> tuple[str, str]:
    """`hex'6869'` -> ("hex", "6869"); the text between the quotes."""
    i = 0
    while lexeme[i] not in "'\"":
        i += 1
    prefix, rest = lexeme[:i], lexeme[i:]
    quote = rest[:3] if rest[:3] in ('"""', "'''") else rest[0]
    return prefix, rest[len(quote):-len(quote)]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _float_text(value: float) -> str:
    """The shortest text that reads back as the same float (§14.3)."""
    return repr(value)


def _fits(line: str) -> bool:
    return text_width(line) <= WIDTH


# --------------------------------------------------------------------------- #
# JSON (§14.3)
# --------------------------------------------------------------------------- #
class _J:
    """A JSON value being laid out: `kind` is "obj", "arr", or "text"."""
    __slots__ = ("kind", "items")

    def __init__(self, kind, items):
        self.kind, self.items = kind, items


def _jtext(text: str) -> _J:
    return _J("text", text)


def _jstr(text: str) -> str:
    # §14.3's escapes are exactly what `json` writes with ensure_ascii off:
    # `"` and `\`, U+0000-U+001F as \b \f \n \r \t or lowercase \u00xx.
    return json.dumps(text, ensure_ascii=False)


def to_json(node: Node, *, lexemes: bool = True, warn=None) -> str:
    """JSON text for a resolved subtree (§14.3). No trailing newline."""
    dropped: list[str] = []
    tree = _JsonBuilder(lexemes, dropped).value(node, None, [])
    if dropped and lexemes and warn is not None:
        warn(f"JSON has no object to hold this {_what(node)}'s lexemes "
             f"({', '.join(dropped)}), so they are dropped; pass "
             f"lexemes=False if only the values were wanted (§14.3)")
    return "\n".join(_jlines(tree, 0, "", ""))


def _what(node: Node) -> str:
    return "list" if isinstance(node, Sequence) else "value"


def _lexeme_path(path) -> str:
    """§14.2: JSON Pointer segment escaping, without a leading slash."""
    return "/".join(part.replace("~", "~0").replace("/", "~1") for part in path)


class _JsonBuilder:
    def __init__(self, lexemes: bool, dropped: list):
        self.lexemes, self.dropped = lexemes, dropped

    def note(self, table, path, text):
        if table is None:
            self.dropped.append(text)
        else:
            table[_lexeme_path(path)] = text

    def value(self, node: Node, table, path) -> _J:
        if isinstance(node, Mapping):
            own: dict = {}
            members = [(pair.key, self.value(pair.value, own, [pair.key]))
                       for pair in node.pairs]
            return self.close(members, own)
        if isinstance(node, MultiMap):
            own = {}
            entries = [_J("obj", [(entry.key, self.value(
                           entry.value, own, ["entries", str(i)]))])
                       for i, entry in enumerate(node.entries)]
            members = [("@type", _jtext('"multimap"')),
                       ("entries", _J("obj", [("@list", _J("arr", entries))]))]
            return self.close(members, own)
        if isinstance(node, Sequence):
            return _J("arr", [self.value(item, table, path + [str(i)])
                              for i, item in enumerate(node.items)])
        return _jtext(self.scalar(node, table, path))

    def close(self, members, own) -> _J:
        if own and self.lexemes:
            members.append(("@_lexemes", _J("obj", [
                (key, _jtext(_jstr(text))) for key, text in own.items()])))
        return _J("obj", members)

    def scalar(self, node: Scalar, table, path) -> str:
        if node.type == "none":
            return "null"
        if node.type == "bool":
            return "true" if node.value else "false"
        if node.type == "int":
            if _radix(node):
                self.note(table, path, node.lexeme)
            return decimal_text(node.value)
        if node.type == "float":
            return _float_text(node.value)
        if node.type == "bytes":
            self.note(table, path, _bytes_lexeme(node))
            return _jstr(_b64url(node.value))
        return _jstr(node.value)


def _jone(tree: _J) -> str:
    if tree.kind == "text":
        return tree.items
    if tree.kind == "arr":
        return "[" + ", ".join(map(_jone, tree.items)) + "]"
    return "{" + ", ".join(f"{_jstr(k)}: {_jone(v)}" for k, v in tree.items) + "}"


def _jlines(tree: _J, indent: int, head: str, tail: str) -> list[str]:
    """`tree` on a line that begins `head` (indentation included) and ends
    `tail`: one line if it fits, else one member per line (§14.1)."""
    one = _jone(tree)
    if tree.kind == "text" or not tree.items or _fits(head + one + tail):
        return [head + one + tail]
    opening, closing = ("[", "]") if tree.kind == "arr" else ("{", "}")
    lines = [head + opening]
    pad = " " * (indent + 2)
    last = len(tree.items) - 1
    for i, item in enumerate(tree.items):
        comma = "," if i < last else ""
        if tree.kind == "arr":
            lines.extend(_jlines(item, indent + 2, pad, comma))
        else:
            key, value = item
            lines.extend(_jlines(value, indent + 2, f"{pad}{_jstr(key)}: ",
                                 comma))
    lines.append(" " * indent + closing + tail)
    return lines


# --------------------------------------------------------------------------- #
# YAML (§14.4)
# --------------------------------------------------------------------------- #
_YAML_PREFIX = "tag:yaml.org,2002:"

# Plain only when provably inert to every YAML 1.1 and 1.2 reader (§14.4):
# a conservative shape, and none of the words either version reads as a
# bool, a null, or a number. Over-quoting costs a reader nothing;
# under-quoting is the Norway problem.
_YAML_RESERVED = {
    "y", "n", "yes", "no", "true", "false", "on", "off", "null", "none",
    "nan", "inf", "infinity", "~",
}


def _yaml_plain_ok(text: str, flow: bool) -> bool:
    if not text or not (text[0].isascii() and (text[0].isalpha()
                                                or text[0] == "_")):
        return False
    allowed = "_.@/+-" + ("" if flow else ":")
    if not all(ch.isascii() and (ch.isalnum() or ch in allowed) for ch in text):
        return False
    if ": " in text or text.endswith(":") or text.lower() in _YAML_RESERVED:
        return False
    try:
        float(text)
    except ValueError:
        return True
    return False


def _ydq(text: str) -> str:
    """A YAML double-quoted scalar: JSON's escapes, plus the characters YAML
    counts as non-printable or as line breaks (C1 controls, NEL, U+2028,
    U+2029, U+FEFF), which JSON would leave as themselves."""
    out = []
    for ch in _jstr(text)[1:-1]:
        cp = ord(ch)
        if 0x7F <= cp <= 0x9F or cp in (0x2028, 0x2029, 0xFEFF, 0xFFFE,
                                        0xFFFF):
            out.append(f"\\u{cp:04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _ystr(text: str, flow: bool = False) -> str:
    return text if _yaml_plain_ok(text, flow) else _ydq(text)


def _yfloat(value: float) -> str:
    """JSON's float text, with `.0` inserted where the mantissa has no `.`:
    YAML 1.1 reads `1e+16` as a string (§14.4)."""
    text = _float_text(value)
    if "e" in text:
        mantissa, exponent = text.split("e")
        if "." not in mantissa:
            text = f"{mantissa}.0e{exponent}"
    return text


class _Yaml:
    def __init__(self):
        self.handles: list[str] = []

    def tag(self, handle: str, suffix: str) -> str:
        if handle not in self.handles:
            self.handles.append(handle)
        return f"!{handle}!{suffix}"

    # -- scalars ---------------------------------------------------------------
    def scalar(self, node: Scalar, flow: bool) -> str:
        if node.type == "none":
            return "null"
        if node.type == "bool":
            return "true" if node.value else "false"
        if node.type == "int":
            radix = _radix(node)
            if radix in ("x", "o", "b"):
                # PyYAML's int constructor knows only lowercase prefixes
                lexeme = node.lexeme
                sign = lexeme[0] if lexeme[0] in "+-" else ""
                body = lexeme[len(sign):]
                return self.tag(radix, "int") + f" {sign}0{body[1].lower()}{body[2:]}"
            if radix:
                return self.tag(radix, "int") + f" {decimal_text(node.value)}"
            return decimal_text(node.value)
        if node.type == "float":
            return _yfloat(node.value)
        if node.type == "bytes":
            if not node.lexeme:
                return f'!!binary "{base64.b64encode(node.value).decode()}"'
            prefix, body = _lexeme_body(node.lexeme)
            if prefix == "b64":
                return '!!binary "' + "".join(body.split()) + '"'
            return self.tag(prefix, "str") + " " + _ydq(body)
        return _ystr(node.value, flow)

    def empty(self, node: Node) -> str | None:
        if isinstance(node, Mapping) and not node.pairs:
            return "{}"
        if isinstance(node, Sequence) and not node.items:
            return "[]"
        if isinstance(node, MultiMap) and not node.entries:
            return self.tag("multimap", "pairs") + " []"
        return None

    def flow(self, node: Node) -> str:
        if isinstance(node, Sequence):
            return "[" + ", ".join(self.flow(item) for item in node.items) + "]"
        return self.scalar(node, flow=True)

    # -- blocks ----------------------------------------------------------------
    def root(self, node: Node) -> list[str]:
        if isinstance(node, Mapping) and node.pairs:
            return self.mapping(node, 0)
        if isinstance(node, MultiMap) and node.entries:
            return [self.tag("multimap", "pairs")] + self.entries(node, 0)
        if isinstance(node, Sequence) and node.items:
            if _flat(node):
                one = self.flow(node)
                if _fits(one):
                    return [one]
            return self.sequence(node, 0)
        empty = self.empty(node)
        return [empty if empty is not None else self.scalar(node, False)]

    def mapping(self, node: Mapping, indent: int) -> list[str]:
        out = []
        for pair in node.pairs:
            out.extend(self.pair(_ystr(pair.key), pair.value, indent))
        return out

    def pair(self, key: str, value: Node, indent: int) -> list[str]:
        head = " " * indent + key + ":"
        empty = self.empty(value)
        if empty is not None:
            return [f"{head} {empty}"]
        if isinstance(value, Mapping):
            return [head] + self.mapping(value, indent + 2)
        if isinstance(value, MultiMap):
            return [f"{head} {self.tag('multimap', 'pairs')}"] + \
                self.entries(value, indent + 2)
        if isinstance(value, Sequence):
            if _flat(value):
                one = f"{head} {self.flow(value)}"
                if _fits(one):
                    return [one]
            return [head] + self.sequence(value, indent + 2)
        return [f"{head} {self.scalar(value, False)}"]

    def entries(self, node: MultiMap, indent: int) -> list[str]:
        out = []
        for entry in node.entries:
            item = Mapping(entry.line, entry.col, [entry])
            out.extend(self.item(item, indent))
        return out

    def sequence(self, node: Sequence, indent: int) -> list[str]:
        out = []
        for item in node.items:
            out.extend(self.item(item, indent))
        return out

    def item(self, node: Node, indent: int) -> list[str]:
        dash = " " * indent + "- "
        empty = self.empty(node)
        if empty is not None:
            return [dash + empty]
        if isinstance(node, Mapping):
            lines = self.mapping(node, indent + 2)
            return [dash + lines[0][indent + 2:]] + lines[1:]
        if isinstance(node, MultiMap):
            return [dash + self.tag("multimap", "pairs")] + \
                self.entries(node, indent + 2)
        if isinstance(node, Sequence):
            if _flat(node):
                one = dash + self.flow(node)
                if _fits(one):
                    return [one]
            return [dash.rstrip()] + self.sequence(node, indent + 2)
        return [dash + self.scalar(node, False)]


def to_yaml(node: Node, *, warn=None) -> str:
    """Block-style YAML for a resolved subtree (§14.4), newline-terminated.
    Markers are `%TAG` handles onto YAML's standard tags, declared in order
    of first use, so an ordinary loader builds a standard type."""
    writer = _Yaml()
    body = writer.root(node)
    head = [f"%TAG !{h}! {_YAML_PREFIX}" for h in writer.handles]
    if head:
        head.append("---")
    return "\n".join(head + body) + "\n"


# --------------------------------------------------------------------------- #
# TOML (§14.5)
# --------------------------------------------------------------------------- #
def _tkey(key: str) -> str:
    """Bare when TOML allows it (ASCII letters, digits, `_`, `-`)."""
    if key and all(ch.isascii() and (ch.isalnum() or ch in "_-") for ch in key):
        return key
    return _tstr(key)


def _tstr(text: str) -> str:
    """A TOML basic string: `"` and `\\` escaped, and every control
    character TOML forbids raw (U+0000-U+001F but tab, and U+007F)."""
    short = {"\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r",
             '"': '\\"', "\\": "\\\\"}
    out = []
    for ch in text:
        if ch in short:
            out.append(short[ch])
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04X}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


class _T:
    """A TOML value being laid out: "arr" may break across lines; "text"
    (scalars and inline tables) never does."""
    __slots__ = ("kind", "items")

    def __init__(self, kind, items):
        self.kind, self.items = kind, items


def _tone(value: _T) -> str:
    if value.kind == "text":
        return value.items
    return "[" + ", ".join(map(_tone, value.items)) + "]"


def _tlines(value: _T, indent: int, head: str, tail: str) -> list[str]:
    one = _tone(value)
    if value.kind == "text" or not value.items or _fits(head + one + tail):
        return [head + one + tail]
    lines = [head + "["]
    pad = " " * (indent + 2)
    last = len(value.items) - 1
    for i, item in enumerate(value.items):
        lines.extend(_tlines(item, indent + 2, pad, "," if i < last else ""))
    lines.append(" " * indent + "]" + tail)
    return lines


class _Toml:
    def __init__(self, lexemes: bool):
        self.lexemes = lexemes
        self.out: list[str] = []

    # -- inline values -----------------------------------------------------------
    def inline(self, node: Node, table: dict, path: list) -> _T:
        """A value that is not a table of its own. `table` is the
        `@_lexemes` record of the nearest object (§14.2)."""
        if isinstance(node, Sequence):
            return _T("arr", [self.inline(item, table, path + [str(i)])
                              for i, item in enumerate(node.items)])
        if isinstance(node, Mapping):
            own: dict = {}
            members = [f"{_tkey(p.key)} = {_tone(self.inline(p.value, own, [p.key]))}"
                       for p in node.pairs if not self.omitted(p, own)]
            return _T("text", self.inline_table(members, own))
        if isinstance(node, MultiMap):
            own = {}
            entries = self.entries(node, own)
            members = ['"@type" = "multimap"', f"entries = {_tone(entries)}"]
            return _T("text", self.inline_table(members, own))
        return _T("text", self.scalar(node, table, path))

    def omitted(self, pair, own: dict) -> bool:
        """`None` in a table: the key is left out, and recorded (§14.5)."""
        if isinstance(pair.value, Scalar) and pair.value.type == "none":
            own[_lexeme_path([pair.key])] = "None"
            return True
        return False

    def inline_table(self, members: list, own: dict) -> str:
        if own and self.lexemes:
            members = members + ['"@_lexemes" = ' + self.lexeme_table(own)]
        return "{" + ", ".join(members) + "}" if members else "{}"

    def lexeme_table(self, own: dict) -> str:
        return "{" + ", ".join(f"{_tkey(k)} = {_tstr(v)}"
                               for k, v in own.items()) + "}"

    def entries(self, node: MultiMap, own: dict) -> _T:
        items = []
        for i, entry in enumerate(node.entries):
            path = ["entries", str(i)]
            if isinstance(entry.value, Scalar) and entry.value.type == "none":
                own[_lexeme_path(path)] = "None"
                items.append(_T("text", "{}"))
                continue
            value = _tone(self.inline(entry.value, own, path))
            items.append(_T("text", f"{{{_tkey(entry.key)} = {value}}}"))
        return _T("arr", items)

    def scalar(self, node: Scalar, table: dict, path: list) -> str:
        where = _lexeme_path(path)
        if node.type == "none":                  # in an array: a stand-in
            table[where] = "None"
            return '"None"'
        if node.type == "bool":
            return "true" if node.value else "false"
        if node.type == "int":
            if not _I64[0] <= node.value <= _I64[1]:
                table[where] = node.lexeme or decimal_text(node.value)
                return _tstr(decimal_text(node.value))
            if _radix(node):
                table[where] = node.lexeme
            return decimal_text(node.value)
        if node.type == "float":
            return _float_text(node.value)
        if node.type == "bytes":
            table[where] = _bytes_lexeme(node)
            return _tstr(_b64url(node.value))
        return _tstr(node.value)

    # -- tables ------------------------------------------------------------------
    def document(self, node: Node) -> str:
        if isinstance(node, MultiMap):
            own: dict = {}
            entries = self.entries(node, own)
            body = ['"@type" = "multimap"'] + _tlines(entries, 0, "entries = ", "")
            self.out.extend(body)
            self.lexeme_record(own, [])
        else:
            self.table(node, [], header=False)
        return "\n".join(self.out).strip("\n") + "\n"

    def table(self, node: Mapping, path: list, header: bool):
        mark = len(self.out)
        own: dict = {}
        later = []
        for pair in node.pairs:
            key, value = pair.key, pair.value
            if self.omitted(pair, own):
                continue
            if isinstance(value, Mapping):
                later.append(("table", key, value))
            elif isinstance(value, Sequence) and value.items and all(
                    isinstance(item, Mapping) for item in value.items):
                later.append(("array", key, value))
            elif isinstance(value, MultiMap):
                mine: dict = {}
                entries = self.entries(value, mine)
                self.out.append(f'{_tkey(key)}."@type" = "multimap"')
                self.out.extend(_tlines(entries, 0,
                                        f"{_tkey(key)}.entries = ", ""))
                if mine and self.lexemes:
                    # a table made by dotted keys never gets a header later
                    self.out.append(f'{_tkey(key)}."@_lexemes" = '
                                    + self.lexeme_table(mine))
            else:
                self.out.extend(_tlines(self.inline(value, own, [key]), 0,
                                        f"{_tkey(key)} = ", ""))
        self.lexeme_record(own, path)
        if header and (len(self.out) > mark or not later):
            # A table with nothing of its own needs no header when a
            # sub-table's already names it: `[[a.b]]` says `a` exists, and
            # `[a]` above it would name a second, redundant table. An empty
            # table keeps its header, or its key would be lost.
            self.out[mark:mark] = ([""] if mark else []) + \
                ["[" + ".".join(map(_tkey, path)) + "]"]
        for kind, key, value in later:
            if kind == "table":
                self.table(value, path + [key], header=True)
                continue
            for element in value.items:
                self.out.append("")
                self.out.append("[[" + ".".join(map(_tkey, path + [key])) + "]]")
                self.table(element, path + [key], header=False)

    def lexeme_record(self, own: dict, path: list):
        """§14.2's placement: one inline table if it fits, else a section."""
        if not own or not self.lexemes:
            return
        line = '"@_lexemes" = ' + self.lexeme_table(own)
        if _fits(line):
            self.out.append(line)
            return
        self.out.append("")
        self.out.append("[" + ".".join(map(_tkey, path + ["@_lexemes"])) + "]")
        self.out.extend(f"{_tkey(k)} = {_tstr(v)}" for k, v in own.items())


def to_toml(node: Node, *, lexemes: bool = True, warn=None) -> str:
    """TOML for a resolved mapping or multimap (§14.5), newline-terminated.
    It reads as the same tree as the JSON output, but for TOML's two limits:
    no null, and 64-bit integers."""
    return _Toml(lexemes).document(node)
