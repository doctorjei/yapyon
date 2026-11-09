"""YAML surface recognition for already-valid literal Yapyon source.

This does not construct YAML values or resolve a schema. Quoting, plain-scalar
boundaries, and collection structure must be checked in YAML's own view: a
Yapyon byte/raw literal is a YAML plain scalar, not a YAML quoted scalar.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import re

from .lexer import AkanError


@dataclass
class _Token:
    kind: str
    start: int
    end: int
    line: int
    col: int


class _Reader:
    def __init__(self, text, source):
        self.text, self.source = text, source
        self.starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]
        self.pos, self.depth, self.i = 0, 0, 0
        self.tokens = []
        self.anchors = set()

    def fail(self, index, message):
        line = bisect_right(self.starts, index)
        raise AkanError("not yamlplus: invalid YAML syntax: " + message,
                        line, index - self.starts[line - 1], self.source)

    def emit(self, kind, start):
        line = bisect_right(self.starts, start)
        self.tokens.append(_Token(kind, start, self.pos, line,
                                  start - self.starts[line - 1]))

    def next_char(self, index):
        return self.text[index:index + 1]

    def separated(self, index):
        return self.next_char(index) in ("", " ", "\t", "\n")

    def scan(self):
        text = self.text
        while self.pos < len(text):
            ch, start = text[self.pos], self.pos
            if ch in " \t\n":
                self.pos += 1
                continue
            if ch == "#":
                if start and text[start - 1] not in " \t\n":
                    self.fail(start, "separate an inline comment from preceding tokens with whitespace")
                end = text.find("\n", self.pos)
                self.pos = len(text) if end < 0 else end
                continue
            if ch in "[{":
                self.depth += 1
                self.pos += 1
                self.emit(ch, start)
            elif ch in "]}," and self.depth:
                if ch != ",":
                    self.depth -= 1
                self.pos += 1
                self.emit(ch, start)
            elif (ch == ":" and (self.separated(start + 1) or self.depth
                                  or self.tokens and self.tokens[-1].kind == "quoted")
                  or ch in "-?" and self.separated(start + 1)):
                if ch == ":" and not self.depth and not self.separated(start + 1):
                    self.fail(start, "separate ':' from a block value with whitespace")
                self.pos += 1
                self.emit(ch, start)
            elif ch in "\"'":
                self.quoted(ch)
                self.emit("quoted", start)
            elif ch in "&*":
                self.pos += 1
                name_start = self.pos
                while self.next_char(self.pos) and (self.text[self.pos].isalnum() or self.text[self.pos] in "-_"):
                    self.pos += 1
                name = text[name_start:self.pos]
                if not name or self.next_char(self.pos) not in ("", " ", "\t", "\n", ",", "]", "}", ":", "?"):
                    self.fail(start, "invalid anchor or alias name")
                if ch == "&":
                    self.anchors.add(name)
                elif name not in self.anchors:
                    self.fail(start, "alias has no preceding anchor")
                self.emit("anchor" if ch == "&" else "alias", start)
            elif ch == "!":
                self.tag()
                self.emit("tag", start)
            elif ch in "|>" and not self.depth:
                self.block_scalar()
                self.emit("quoted", start)
            else:
                self.plain()
                if self.pos == start:
                    self.fail(start, "unexpected character")
                self.emit("plain", start)
        self.emit("eof", len(text))

    def quoted(self, quote):
        start = self.pos
        self.pos += 1
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            self.pos += 1
            if ch == quote:
                if quote == "'" and self.next_char(self.pos) == "'":
                    self.pos += 1
                    continue
                return
            if ch == "\\" and quote == '"':
                escaped = self.next_char(self.pos)
                if escaped in ("x", "u", "U"):
                    width = {"x": 2, "u": 4, "U": 8}[escaped]
                    digits = self.text[self.pos + 1:self.pos + 1 + width]
                    if len(digits) != width or any(c not in "0123456789abcdefABCDEF" for c in digits):
                        self.fail(self.pos - 1, "incomplete hexadecimal escape")
                    self.pos += width + 1
                elif escaped and escaped in '0abtnvfre "/\\N_LP\t\n':
                    self.pos += 1
                else:
                    self.fail(self.pos - 1, "unrecognized double-quoted escape; use a shared hexadecimal escape")
        self.fail(start, "unterminated quoted scalar")

    def tag(self):
        start = self.pos
        self.pos += 1
        if self.next_char(self.pos) == "<":
            end = self.text.find(">", self.pos + 1)
            if end < 0 or any(ch.isspace() for ch in self.text[self.pos + 1:end]):
                self.fail(start, "invalid verbatim tag")
            self.pos = end + 1
            return
        while self.next_char(self.pos) and self.text[self.pos] not in " \t\n,[]{}":
            ch = self.text[self.pos]
            if ch == "%":
                digits = self.text[self.pos + 1:self.pos + 3]
                if len(digits) != 2 or any(c not in "0123456789abcdefABCDEF" for c in digits):
                    self.fail(self.pos, "invalid tag URI escape")
                self.pos += 3
                continue
            if not (ch.isalnum() or ch in "-;/?:@&=+$_.!~*'()"):
                self.fail(self.pos, "invalid tag character")
            self.pos += 1
        tag = self.text[start:self.pos]
        if "!" in tag[1:] and not tag.startswith("!!"):
            self.fail(start, "tag handle has not been declared")

    def block_scalar(self):
        start = self.pos
        end = self.text.find("\n", start)
        end = len(self.text) if end < 0 else end
        header = self.text[start:end]
        if not re.fullmatch(r"[|>](?:[1-9][-+]?|[-+][1-9]?)?(?:[ \t]+(?:#.*)?)?", header):
            self.fail(start, "invalid block-scalar header")
        line = bisect_right(self.starts, start)
        line_text = self.text[self.starts[line - 1]:start]
        parent = len(line_text) - len(line_text.lstrip(" "))
        for i in range(len(self.tokens) - 1, 0, -1):
            if self.tokens[i].line != line:
                break
            if self.tokens[i].kind == ":":
                parent = self.tokens[i - 1].col
                break
        explicit = next((int(ch) for ch in header[:3] if ch in "123456789"), None)
        indent = parent + explicit if explicit is not None else None
        self.pos = min(end + 1, len(self.text))
        while self.pos < len(self.text):
            end = self.text.find("\n", self.pos)
            end = len(self.text) if end < 0 else end
            content = self.text[self.pos:end]
            width = len(content) - len(content.lstrip(" "))
            if content.strip(" "):
                if indent is None:
                    if width <= parent:
                        break
                    indent = width
                if width < indent:
                    break
            self.pos = min(end + 1, len(self.text))

    def properties(self):
        kinds = set()
        while self.peek().kind in ("tag", "anchor"):
            token = self.peek()
            if token.kind in kinds:
                self.fail(token.start, "duplicate node property")
            kinds.add(token.kind)
            self.i += 1
        return bool(kinds)

    def plain(self):
        start = self.pos
        if self.text[start] in ",]}|>%@`":
            self.fail(start, "this indicator cannot start a plain scalar")
        if self.depth and self.text[start] == "?":
            self.pos += 1
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            if ch == "\n" or self.depth and ch in ",[]{}?":
                break
            if ch == ":" and (self.separated(self.pos + 1) or
                               self.depth and self.next_char(self.pos + 1) in (",", "[", "]", "{", "}")):
                break
            if ch == "#" and (self.pos == start or self.text[self.pos - 1] in " \t"):
                break
            self.pos += 1
        while self.pos > start and self.text[self.pos - 1] in " \t":
            self.pos -= 1

    def peek(self):
        return self.tokens[self.i]

    def take(self, kind):
        if self.peek().kind == kind:
            self.i += 1
            return True
        return False

    def expect(self, kind):
        if not self.take(kind):
            self.fail(self.peek().start, f"expected {kind!r}")

    def flow_node(self, depth):
        if depth > 128:
            self.fail(self.peek().start, "flow nesting exceeds this implementation's ceiling of 128")
        had_properties = self.properties()
        start = self.peek()
        if had_properties and start.kind in (",", "]", "}"):
            return
        if had_properties and start.kind == "alias":
            self.fail(start.start, "an alias cannot carry node properties")
        if self.take("["):
            end, mapping = "]", False
        elif self.take("{"):
            end, mapping = "}", True
        else:
            if self.peek().kind not in ("quoted", "plain", "alias"):
                self.fail(start.start, "expected a flow value")
            self.i += 1
            if start.kind == "plain":
                while self.peek().kind == "plain" and self.peek().line > start.line:
                    start = self.peek()
                    self.i += 1
            return
        if self.take(end):
            return
        while True:
            if self.peek().kind in (",", end):
                self.fail(self.peek().start, "empty flow entry")
            explicit = self.take("?")
            if self.peek().kind == ":" and not explicit:
                self.fail(self.peek().start, "an empty flow key requires '?'")
            if self.peek().kind not in (":", ",", end):
                self.flow_node(depth + 1)
            if self.take(":"):
                if self.peek().kind not in (",", end):
                    self.flow_node(depth + 1)
            elif not mapping and self.peek().kind not in (",", end):
                self.fail(self.peek().start, "expected a flow separator")
            if self.take(end):
                return
            self.expect(",")
            if self.take(end):
                return

    def block_node(self, depth=0):
        if depth > 128:
            self.fail(self.peek().start, "block nesting exceeds this implementation's ceiling of 128")
        first = self.peek()
        indent = first.col
        if first.kind == "-":
            while self.peek().kind == "-" and self.peek().col == indent:
                marker = self.peek()
                self.i += 1
                if self.peek().kind != "eof" and (self.peek().line == marker.line or self.peek().col > indent):
                    self.block_node(depth + 1)
            return
        if (first.kind in ("plain", "quoted") and
                self.tokens[self.i + 1].kind == ":" and
                self.tokens[self.i + 1].line == first.line):
            while True:
                key = self.peek()
                if key.kind not in ("plain", "quoted") or key.col != indent:
                    break
                colon = self.tokens[self.i + 1]
                if colon.kind != ":" or colon.line != key.line:
                    break
                self.i += 2
                nxt = self.peek()
                if nxt.kind != "eof" and (nxt.line == colon.line or nxt.col > indent):
                    if nxt.line == colon.line and nxt.kind == "-":
                        self.fail(nxt.start, "a block sequence needs a new line after ':'")
                    if nxt.line == colon.line:
                        self.inline_node(indent, depth + 1)
                    else:
                        self.block_node(depth + 1)
            return
        self.inline_node(indent - 1, depth + 1)

    def inline_node(self, parent_indent, depth):
        had_properties = self.properties()
        first = self.peek()
        if had_properties and (first.kind == "eof" or first.col <= parent_indent):
            return
        if had_properties and first.kind == "alias":
            self.fail(first.start, "an alias cannot carry node properties")
        if first.kind in ("[", "{"):
            self.flow_node(depth)
            return
        if first.kind not in ("plain", "quoted", "alias"):
            self.fail(first.start, "expected a scalar or collection")
        self.i += 1
        if first.kind == "plain":
            while (self.peek().kind == "plain" and self.peek().line > first.line
                   and self.peek().col > parent_indent):
                if self.tokens[self.i + 1].kind == ":":
                    break
                first = self.peek()
                self.i += 1

    def check(self):
        self.scan()
        self.block_node()
        self.expect("eof")


def check_syntax(text, source=None):
    """Check YAML's surface view without loading or interpreting any data."""
    _Reader(text, source).check()
