"""yapyon reference parser — v0.1

YAMLちゃうで。やぴょんやぴょん。

Recursive descent over the lexer's token stream (SPEC §8).  The grammar is
plain LL(1); the one lookahead-sensitive spot is that a NAME at the start of
a line is a key iff a COLON follows it.

The parser is context-free by construction.  The lexer has already resolved
indentation into INDENT / DEDENT / DASH and suppressed newlines inside
brackets, so nothing here inspects a column or a character — and there is no
feedback channel back to the lexer.

The AST keeps exactly what the resolver (SPEC §5) will need:

  * every node carries the line and column of its first character;
  * numeric and keyword scalars carry their **source lexeme**, because
    non-string scalars splice their lexeme, not their value (SPEC §5.4);
  * bytes scalars carry the spelling that produced them ("b" / "rb" / "b64"),
    because the splice matrix (SPEC §5.5) admits b64-bytes into text and
    akans b-bytes there;
  * y-family literals stay unresolved as YString nodes.  Holes are the
    resolver's business; the parser only carries them.

A mapping's pairs are kept as an ordered list (with a by_key index built
alongside), not as a bare dict: order is part of the document, and it is what
a diagnostic points back at.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .lexer import AkanError, Lexer, Token, Yakamashiwa, is_dunder


# --------------------------------------------------------------------------- #
# AST
# --------------------------------------------------------------------------- #
@dataclass
class Node:
    """Base: every node knows where it began."""

    line: int
    col: int


@dataclass
class Scalar(Node):
    """A literal.  `lexeme` is the source spelling of numbers and keywords —
    what a y-string splices (SPEC §5.4).  `prefix` is the string/bytes
    spelling as written, which the splice matrix (SPEC §5.5) cares about."""

    type: str                 # str | bytes | int | float | bool | none
    value: object
    lexeme: str = ""
    prefix: str = ""


@dataclass
class YString(Node):
    """An unresolved y-family literal: alternating text and holes."""

    prefix: str               # y | ry | yb | yt
    parts: list = field(default_factory=list)   # [("text", s) | ("hole", "a.b")]

    @property
    def type(self) -> str:
        return _Y_TYPE[self.prefix]


_Y_TYPE = {"y": "str", "ry": "str", "yb": "bytes", "yt": "template"}


@dataclass
class Pair(Node):
    """One `key: value`.  The position is the key's."""

    key: str
    value: Node


@dataclass
class Mapping(Node):
    pairs: list = field(default_factory=list)   # list[Pair], in source order

    def __post_init__(self):
        # Keys within one mapping are unique (SPEC §7), so this is lossless.
        self.by_key = {p.key: p.value for p in self.pairs}


@dataclass
class Sequence(Node):
    items: list = field(default_factory=list)   # list[Node]


@dataclass
class MultiMap(Node):
    """An ordered multimap (SPEC §7.1): keyed entries whose keys may repeat.

    Deliberately no `by_key` index — repeats are the point, and the entry
    keys take no part in hole resolution (§5.2)."""

    entries: list = field(default_factory=list)   # list[Pair], in source order


# --------------------------------------------------------------------------- #
# Token classes and diagnostics
# --------------------------------------------------------------------------- #
_SCALAR_KINDS = frozenset({"STRING", "BYTES", "INT", "FLOAT", "KEYWORD",
                           "YSTR", "YBSTR", "YTSTR"})

_DESCRIBE = {
    "NEWLINE": "end of line", "EOF": "end of file",
    "INDENT": "an indented block", "DEDENT": "the end of a block",
    "DASH": "a sequence item ('- ')",
    "COLON": "':'", "COMMA": "','",
    "LBRACKET": "'['", "RBRACKET": "']'",
    "LBRACE": "'{'", "RBRACE": "'}'",
    "STRING": "a string", "BYTES": "a bytes literal",
    "INT": "an integer", "FLOAT": "a float",
    "YSTR": "a y-string", "YBSTR": "a yeeb-string", "YTSTR": "a yeet-string",
}

