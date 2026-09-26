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
    every lone "}" is akan. `a.b` is sugar for `a["b"]` — the bracket is
    the general form and its content yields a key (quoted literal, integer
    index, or a reference whose value is the key). The dunder namespace is
    yapyon's: __ROOT__ and __PARENT__ lead a reference, __KEY__ and the three
    __AS_X__() serializers end one, and every other dunder is akan.
    `parse_ref` is the one implementation of that grammar (GRAMMAR §G5); the
    lexer validates with it and the resolver and templates traverse with it.
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
from bisect import bisect_right
from dataclasses import dataclass, field
from unicodedata import decomposition as _decomposition
from unicodedata import normalize as _normalize

from ._xid import UNICODE_VERSION, XID_CONTINUE, XID_IGNORED, XID_START
from unicodedata import category as _category, name as _uname


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
    parts: list = field(default_factory=list)  # y-family: [("text", x)|("hole", ref_src)]

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
    for '٣' (U+0663) and '²', which belong to GRAMMAR §G4.1's identifier rules or to
    nothing at all — routing them to the number lexer only produces a
    'malformed number' where the mistake was a name.  False at EOF, where
    `_peek` returns ""."""
    return ch.isdigit() and ch.isascii()


class RefError(ValueError):
    """A malformed hole reference, position-free.

    `parse_ref` knows the grammar but not where in the document the text sat,
    so it raises this and the caller re-raises an `AkanError` at the hole's
    line and column (law 7).
    """


class Ref:
    """A parsed hole reference.

    **The grammar is GRAMMAR §G5 and is not restated here.** A copy lived in
    this docstring until 2026-09-15 and had gone stale twice over: it
    generated no serializer call and no relative anchor, so it described a
    language narrower than the one `parse_ref` accepts. Cite the grammar;
    `tools/check_ref_grammar.py` keeps the document and this parser in step,
    and `tests/test_ref_grammar.py` runs it.

    `a.b` is sugar for `a["b"]`: the bracket is the general form and its
    content yields a key. So `steps` is a flat list of what to do next, and
    a dotted segment and a quoted key produce the *same* step kind — the
    equivalence is real rather than asserted.

        ("key",   str)   a mapping key, however it was spelled
        ("index", int)   a list position; brackets only, since 0 is no
                         identifier
        ("ref",   Ref)   a key named by another reference, resolved in the
                         scope of the y-string, not of the node indexed

    `text` is the source spelling, kept so diagnostics and `Template.holes`
    can show what the author actually wrote.
    """

    __slots__ = ("root", "steps", "text", "shirans", "parents", "key",
                 "serializer")

    def __init__(self, root: bool, steps: list, text: str, shirans=(),
                 parents: int = 0, key: bool = False, serializer: str = ""):
        self.root, self.steps, self.text = root, list(steps), text
        self.shirans: list[str] = list(shirans)   # legal, but worth a word
        self.parents = parents      # §5.1.1: how many __PARENT__ hops, 0 if none
        self.key = key              # §5.1.1: ends in __KEY__, naming a position
        self.serializer = serializer   # §5.1.2: a SERIALIZER_NAMES member, or ""

    def __eq__(self, other):
        return (isinstance(other, Ref) and self.root == other.root
                and self.steps == other.steps
                and self.parents == other.parents and self.key == other.key)

    def __hash__(self):
        return hash((self.root, self.parents, self.key,
                     tuple(map(str, self.steps))))

    def __repr__(self):
        return f"Ref({self.text!r})"


def _ref_int(token: str) -> int:
    """A bracket index: decimal digits, optionally after `-`. A negative
    index counts from the end, as in Python — `xs[-1]` is the last element,
    and `xs[-0]` is `xs[0]` because `-0` is the integer 0."""
    digits = token[1:] if token.startswith("-") else token
    if not digits.isdigit() or not digits.isascii():
        raise RefError(f"{token!r} is neither an identifier, a quoted key, "
                       f"nor a number")
    return int(token)


def _split_subscript(text: str, i: int) -> tuple[str, int]:
    """The content of the bracket opening at `text[i]`, and the index past
    its `]`. Tracks nesting and quotes, so `a[b[c]]` and `a["]"]` both close
    where they should."""
    depth, j, quote = 0, i, ""
    while j < len(text):
        ch = text[j]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    raise RefError("unclosed '[' in a hole reference")


def _find_hole_end(s: str, start: int) -> int:
    """Index of the `}` that closes a hole opening before `start`, or -1.

    Not `s.find("}")`: a quoted key may contain a brace, and a nested
    subscript may contain brackets, so the scan has to track both.
    """
    depth, i, quote = 0, start, ""
    while i < len(s):
        ch = s[i]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        elif ch == "}" and depth <= 0:
            return i
        i += 1
    return -1


def parse_ref(text: str) -> Ref:
    """Parse a hole's interior. **The one implementation of the grammar.**

    The lexer calls this to validate at scan time, so errors land at the
    point of the mistake; the resolver and templates call it to traverse.
    Two rules that must agree drift when written twice, and this grammar is
    used in three places.
    """
    source, text = text, text.strip()
    if not text:
        raise RefError("empty hole '{}'")

    root = False
    if _leads(text, "__ROOT__"):
        root, text = True, _strip_anchor(text, "__ROOT__")
        if not text:
            return Ref(True, [], source)

    # §5.1.1's relative anchors. `__PARENT__` repeats, where `__ROOT__` may not:
    # it moves one level, so a chain of them is the only way to move several.
    parents = 0
    while _leads(text, "__PARENT__"):
        if root:
            raise RefError("__ROOT__ already anchors this reference; "
                           "__PARENT__ is relative and cannot follow it")
        parents += 1
        text = _strip_anchor(text, "__PARENT__")
        if not text:
            return Ref(False, [], source, parents=parents)

    # §5.1.2's named serializers end a reference too: they name an *encoding*
    # of the value reached, so nothing can follow one.
    serializer = ""
    if text.endswith(")"):
        head, _, call = text.rpartition(".")
        if call.endswith("()") and is_dunder(call[:-2]):
            serializer = _check_serializer(call[:-2])
            if not head:
                # A bare anchor is barred for a different reason than a bare
                # serializer, and saying so matters: an anchor is *always* an
                # ancestor of the hole, so encoding it would need the value
                # being encoded. Structural, so it lands here (law 7) rather
                # than as a cycle the resolver reports later.
                anchor = "__ROOT__" if root else "__PARENT__" if parents else ""
                if anchor:
                    raise RefError(
                        f"{anchor} contains this hole, so {{{source.strip()}}} "
                        f"would encode the value it is computing; name a block "
                        f"that does not contain it, as {{{anchor}.blk.{call}}}")
                raise RefError(f"{call} needs a value to encode; write "
                               f"{{something.{call}}}")
            text = head
        elif call.endswith("()"):
            raise RefError(f"{call[:-2]!r} is not a serializer; the named "
                           f"ones are spelled __AS_X__()")

    # `__KEY__` names a *position*, so it ends the reference and may follow
    # only an anchor -- never data traversal. After `a.b` the key is the
    # literal "b", which the author already wrote, so nothing is lost by
    # barring it, and narrowing later would not be compatible.
    if text == "__KEY__":
        if serializer:
            raise RefError("a key is already text; it needs no serializer")
        if root:
            raise RefError("the document root has no key, so "
                           "{__ROOT__.__KEY__} can never name anything")
        return Ref(False, [], source, parents=parents, key=True)

    steps: list = []
    shirans: list[str] = []
    i, expect_name = 0, True
    while i < len(text):
        if text[i] == "[":
            inner, i = _split_subscript(text, i)
            step = _parse_subscript(inner, shirans)
            steps.append(step)
            if step[0] == "ref":
                shirans.extend(step[1].shirans)
            expect_name = False
            continue
        if text[i] == ".":
            if expect_name:
                raise RefError("empty segment in a hole reference "
                               "(two dots, or a leading one)")
            i, expect_name = i + 1, True
            continue
        j = i
        while j < len(text) and text[j] not in ".[":
            j += 1
        seg = text[i:j]
        _check_segment(seg)
        steps.append(("key", fold_name(seg)))
        i, expect_name = j, False
    if expect_name:
        raise RefError("a hole reference may not end with '.'")
    return Ref(root, steps, source, shirans, parents=parents,
               serializer=serializer)


def _check_serializer(name: str) -> str:
    """§5.1.2. The names come from `serializers` rather than a second list
    here, so the grammar cannot come to disagree with what exists."""
    from .serializers import SERIALIZER_NAMES
    if name in SERIALIZER_NAMES:
        return name
    raise RefError(f"there is no serializer named {name}(); yapyon defines "
                   f"{', '.join(n + '()' for n in SERIALIZER_NAMES)}")


def _leads(text: str, anchor: str) -> bool:
    """`anchor` alone, or followed by `.` or `[` — an anchor may be
    subscripted directly, so `{__PARENT__[p]}` addresses the enclosing
    mapping by a key held in `p`."""
    rest = text[len(anchor):]
    return text.startswith(anchor) and (rest == "" or rest[0] in ".[")


def _strip_anchor(text: str, anchor: str) -> str:
    rest = text[len(anchor):]
    return rest[1:] if rest[:1] == "." else rest


def _parse_subscript(inner: str, shirans: list):
    """`["k"]`, `[0]`, or `[ref]` — the three things a bracket may hold."""
    inner = inner.strip()
    if not inner:
        raise RefError("empty subscript '[]'")
    if inner[0] in "\"'":
        if len(inner) < 2 or inner[-1] != inner[0]:
            raise RefError(f"unterminated quoted key {inner!r}")
        key = inner[1:-1]
        if "\\" in key:
            raise RefError("escapes in a quoted key are reserved; write the "
                           "characters directly")
        if is_identifier(key) and not is_dunder(key) \
                and reserved_fold(key) is None:
            # Legal, and equivalent — but there is one canonical spelling.
            # The register's middle rung: did you mean the plainer one?
            shirans.append(f"[{inner[0]}{key}{inner[0]}] is the long way to "
                           f"write .{key}; both name the same key")
        return ("key", fold_name(key))
    if inner[0].isdigit() or inner[0] == "-":
        return ("index", _ref_int(inner))
    return ("ref", parse_ref(inner))


def _check_segment(seg: str) -> None:
    """GRAMMAR §G4.1's identifier rule, applied to a dotted segment."""
    if not seg:
        raise RefError("empty segment in a hole reference")
    if seg == "__ROOT__":                     # before the dunder test, so
        raise RefError("__ROOT__ is only valid as the first segment")
    if seg == "__PARENT__":
        raise RefError("__PARENT__ may only lead a reference, before any "
                       "key or subscript")
    if seg == "__KEY__":
        raise RefError("__KEY__ ends a reference and may follow only "
                       "__PARENT__; after a key the name is already known")
    if is_dunder(seg):                        # the specific message wins
        raise RefError(f"reserved name {seg!r} in hole (defined: __ROOT__, "
                       f"__PARENT__, __KEY__)")
    if ":" in seg or "!" in seg:              # GRAMMAR §G5.2, reserved in §9
        raise RefError("format specs and conversions are reserved; a hole "
                       "names a value and does nothing else")
    if not is_identifier(seg):
        raise RefError(f"holes name document values; {seg!r} is not an "
                       f"identifier{bad_segment_hint(seg)}")
    if seg in KEYWORDS:
        raise RefError(f"{seg!r} cannot be a hole name")
    reserved = reserved_fold(seg)
    if reserved is not None:
        raise RefError(f"{seg!r} is another spelling of {reserved!r}; "
                       f"reserved names are written exactly one way")


