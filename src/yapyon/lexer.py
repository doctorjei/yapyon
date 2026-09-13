"""yapyon reference lexer — v0.1

YAMLちゃうで。やぴょんやぴょん。

All context-sensitivity is quarantined here, in exactly two pieces of state:
an indent stack (which also carries dash frames) and a bracket depth. The
parser downstream sees a plain context-free token stream.

Design decisions implemented (from the design session):
  * Indentation: spaces only; a tab in indentation is akan.
  * Frames: "- " (sequence item) and "+ " (multimap entry) at line-content
    start emit DASH/PLUS INDENT, anchored at the marker's column + 2.  They
    stack and interleave: "- - x", "- + a: 1".
  * Inside [ ] or { }: newlines and indentation are suppressed entirely
    (Python implicit line joining); commas are the parser's business.
  * Strings: single-quoted, double-quoted, and triple-double-quoted
    (dedent anchored at the opening delimiter's column; blank lines exempt;
    closing may not sit shallower than the anchor).
  * Prefixes (lowercase, canonical spellings only):
        b, b64          — bytes spellings
        r, rb           — raw (backslash is literal); rb = raw bytes
        y, yb, yt, ry   — the y-family (holes live; {{ }} escapes)
    Unknown or non-canonical prefixes (F, BR, yr, ...) are akan by name.
  * Holes: strict braces. Every "{" opens a well-formed hole or is "{{";
    every lone "}" is akan. Hole = NAME ("." NAME)*, __ROOT__ allowed as
    first segment only; other dunder segments are reserved (akan).
  * Numbers: Python literals (0x/0o/0b, underscores, floats, exponents),
    optional leading sign. No inf/nan spellings.
  * Keywords: True / False / None. Any other bare word is a NAME token
    (legal as a key; the parser akans it in value position).
  * Escapes: Python's table minus \\N{...}; unknown escapes are akan
    (stricter than Python, by design).

Diagnostics: AkanError ("akan: ..."), warnings collect as "shiran: ..."
strings, internal invariant failures raise Yakamashiwa.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #
class AkanError(Exception):
    """A yapyon syntax error.  あかん。

    `source` names where the text came from, when the caller knows. A loader
    that parses several fragments and merges them — which is the whole point
    of exposing `parse`/`resolve`/`build` separately — otherwise reports a
    line and column into an unidentifiable fragment.

    With a source the message takes the `file:line:col:` form editors and
    compilers already understand; without one it is unchanged, so nothing
    that reads the old wording breaks.
    """

    def __init__(self, msg: str, line: int, col: int, source: str | None = None):
        self.msg, self.line, self.col, self.source = msg, line, col, source
        where = (f"line {line}, col {col}" if source is None
                 else f"{source}:{line}:{col}")
        super().__init__(f"akan: {where}: {msg}")


class Yakamashiwa(Exception):
    """Internal lexer invariant violated — a bug in yapyon, not your file."""


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
# kinds: NEWLINE INDENT DEDENT DASH NAME KEYWORD INT FLOAT STRING BYTES
#        YSTR YBSTR YTSTR COLON COMMA LBRACKET RBRACKET LBRACE RBRACE EOF
@dataclass
class Token:
    kind: str
    value: object = None
    line: int = 0
    col: int = 0
    prefix: str = ""          # string prefix as written: "" r b rb b64 y yb yt ry
    lexeme: str = ""          # source spelling of numbers and keywords (§5.4)
    parts: list = field(default_factory=list)  # y-family: [("text", x)|("hole", "a.b")]

    def __repr__(self):
        v = "" if self.value is None else f" {self.value!r}"
        return f"<{self.kind}{v} @{self.line}:{self.col}>"


STRING_PREFIXES = {"b", "b64", "r", "rb", "y", "yb", "yt", "ry"}
RAW_PREFIXES = {"r", "rb", "ry"}
BYTES_PREFIXES = {"b", "rb", "yb"}          # b64 handled separately
Y_PREFIXES = {"y", "yb", "yt", "ry"}
KEYWORDS = {"True": True, "False": False, "None": None}

_TOKEN_KIND_FOR_PREFIX = {
    "": "STRING", "r": "STRING",
    "b": "BYTES", "b64": "BYTES", "rb": "BYTES",
    "y": "YSTR", "ry": "YSTR", "yb": "YBSTR", "yt": "YTSTR",
}

_PREFIX_HINTS = {
    "f": "yapyon has no f-strings; use y for document splicing",
    "t": "yeeted; use yt",
    "u": "just remove it (all yapyon strings are Unicode)",
    "br": "canonical order is rb",
    "yr": "canonical order is ry",
    "fb": "bytes and templates don't combine; use yb",
    "bf": "bytes and templates don't combine; use yb",
    "yb64": "reserved for a future version",
    "ytb": "reserved for a future version",
}

_ESCAPES = {                                 # Python's table minus \N{...}
    "\n": "", "\\": "\\", "'": "'", '"': '"',
    "a": "\a", "b": "\b", "f": "\f", "n": "\n",
    "r": "\r", "t": "\t", "v": "\v",
}


def _digit(ch: str) -> bool:
    """Number literals are ASCII (SPEC §3).  `str.isdigit()` is also True
    for '٣' (U+0663) and '²', which belong to §7's identifier rules or to
    nothing at all — routing them to the number lexer only produces a
    'malformed number' where the mistake was a name.  False at EOF, where
    `_peek` returns ""."""
    return ch.isdigit() and ch.isascii()


DOLLAR_HINT = (" — if the `$` was meant as an environment variable, yapyon "
               "does not expand them; do that after loading")
"""Hedged on purpose (SPEC §5.1, and the `$VAR` decision behind it).