# The Norway problem, answered at the point of the mistake.
_BARE_WORD_FIX = {
    "true": "True", "yes": "True", "on": "True", "y": "True",
    "false": "False", "no": "False", "off": "False", "n": "False",
    "null": "None", "nil": "None", "none": "None",
}


def _describe(tok: Token) -> str:
    if tok.kind == "NAME":
        return f"the bare word {tok.value!r}"
    if tok.kind == "KEYWORD":
        return tok.lexeme or repr(tok.value)
    return _DESCRIBE.get(tok.kind, tok.kind)


def _bare_word_msg(word: str) -> str:
    """Law 1: an unquoted word is never a string and never a boolean."""
    fix = _BARE_WORD_FIX.get(word.lower())
    if fix:
        return (f"bare word {word!r} in value position; write {fix} for the "
                f'value or "{word}" for the string')
    if word.lower() in ("inf", "nan", "infinity"):
        return (f"bare word {word!r} in value position; yapyon has no "
                f'inf/nan spelling (quote it: "{word}")')
    return (f"bare word {word!r} in value position; yapyon has no plain "
            f'scalars (quote it: "{word}")')


_BLOCK_FORM = {
    "DASH": "'- ' items",
    "PLUS": "'+ ' entries",
    "NAME": "'key: value' pairs",
}