DOLLAR_HINT = (" — if the `$` was meant as an environment variable, yapyon "
               "does not expand them; do that after loading")
"""Hedged on purpose (GRAMMAR §G4.7, and the `$VAR` decision behind it).

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
    for ch in seg:
        why = why_not_in_name(ch)
        if why:
            return f" — {why}"
    return ""


def is_dunder(name: str) -> bool:
    """True for names the __dunder__ namespace reserves for yapyon itself.

    **One predicate, two rules** (GRAMMAR §G4.1 and §G5): a hole segment spelled
    this way names one of yapyon's own built-ins — only `__ROOT__` in v0.1 —
    and a *key* spelled this way is akan, so no document can define a name it
    could never address. The parser imports this rather than repeating the
    test, because two rules that must agree will drift when written twice.

    `__` and `___` count. Reserving a little more than `__x__` costs nothing,
    and widening later is compatible where narrowing is not.
    """
    return name.startswith("__") and name.endswith("__")


def _in_table(lows: tuple, table: tuple, ch: str) -> bool:
    cp = ord(ch)
    i = bisect_right(lows, cp) - 1
    return i >= 0 and cp <= table[i][1]


_START_LOWS = tuple(lo for lo, _ in XID_START)
_CONTINUE_LOWS = tuple(lo for lo, _ in XID_CONTINUE)


def id_start(ch: str) -> bool:
    """May `ch` begin a name? GRAMMAR §G4.1: pinned XID_Start, minus the
    default-ignorables, plus `_`. **The table is ours, not the host's** —
    `str.isidentifier()` answers for whatever Unicode the interpreter
    carries, so the same key loaded on 3.13 and akaned on 3.11.

    The emptiness guard is trap 1: `_peek` returns "" at EOF."""
    return bool(ch) and (ch == "_" or _in_table(_START_LOWS, XID_START, ch))


def _id_continue(ch: str) -> bool:
    """May `ch` appear after the first character of a name? (GRAMMAR §G4.1.)"""
    return bool(ch) and _in_table(_CONTINUE_LOWS, XID_CONTINUE, ch)


_IGNORED_LOWS = tuple(lo for lo, _ in XID_IGNORED)


def why_not_in_name(ch: str) -> str:
    """Why `ch` is refused in a name, when the reason is not obvious: it is
    invisible, or it is newer than the pinned table. Empty otherwise.

    Invisible is judged by our table *or* general category Cf, so ZWJ reads
    as invisible on every host — Unicode 14 did not make it an identifier
    character at all, and later versions did."""
    if not ch or id_start(ch) or _id_continue(ch):
        return ""
    label = f"U+{ord(ch):04X} {_uname(ch, 'unnamed')}"
    if _in_table(_IGNORED_LOWS, XID_IGNORED, ch) or _category(ch) == "Cf":
        return (f"{label} is invisible, and names may not contain invisible "
                f"characters (GRAMMAR §G4.1)")
    if ("a" + ch).isidentifier():
        return (f"{label} is not an identifier character in Unicode "
                f"{UNICODE_VERSION}, which yapyon's names are pinned to "
                f"(GRAMMAR §G4.1)")
    return ""


def is_identifier(name: str) -> bool:
    """GRAMMAR §G4.1's one predicate, for keys and hole segments alike.
    It judges the characters **as written**; identity is `fold_name`'s."""
    return (bool(name) and id_start(name[0])
            and all(_id_continue(ch) for ch in name[1:]))