`$` is an ordinary character with no meaning in yapyon, so we cannot know
whether the author meant a variable or wrote a literal dollar. The hint says
"if", never diagnoses, and never changes the outcome — only the wording.
"After loading" rather than "pre-process", because the pre-parse text
substitution three projects reach for is the injection-prone path.
"""


def bad_segment_hint(seg: str) -> str:
    """The clause to append when a hole segment is not an identifier.

    Earned, not automatic: the regex-quantifier hint used to fire on *every*
    non-identifier hole, so `{$HOME}` was told about doubled braces, which
    has nothing to do with what was attempted.
    """
    if seg and all(ch.isdigit() or ch == "," for ch in seg):
        return " (a regex quantifier needs doubled braces: {{n,m}})"
    if seg.startswith("$"):
        return DOLLAR_HINT
    return ""


def is_dunder(name: str) -> bool:
    """True for names the __dunder__ namespace reserves for yapyon itself.

    **One predicate, two rules** (SPEC §5.1 and §7): a hole segment spelled
    this way names one of yapyon's own built-ins — only `__ROOT__` in v0.1 —
    and a *key* spelled this way is akan, so no document can define a name it
    could never address. The parser imports this rather than repeating the
    test, because two rules that must agree will drift when written twice.

    `__` and `___` count. Reserving a little more than `__x__` costs nothing,
    and widening later is compatible where narrowing is not.
    """
    return name.startswith("__") and name.endswith("__")


def _id_continue(ch: str) -> bool:
    """True for XID_Continue (SPEC §7).  ``("a" + ch).isidentifier()`` is
    exactly that test, which keeps the Unicode tables in `str`.  The explicit
    emptiness check matters: ``"a" + "" == "a"`` *is* an identifier, so at EOF
    this would otherwise answer True forever."""
    return bool(ch) and ("a" + ch).isidentifier()


# --------------------------------------------------------------------------- #
# Lexer
# --------------------------------------------------------------------------- #
class Lexer:
    def __init__(self, text: str, *, source: str | None = None):
        self.text = text
        self.source = source                  # a name for diagnostics, if known
        self.pos = 0
        self.line = 1
        self.col = 0                          # 0-based column
        self.indents: list[int] = [0]         # indent anchors (incl. dash frames)
        self.depth = 0                        # bracket nesting depth
        self.tokens: list[Token] = []
        self.warnings: list[str] = []         # shiran: ...

    # -- character helpers ---------------------------------------------------
    def _peek(self, n: int = 0) -> str:
        i = self.pos + n
        return self.text[i] if i < len(self.text) else ""

    def _advance(self, n: int = 1) -> str:
        out = self.text[self.pos:self.pos + n]
        for ch in out:
            if ch == "\n":
                self.line += 1
                self.col = 0
            else:
                self.col += 1
        self.pos += n
        return out

    def _emit(self, kind: str, value=None, line=None, col=None, **kw):
        self.tokens.append(Token(kind, value,
                                 self.line if line is None else line,
                                 self.col if col is None else col, **kw))

    def _akan(self, msg: str, line=None, col=None):
        raise AkanError(msg, self.line if line is None else line,
                        self.col if col is None else col, self.source)

    # -- top level -----------------------------------------------------------
    def tokenize(self) -> list[Token]:
        at_line_start = True
        while self.pos < len(self.text):
            if at_line_start and self.depth == 0:
                if self._handle_line_start():
                    continue                   # blank/comment line consumed
                at_line_start = False
            ch = self._peek()
            if ch == "\n":
                if self.depth == 0:
                    self._emit("NEWLINE")
                    at_line_start = True
                self._advance()                # inside brackets: soft, dropped
            elif ch and ch in " \t":
                self._advance()                # interior whitespace
            elif ch == "#":
                while self._peek() and self._peek() != "\n":
                    self._advance()
            else:
                self._lex_token()
        # EOF housekeeping: close the last logical line, then all frames.
        if self.depth != 0:
            self._akan("unclosed bracket at end of file")
        if self.tokens and self.tokens[-1].kind not in ("NEWLINE", "DEDENT"):
            self._emit("NEWLINE")
        while len(self.indents) > 1:
            self.indents.pop()
            self._emit("DEDENT")
        self._emit("EOF")
        return self.tokens

    # -- line starts: indentation + dash frames ------------------------------
    def _handle_line_start(self) -> bool:
        """Measure indentation; emit INDENT/DEDENT/DASH.  True if the line
        was blank or comment-only (fully consumed, caller should loop)."""
        start = self.pos
        width = 0
        while self._peek() and self._peek() in " \t":
            if self._peek() == "\t":
                self._akan("tab in indentation (spaces only)")
            self._advance()
            width += 1
        nxt = self._peek()
        if nxt in ("", "\n"):                  # blank line: no tokens at all
            if nxt:
                self._advance()
            return True
        if nxt == "#":                         # comment-only line
            while self._peek() and self._peek() != "\n":
                self._advance()
            if self._peek():
                self._advance()
            return True

        top = self.indents[-1]
        if width > top:
            self.indents.append(width)
            self._emit("INDENT", col=width)
        else:
            while width < self.indents[-1]:
                self.indents.pop()
                self._emit("DEDENT", col=width)
            if width != self.indents[-1]:
                self._akan(f"indent {width} matches no open block "
                           f"(open: {self.indents})", col=width)

        # Frame markers at content start: "- " opens a sequence item, "+ " a
        # multimap entry (or bare at EOL).  Both stack and interleave.
        while self._peek() in ("-", "+") and self._peek(1) in (" ", "\n", ""):
            marker, marker_col = self._peek(), self.col
            self._emit("DASH" if marker == "-" else "PLUS")
            self._advance()                    # the marker
            if self._peek() == " ":
                self._advance()
            anchor = marker_col + 2
            if anchor <= self.indents[-1]:
                raise Yakamashiwa("frame anchor not deeper than stack top")
            self.indents.append(anchor)
            self._emit("INDENT", col=anchor)
        return False

    # -- ordinary tokens -----------------------------------------------------
    def _lex_token(self):
        ch = self._peek()
        line, col = self.line, self.col

        single = {":": "COLON", ",": "COMMA",
                  "[": "LBRACKET", "]": "RBRACKET",
                  "{": "LBRACE", "}": "RBRACE"}
        if ch in single:
            if ch in "[{":
                self.depth += 1
            elif ch in "]}":
                if self.depth == 0:
                    self._akan(f"unmatched {ch!r}")
                self.depth -= 1
            self._emit(single[ch], ch)
            self._advance()
            return

        if ch in "'\"":
            self._lex_string("", line, col)
            return

        if _digit(ch) or (ch in "+-." and _digit(self._peek(1))) \
                or (ch in "+-" and self._peek(1) == "." and _digit(self._peek(2))):
            self._lex_number(line, col)
            return

        if ch.isidentifier():                  # identifier, keyword, or prefix
            name = self._scan_identifier()
            if self._peek() in ("'", '"'):
                if name not in STRING_PREFIXES:
                    hint = _PREFIX_HINTS.get(
                        name, "use one of: " + ", ".join(sorted(STRING_PREFIXES)))
                    self._akan(f"unknown string prefix {name!r}; {hint}",
                               line, col)
                self._lex_string(name, line, col)
            elif name in KEYWORDS:
                self._emit("KEYWORD", KEYWORDS[name], line, col, lexeme=name)
            else:
                self._emit("NAME", name, line, col)
            return

        for reserved in ("---", "..."):           # SPEC §8, reserved tokens
            if self.text.startswith(reserved, self.pos):
                self._akan(f"{reserved!r} is reserved and has no meaning in "
                           f"v0.1; yapyon is one document per file")
        if ch in "-+" and self._peek(1) in (" ", "\n", ""):
            self._akan(f"{ch!r} opens a block frame only at the start of a "
                       f"line's content")
        if _id_continue(ch):        # §7: legal inside a name, just not first
            self._akan(f"{ch!r} cannot start a name, though it may appear "
                       f"inside one (SPEC §7: names are Unicode identifiers)")
        if ch.isalnum():            # word-like, but no identifier admits it
            self._akan(f"{ch!r} cannot appear in a name (SPEC §7: names are "
                       f"Unicode identifiers, UAX #31)")
        self._akan(f"unexpected character {ch!r}")

    def _scan_identifier(self) -> str:
        """Scan one identifier (SPEC §7): an XID_Start character or '_',
        then XID_Continue characters.

        This is deliberately the same rule `_scan_hole` applies to its
        segments, so every key is addressable from a hole.  ``("a" + ch)``
        `.isidentifier()` is exactly the XID_Continue test, which keeps the
        Unicode tables in `str` rather than here.

        The explicit EOF guard is load-bearing: `_peek` returns "" at EOF and
        ``"a" + "" == "a"`` *is* an identifier, so without it the loop would
        not terminate."""
        if not self._peek().isidentifier():
            raise Yakamashiwa("_scan_identifier called off an identifier")
        out = [self._advance()]
        while _id_continue(self._peek()):
            out.append(self._advance())
        return "".join(out)

    # -- numbers -------------------------------------------------------------
    def _lex_number(self, line, col):
        start = self.pos
        if self._peek() and self._peek() in "+-":
            self._advance()
        is_float = False
        if self._peek() == "0" and self._peek(1) in "xXoObB":
            self._advance(2)
            while self._peek().isalnum() or self._peek() == "_":
                self._advance()
        else:
            while self._peek().isdigit() or self._peek() == "_":
                self._advance()
            if self._peek() == ".":
                is_float = True
                self._advance()
                while self._peek().isdigit() or self._peek() == "_":
                    self._advance()
            if self._peek() and self._peek() in "eE" and (self._peek(1).isdigit()
                                         or (self._peek(1) in "+-"
                                             and self._peek(2).isdigit())):
                is_float = True
                self._advance()
                if self._peek() and self._peek() in "+-":
                    self._advance()
                while self._peek().isdigit():
                    self._advance()
        lexeme = self.text[start:self.pos]
        try:                                   # Python's own rules judge validity
            import ast
            value = ast.literal_eval(lexeme)
        except (ValueError, SyntaxError):
            self._akan(f"malformed number {lexeme!r}", line, col)
        if isinstance(value, float) and not is_float:
            raise Yakamashiwa("number classified inconsistently")
        # The lexeme rides along: y-strings splice what the author wrote (§5.4).
        self._emit("FLOAT" if is_float else "INT", value, line, col, lexeme=lexeme)

    # -- strings -------------------------------------------------------------
    def _lex_string(self, prefix: str, line: int, col: int):
        quote = self._peek()
        # Anchor = the column where the literal *starts*, prefix included, so
        # y"""...""" aligns with its block just as """...""" does.
        triple = self._peek(1) == quote and self._peek(2) == quote
        self._advance(3 if triple else 1)
        raw_chars, raw_pos = self._scan_string_body(quote, triple, line, col)

        is_raw = prefix in RAW_PREFIXES
        is_bytes = prefix in BYTES_PREFIXES

        if prefix in Y_PREFIXES:
            # Structure first, escapes second: each text chunk is decoded on
            # its own, which is also why a yb-string needs no round trip
            # through latin-1 to keep its bytes.
            parts = []
            for chunk in self._scan_holes(raw_chars, raw_pos, is_raw,
                                          line, col):
                if chunk[0] == "hole":
                    parts.append(("hole", chunk[1]))
                    continue
                _, text, text_pos = chunk
                parts.append(("text", text if is_raw else
                              self._process_escapes(text, text_pos, is_bytes,
                                                    line, col)[0]))
            empty = b"" if is_bytes else ""
            value = empty.join(part for kind, part in parts if kind == "text")
            self._emit(_TOKEN_KIND_FOR_PREFIX[prefix], value, line, col,
                       prefix=prefix, parts=parts)
            return

        if prefix == "b64":
            value = self._decode_b64(raw_chars, line, col)
        elif is_raw:
            if is_bytes:
                for index, ch in enumerate(raw_chars):
                    if ord(ch) > 127:
                        self._akan("non-ASCII character in bytes literal",
                                   *raw_pos[index])
                value = raw_chars.encode("ascii")
            else:
                value = raw_chars
        else:
            value = self._process_escapes(raw_chars, raw_pos, is_bytes,
                                          line, col)[0]
        self._emit(_TOKEN_KIND_FOR_PREFIX[prefix], value, line, col,
                   prefix=prefix)

    def _scan_string_body(self, quote, triple, line, col):
        """Scan a string body, dedenting block strings (SPEC 4.1).

        The dedent anchor is the indentation of the first non-blank
        continuation line, so an inline opening after a key and an own-line
        opening both behave as they look.  A newline immediately after the opening
        delimiter is dropped.  Blank lines are exempt and set no anchor.
        Single pass, no lookahead: consume the leading spaces, then decide.

        Returns the body and a parallel list of source (line, col) positions,
        one per character, so that a later akan can point at the character
        that caused it rather than at the quote that opened the literal.
        """
        out, pos = [], []
        closer = quote * (3 if triple else 1)
        anchor = None          # discovered at the first content continuation line
        pristine = True        # nothing emitted yet -> a newline here is dropped
        while True:
            if self.pos >= len(self.text):
                self._akan("unterminated string", line, col)
            if self.text.startswith(closer, self.pos):
                if triple and anchor is not None and self.col < anchor:
                    self._akan(f"closing delimiter outdents past the string's "
                               f"indentation (col {self.col} < {anchor})")
                self._advance(len(closer))
                return "".join(out), pos
            ch = self._peek()
            if ch == "\n":
                if not triple:
                    self._akan("newline in single-line string", line, col)
                here = (self.line, self.col)
                self._advance()
                if not pristine:
                    out.append("\n")
                    pos.append(here)
                pristine = False
                width = 0
                while self._peek() == " ":
                    self._advance()
                    width += 1
                if self._peek() == "\n" or self.pos >= len(self.text):
                    continue                      # blank line: exempt
                if self.text.startswith(closer, self.pos):
                    continue                      # closing line: checked above
                if anchor is None:
                    anchor = width                # first content line sets it
                elif width < anchor:
                    self._akan(f"line outdents past the string's indentation "
                               f"(needs {anchor} leading spaces, found {width})")
                else:
                    keep = width - anchor         # indentation past the anchor
                    out.append(" " * keep)        # is content, and it is here:
                    pos.extend((self.line, anchor + k) for k in range(keep))
                continue
            pos.append((self.line, self.col))
            out.append(self._advance())
            pristine = False

    def _process_escapes(self, s: str, pos: list, is_bytes: bool,
                         line: int, col: int):
        """Apply the escape table, carrying source positions through.

        An escape's output character takes the position of its backslash, so
        a later akan points at the escape rather than at the whole literal.
        Returns (value, positions)."""
        out, out_pos = [], []          # out holds code points

        def at(index):                 # source position of s[index]
            return pos[index] if index < len(pos) else (line, col)

        def emit(codepoint, index, literal=False):
            if is_bytes:
                if literal and codepoint > 127:   # `b"é"`: spell it \xHH
                    self._akan("non-ASCII character in bytes literal",
                               *at(index))
                if codepoint > 255:               # but `b"\x89"` is the point
                    self._akan(f"escape value {codepoint} is outside the byte "
                               f"range 0-255", *at(index))
            out.append(codepoint)
            out_pos.append(at(index))

        i = 0
        while i < len(s):
            if s[i] != "\\":
                emit(ord(s[i]), i, literal=True)
                i += 1
                continue
            start = i                  # the backslash owns the position
            i += 1
            if i >= len(s):
                self._akan("dangling backslash in string", *at(start))
            e = s[i]
            if e in _ESCAPES:
                for c in _ESCAPES[e]:
                    emit(ord(c), start)
                i += 1
            elif e == "x":
                hexpart = s[i + 1:i + 3]
                if len(hexpart) < 2 or any(c not in "0123456789abcdefABCDEF"
                                           for c in hexpart):
                    self._akan(r"malformed \x escape", *at(start))
                emit(int(hexpart, 16), start)
                i += 3
            elif e in "01234567":
                j = i
                while j < len(s) and j - i < 3 and s[j] in "01234567":
                    j += 1
                emit(int(s[i:j], 8), start)
                i = j
            elif e in "uU" and not is_bytes:
                width = 4 if e == "u" else 8
                hexpart = s[i + 1:i + 1 + width]
                if len(hexpart) < width or any(
                        c not in "0123456789abcdefABCDEF" for c in hexpart):
                    self._akan(rf"malformed \{e} escape", *at(start))
                codepoint = int(hexpart, 16)
                if 0xD800 <= codepoint <= 0xDFFF:      # SPEC §4.2
                    self._akan(f"\\{e} escape names the surrogate "
                               f"U+{codepoint:04X}; yapyon strings are "
                               f"Unicode scalar values (write the character "
                               f"itself, e.g. \\U0001F600)", *at(start))
                if codepoint > 0x10FFFF:
                    self._akan(rf"malformed \{e} escape", *at(start))
                emit(codepoint, start)
                i += 1 + width
            else:
                self._akan(f"unknown escape \\{e} "
                           f"(yapyon escapes are Python's minus \\N)",
                           *at(start))
        if is_bytes:
            return bytes(out), out_pos
        return "".join(chr(c) for c in out), out_pos

    def _decode_b64(self, s: str, line: int, col: int) -> bytes:
        cleaned = "".join(s.split())           # permit interior whitespace
        try:
            return base64.b64decode(cleaned, validate=True)
        except (ValueError, base64.binascii.Error):
            self._akan("invalid base64 content", line, col)

    # -- y-family hole scanning ----------------------------------------------
    def _scan_holes(self, s: str, pos: list, is_raw: bool,
                    line: int, col: int) -> list:
        """Split a raw string body into text chunks and holes.

        Holes are recognised **before** escapes decode (SPEC §5.1), so an
        escape that produces a brace is content and never structure — the
        layering Python uses for f-strings, where `f"\\x7bname\\x7d"` is the
        six characters `{name}`.  Text chunks come back raw, for the caller
        to escape-process in place.

        Returns [("text", raw_chunk, positions) | ("hole", name)].
        """
        chunks, buf, buf_pos, i = [], [], [], 0

        def at(index):                 # source position of s[index]
            return pos[index] if index < len(pos) else (line, col)

        def keep(index, char=None):
            buf.append(s[index] if char is None else char)
            buf_pos.append(at(index))

        def flush():
            if buf:
                chunks.append(("text", "".join(buf), list(buf_pos)))
                buf.clear()
                buf_pos.clear()

        while i < len(s):
            ch = s[i]
            if not is_raw and ch == "\\":
                # An escape never produces structure; step over it whole, so
                # that `\\{x}` opens a hole and `\{` does not.
                nxt = s[i + 1:i + 2]
                if nxt in ("{", "}"):
                    self._akan(f"backslash never escapes a brace; write "
                               f"'{nxt * 2}' for a literal one", *at(i))
                keep(i)
                if nxt:
                    keep(i + 1)
                i += 2
                continue
            if ch == "{":
                if s[i + 1:i + 2] == "{":
                    keep(i, "{")
                    i += 2
                    continue
                end = s.find("}", i + 1)
                if end < 0:
                    self._akan("unclosed hole '{' (write '{{' for a literal "
                               "brace)", *at(i))
                name = s[i + 1:end].strip()
                self._check_hole_name(name, *at(i))
                flush()
                chunks.append(("hole", name))
                i = end + 1
                continue
            if ch == "}":
                if s[i + 1:i + 2] == "}":
                    keep(i, "}")
                    i += 2
                    continue
                self._akan("lone '}' (write '}}' for a literal brace)", *at(i))
            keep(i)
            i += 1
        flush()
        return chunks

    def _check_hole_name(self, name: str, line: int, col: int):
        if not name:
            self._akan("empty hole '{}'", line, col)
        if ":" in name or "!" in name:            # SPEC §5.1, reserved in §9
            self._akan("format specs and conversions are reserved; a hole "
                       "names a value and does nothing else", line, col)
        segs = name.split(".")
        for idx, seg in enumerate(segs):
            if seg == "__ROOT__":
                if idx != 0:
                    self._akan("__ROOT__ is only valid as the first segment",
                               line, col)
                continue
            if is_dunder(seg):
                self._akan(f"reserved name {seg!r} in hole "
                           f"(only __ROOT__ is defined)", line, col)
            if not seg.isidentifier():
                self._akan(f"holes name document values; {seg!r} is not an "
                           f"identifier{bad_segment_hint(seg)}", line, col)
            if seg in KEYWORDS:
                self._akan(f"{seg!r} cannot be a hole name", line, col)


def tokenize(text: str, *, source: str | None = None) -> list[Token]:
    return Lexer(text, source=source).tokenize()


if __name__ == "__main__":
    import sys
    src = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    try:
        for tok in tokenize(src):
            print(tok)
    except AkanError as e:
        print(e)
        sys.exit(1)