def _bad_key_msg(tok: Token) -> str:
    """SPEC §7: keys are bare identifiers in v0.1."""
    if tok.kind in ("STRING", "YSTR", "YTSTR"):
        return ("keys are bare identifiers in v0.1; quoted keys are reserved "
                "(write name: rather than \"name\":)")
    if tok.kind in ("BYTES", "YBSTR"):
        return "keys are bare identifiers in v0.1; a bytes literal is not a key"
    if tok.kind in ("INT", "FLOAT"):
        return "keys are bare identifiers in v0.1; numeric keys are akan"
    if tok.kind == "KEYWORD":
        spelling = tok.lexeme or str(tok.value)
        return f"{spelling!r} is a keyword, not a key"
    return f"expected a key (a bare identifier), found {_describe(tok)}"


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
class Parser:
    """Recursive descent over a token stream.  `warnings` carries shiran
    diagnostics forward from the lexer; the loader (SPEC §6) surfaces them."""

    def __init__(self, tokens: list[Token], warnings: list[str] | None = None,
                 *, source: str | None = None):
        self.toks = tokens
        self.i = 0
        self.warnings: list[str] = list(warnings or [])
        self.source = source              # a name for diagnostics, if known

    # -- token helpers -------------------------------------------------------
    def _peek(self, n: int = 0) -> Token:
        return self.toks[min(self.i + n, len(self.toks) - 1)]   # EOF is a fixpoint

    def _at(self, *kinds: str) -> bool:
        return self._peek().kind in kinds

    def _advance(self) -> Token:
        tok = self._peek()
        if tok.kind != "EOF":
            self.i += 1
        return tok

    def _akan(self, msg: str, tok: Token | None = None):
        at = self._peek() if tok is None else tok
        raise AkanError(msg, at.line, at.col, self.source)

    def _expect(self, kind: str, msg: str) -> Token:
        if not self._at(kind):
            self._akan(msg)
        return self._advance()

    # -- document ------------------------------------------------------------
    def parse(self) -> Node:
        if not self.toks or self.toks[-1].kind != "EOF":
            raise Yakamashiwa("token stream does not end with EOF")
        if self._at("EOF"):
            self._akan("empty document (a document is exactly one value)")
        node = self._block_value()
        if not self._at("EOF"):
            self._akan(f"expected end of file, found "
                       f"{_describe(self._peek())} after the document's "
                       f"value; yapyon is one document per file")
        return node

    # -- block level ---------------------------------------------------------
    def _block_value(self) -> Node:
        if self._at("DASH"):
            return self._block_seq()
        if self._at("PLUS"):
            return self._block_mmap()
        if self._at("NAME") and self._peek(1).kind == "COLON":
            return self._block_map()
        start = self._peek()
        value = self._flow_value()
        if self._at("COLON"):                    # `"a": 1`, `1: 2`, `True: 1`
            self._akan(_bad_key_msg(start), start)
        self._expect("NEWLINE",
                     f"expected end of line after the value, found "
                     f"{_describe(self._peek())}")
        return value

    def _block_map(self) -> Mapping:
        first = self._peek()
        pairs: list[Pair] = []
        first_line: dict[str, int] = {}
        while self._at("NAME") and self._peek(1).kind == "COLON":
            pairs.append(self._pair(first_line))
        if not self._at("DEDENT", "EOF"):
            tok = self._peek()
            if tok.kind in ("DASH", "PLUS"):
                self._akan_mixed("NAME", tok)
            self._akan(f"expected a key, found {_describe(tok)}")
        return Mapping(first.line, first.col, pairs)

    def _akan_mixed(self, own: str, tok: Token):
        """SPEC §7.1: a block is a mapping, a sequence, or a multimap."""
        self._akan(f"a block holds {_BLOCK_FORM[own]} or "
                   f"{_BLOCK_FORM[tok.kind]}, not both", tok)

    def _check_key(self, key_tok: Token, first_line: dict[str, int]) -> str:
        """SPEC §7's rules on a name in key position, in one place.

        Block pairs and flow maps both come here so the two cannot drift —
        they held separate copies of the duplicate check before.
        """
        key = key_tok.value
        if is_dunder(key):
            self._akan(f"{key!r} cannot be a key: dunder names are reserved "
                       f"for yapyon's own (only __ROOT__ is defined), so no "
                       f"hole could ever name it — drop the leading and "
                       f"trailing '__'", key_tok)
        if key in first_line:
            self._akan(f"duplicate key {key!r} (first defined on line "
                       f"{first_line[key]})", key_tok)
        first_line[key] = key_tok.line
        return key

    def _pair(self, first_line: dict[str, int]) -> Pair:
        key_tok = self._advance()                # NAME
        self._advance()                          # COLON
        key = self._check_key(key_tok, first_line)

        if self._at("NEWLINE"):                  # value is an indented block
            self._advance()
            if not self._at("INDENT"):
                self._akan(f"key {key!r} has no value (write one after the "
                           f"colon, or indent a block under it)", key_tok)
            self._advance()
            value = self._block_value()
            self._expect("DEDENT", "expected the end of the indented block")
        else:                                    # value is on this line
            value = self._flow_value()
            self._expect("NEWLINE",
                         f"expected end of line after the value of {key!r}, "
                         f"found {_describe(self._peek())}")
        return Pair(key_tok.line, key_tok.col, key, value)

    def _frame_body(self, marker: Token, parse_body, what: str) -> Node:
        """`MARKER INDENT [ NEWLINE ] body DEDENT` (SPEC §8).

        The optional NEWLINE is the bare-marker form (`-` or `+` alone on its
        line); the optional inner INDENT/DEDENT covers a body indented deeper
        than the frame's anchor.  Both are layout, not meaning."""
        if not self._at("INDENT"):               # the lexer pairs these
            raise Yakamashiwa(f"{marker.kind} not followed by INDENT")
        self._advance()
        if self._at("NEWLINE"):                  # bare marker; body beneath it
            self._advance()
            if self._at("DEDENT"):               # ...except there is no body
                self._akan(f"{what} has no value (write None)", marker)
            if self._at("INDENT"):               # body sits deeper than anchor
                self._advance()
                body = parse_body()
                self._expect("DEDENT", f"expected the end of the {what}")
            else:
                body = parse_body()
        else:
            body = parse_body()
        self._expect("DEDENT", f"expected the end of the {what}")
        return body

    def _block_seq(self) -> Sequence:
        first = self._peek()
        items: list[Node] = []
        while self._at("DASH"):
            items.append(self._frame_body(self._advance(), self._block_value,
                                          "sequence item"))
        if not self._at("DEDENT", "EOF"):
            tok = self._peek()
            if tok.kind == "PLUS" or (tok.kind == "NAME"
                                      and self._peek(1).kind == "COLON"):
                self._akan_mixed("DASH", tok)
            self._akan(f"expected a sequence item ('- '), found "
                       f"{_describe(tok)}")
        return Sequence(first.line, first.col, items)

    def _block_mmap(self) -> MultiMap:
        first = self._peek()
        entries: list[Pair] = []
        while self._at("PLUS"):
            entries.append(self._frame_body(self._advance(), self._mmap_entry,
                                            "multimap entry"))
        if not self._at("DEDENT", "EOF"):
            tok = self._peek()
            if tok.kind == "DASH" or (tok.kind == "NAME"
                                      and self._peek(1).kind == "COLON"):
                self._akan_mixed("PLUS", tok)
            self._akan(f"expected a multimap entry ('+ '), found "
                       f"{_describe(tok)}")
        return MultiMap(first.line, first.col, entries)

    def _mmap_entry(self) -> Pair:
        """Exactly one pair (SPEC §7.1).  Keys repeat *across* entries."""
        tok = self._peek()
        if not (tok.kind == "NAME" and self._peek(1).kind == "COLON"):
            if tok.kind in _SCALAR_KINDS or tok.kind in ("LBRACKET", "LBRACE"):
                self._akan("a multimap entry is a 'key: value' pair, not a "
                           "bare value")
            self._akan(f"expected a key, found {_describe(tok)}")
        pair = self._pair({})                    # no cross-entry dup check
        if self._at("NAME") and self._peek(1).kind == "COLON":
            self._akan("a multimap entry holds one key: value pair; indent it "
                       "under the key, or open a new '+ ' entry")
        return pair

    # -- flow level ----------------------------------------------------------
    def _flow_value(self) -> Node:
        tok = self._peek()
        if tok.kind == "LBRACKET":
            return self._flow_list()
        if tok.kind == "LBRACE":
            return self._flow_map()
        if tok.kind in _SCALAR_KINDS:
            return self._scalar()
        if tok.kind == "NAME":
            self._akan(_bare_word_msg(tok.value))
        self._akan(f"expected a value, found {_describe(tok)}")

    def _scalar(self) -> Node:
        tok = self._advance()
        if tok.kind in ("YSTR", "YBSTR", "YTSTR"):
            return YString(tok.line, tok.col, tok.prefix, list(tok.parts))
        if tok.kind == "STRING":
            return Scalar(tok.line, tok.col, "str", tok.value, prefix=tok.prefix)
        if tok.kind == "BYTES":
            return Scalar(tok.line, tok.col, "bytes", tok.value,
                          prefix=tok.prefix)
        if tok.kind in ("INT", "FLOAT"):
            return Scalar(tok.line, tok.col, tok.kind.lower(), tok.value,
                          lexeme=tok.lexeme)
        if tok.kind == "KEYWORD":
            kind = "bool" if isinstance(tok.value, bool) else "none"
            return Scalar(tok.line, tok.col, kind, tok.value, lexeme=tok.lexeme)
        raise Yakamashiwa(f"scalar token of unknown kind {tok.kind!r}")

    def _flow_list(self) -> Sequence:
        opener = self._advance()                 # LBRACKET
        items: list[Node] = []
        while not self._at("RBRACKET"):
            items.append(self._flow_value())
            if self._at("COMMA"):
                self._advance()                  # trailing comma is fine
            elif not self._at("RBRACKET"):
                self._akan(f"expected ',' or ']' in a flow list, found "
                           f"{_describe(self._peek())} (commas are mandatory)")
        self._advance()                          # RBRACKET
        return Sequence(opener.line, opener.col, items)

    def _flow_map(self) -> Mapping:
        opener = self._advance()                 # LBRACE
        pairs: list[Pair] = []
        first_line: dict[str, int] = {}
        while not self._at("RBRACE"):
            key_tok = self._peek()
            if key_tok.kind != "NAME":
                self._akan(_bad_key_msg(key_tok), key_tok)
            self._advance()
            self._expect("COLON", f"expected ':' after the key "
                                  f"{key_tok.value!r}")
            key = self._check_key(key_tok, first_line)
            pairs.append(Pair(key_tok.line, key_tok.col, key,
                              self._flow_value()))
            if self._at("COMMA"):
                self._advance()                  # trailing comma is fine
            elif not self._at("RBRACE"):
                self._akan(f"expected ',' or '}}' in a flow mapping, found "
                           f"{_describe(self._peek())} (commas are mandatory)")
        self._advance()                          # RBRACE
        return Mapping(opener.line, opener.col, pairs)


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #
def parse_tokens(tokens: list[Token], warnings: list[str] | None = None,
                 *, source: str | None = None) -> Node:
    return Parser(tokens, warnings, source=source).parse()