def fold_name(name: str) -> str:
    """A name's identity (GRAMMAR §G4.1, SPEC §7): width variants to their
    standard form, **then** NFC. `ｎａｍｅ` and `name` are the same name by
    definition, as are `café` spelled precomposed and decomposed.

    The order is load-bearing. Halfwidth `ｶﾞ` unfolds to `カ` plus a
    *combining* voiced mark, and only NFC afterwards composes that into
    `ガ`; the other order leaves it decomposed, a different string.

    Only the `<wide>` and `<narrow>` compatibility mappings are applied —
    the rest of NFKC is not, so `ﬁ` and `fi` stay distinct names. Both steps
    read the host's `unicodedata`, which is sound because Unicode's
    stability policies freeze decompositions and NFC for every character
    already assigned, and a name holds only Unicode 14 characters."""
    if name.isascii():
        return name
    out = []
    for ch in name:
        d = _decomposition(ch)
        if d.startswith(("<wide>", "<narrow>")):
            out.extend(chr(int(h, 16)) for h in d.split()[1:])
        else:
            out.append(ch)
    return _normalize("NFC", "".join(out))


def reserved_fold(name: str) -> str | None:
    """The keyword, prefix or dunder `name` folds onto without being spelled
    as, if any. Such a name is akan, as in Python, where `Ｔｒｕｅ` is an
    error rather than `True`: reserved words have exactly one spelling
    (GRAMMAR §G4.1), and folding is what defines *names*, not syntax."""
    folded = fold_name(name)
    if folded != name and (folded in KEYWORDS or folded in STRING_PREFIXES
                           or is_dunder(folded)):
        return folded
    return None


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

        if id_start(ch):                       # identifier, keyword, or prefix
            name = self._scan_identifier()
            reserved = reserved_fold(name)
            if reserved is not None:
                self._akan(f"{name!r} is another spelling of {reserved!r}; "
                           f"keywords, prefixes and dunder names are written "
                           f"exactly one way", line, col)
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
                # The token carries the name's identity; the lexeme keeps
                # what was written, for diagnostics.
                self._emit("NAME", fold_name(name), line, col, lexeme=name)
            return

        for reserved in ("---", "..."):           # GRAMMAR §G6, reserved tokens
            if self.text.startswith(reserved, self.pos):
                self._akan(f"{reserved!r} is reserved and has no meaning in "
                           f"v0.1; yapyon is one document per file")
        if ch in "-+" and self._peek(1) in (" ", "\n", ""):
            self._akan(f"{ch!r} opens a block frame only at the start of a "
                       f"line's content")
        why = why_not_in_name(ch)
        if why:
            self._akan(why)
        if _id_continue(ch):        # GRAMMAR §G4.1: legal inside a name, just not first
            self._akan(f"{ch!r} cannot start a name, though it may appear "
                       f"inside one (GRAMMAR §G4.1: names are Unicode identifiers)")
        if ch.isalnum():            # word-like, but no identifier admits it
            self._akan(f"{ch!r} cannot appear in a name (GRAMMAR §G4.1: names are "
                       f"Unicode identifiers, UAX #31)")
        self._akan(f"unexpected character {ch!r}")

    def _scan_identifier(self) -> str:
        """Scan one identifier (GRAMMAR §G4.1) as written: a start
        character, then continue characters, both from the pinned table.

        This is deliberately the same rule `_check_segment` applies to hole
        segments, so every key is addressable from a hole. The EOF guard lives
        in the predicates (trap 1)."""
        if not id_start(self._peek()):
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
            if ch == "\\" and self._peek(1) not in ("", "\n"):
                # A backslash protects the character after it, so `\"` is
                # content and not the closing delimiter -- GRAMMAR §G4.5's table has
                # \" and \'. This is a *scanning* rule, so it holds for raw
                # strings too: r"x\"y" keeps the backslash in the value but
                # still does not end there, exactly as in Python.
                # Backslash-newline is excluded so the newline branch below
                # keeps doing GRAMMAR §G4.4's dedent; _process_escapes joins the line
                # afterwards. The empty peek guards EOF (trap 1).
                for _ in range(2):
                    pos.append((self.line, self.col))
                    out.append(self._advance())
                pristine = False
                continue
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
                # Unreachable from any document: _scan_string_body consumes a
                # backslash together with the character it protects, so a body
                # cannot end on a lone one -- a backslash last before EOF is
                # caught there as "unterminated string". Kept as an invariant
                # rather than deleted, because the scanner is what makes it
                # true and a future change there should say so loudly.
                raise Yakamashiwa(
                    "escape processing reached a dangling backslash; "
                    "_scan_string_body should have made this impossible")
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
                if 0xD800 <= codepoint <= 0xDFFF:      # GRAMMAR §G4.5
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

        Holes are recognised **before** escapes decode (GRAMMAR §G4.7), so an
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
                end = _find_hole_end(s, i + 1)
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
        """Validate at scan time, so a malformed reference akans where it was
        written. `parse_ref` owns the grammar; this only supplies position."""
        try:
            ref = parse_ref(name)
        except RefError as e:
            self._akan(str(e), line, col)
        for message in ref.shirans:
            where = (f"line {line}, col {col}" if self.source is None
                     else f"{self.source}:{line}:{col}")
            self.warnings.append(f"shiran: {where}: {message}")


def tokenize(text: str, *, source: str | None = None) -> list[Token]:
    return Lexer(text, source=source).tokenize()


def _dump(text, source):
    lexer = Lexer(text, source=source)
    tokens = lexer.tokenize()
    return "".join(f"{tok}\n" for tok in tokens), lexer.warnings


def main(argv):
    """The token dump, as `python -m yapyon lexer`."""
    from ._cli import run
    return run(argv, _dump)


if __name__ == "__main__":
    import sys

    # Delegate through the *package* module rather than calling `main` in this
    # namespace. Under `python -m yapyon.lexer` this file runs a second time as
    # `__main__`, so its `AkanError` is a different class object from the one
    # `_cli` catches -- and the akan would escape as a traceback. Importing by
    # full path gets the canonical module. `python -m yapyon lexer` avoids the
    # double import entirely and is the documented spelling.
    from yapyon.lexer import main as _main

    sys.exit(_main(sys.argv))