def parse(text: str, *, source: str | None = None) -> Node:
    """Text to AST.  Holes are left unresolved (SPEC §5 is the resolver's);
    the loader will drive `Parser` directly to reach its warnings."""
    lexer = Lexer(text, source=source)
    tokens = lexer.tokenize()
    return Parser(tokens, lexer.warnings, source=source).parse()


def dump(node: Node, level: int = 0) -> str:
    """One node per line, positions attached — for `python -m yapyon.parser`."""
    pad = "  " * level
    where = f"@{node.line}:{node.col}"
    if isinstance(node, Mapping):
        if not node.pairs:
            return f"{pad}mapping (empty) {where}"
        out = [f"{pad}mapping {where}"]
        for pair in node.pairs:
            out.append(f"{pad}  {pair.key}: @{pair.line}:{pair.col}")
            out.append(dump(pair.value, level + 2))
        return "\n".join(out)
    if isinstance(node, MultiMap):
        out = [f"{pad}multimap {where}"]
        for entry in node.entries:
            out.append(f"{pad}  + {entry.key}: @{entry.line}:{entry.col}")
            out.append(dump(entry.value, level + 2))
        return "\n".join(out)
    if isinstance(node, Sequence):
        if not node.items:
            return f"{pad}sequence (empty) {where}"
        out = [f"{pad}sequence {where}"]
        for item in node.items:
            out.append(dump(item, level + 1))
        return "\n".join(out)
    if isinstance(node, YString):
        return f"{pad}{node.prefix}-string {node.parts!r} {where}"
    if isinstance(node, Scalar):
        extra = f" lexeme={node.lexeme!r}" if node.lexeme else ""
        extra += f" prefix={node.prefix!r}" if node.prefix else ""
        return f"{pad}{node.type} {node.value!r}{extra} {where}"
    raise Yakamashiwa(f"unknown node type {type(node).__name__}")


def _dump(text, source):
    # Driving the stages directly rather than calling `parse`, which discards
    # warnings by design -- see `_cli` for why a CLI shows them.
    from .lexer import Lexer
    lexer = Lexer(text, source=source)
    parser = Parser(lexer.tokenize(), lexer.warnings, source=source)
    return dump(parser.parse()) + "\n", parser.warnings


def main(argv):
    """The AST dump, as `python -m yapyon parser`."""
    from ._cli import run
    return run(argv, _dump)


if __name__ == "__main__":
    import sys

    # See the note in lexer.py: under `python -m yapyon.parser` this file runs
    # again as `__main__`, so the exception classes would not match.
    from yapyon.parser import main as _main

    sys.exit(_main(sys.argv))
