"""yapyon reference parser

YAMLちゃうで。やぴょんやぴょん。

Recursive descent over the lexer's token stream (GRAMMAR §G6).  The grammar is
plain LL(1); the one lookahead-sensitive spot is that a NAME at the start of
a line is a key iff a COLON follows it.

The parser is context-free by construction.  The lexer has already resolved
indentation into INDENT / DEDENT / DASH and suppressed newlines inside
brackets, so nothing here inspects a column or a character — and there is no
feedback channel back to the lexer.

The AST keeps exactly what the resolver (SPEC §5) will need:

  * every node carries the line and column of its first character;
  * every literal, and every key, carries its **source lexeme** (SPEC §3),
    so a writer can reproduce what the author wrote;
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

import copy
from dataclasses import dataclass, field
from itertools import count

from .lexer import (AkanError, Lexer, RefError, Token, Yakamashiwa,
                    fold_name, is_dunder, parse_ref)
from ._keys import key_error


# --------------------------------------------------------------------------- #
# AST
# --------------------------------------------------------------------------- #
@dataclass
class Node:
    """Base: every node knows where it began — line, column, and the
    document it was written in, so a diagnostic in a tree assembled from
    several documents names the right one (SPEC §15.6). `source` is a
    class attribute, not a field: set on parsed nodes, `None` otherwise."""

    line: int
    col: int

    source = None
    fill_checks = ()


@dataclass
class Scalar(Node):
    """A literal.  `lexeme` is its source spelling, prefix, quotes and
    escapes included (SPEC §3) — what a yapyon writer reproduces (§4.4).
    Empty for a value with no source, such as a resolved y-string.
    `prefix` is the string/bytes prefix as written."""

    type: str                 # str | bytes | int | float | bool | none
    value: object
    lexeme: str = ""
    prefix: str = ""


@dataclass
class YString(Node):
    """An unresolved y-family literal: alternating text and holes."""

    prefix: str               # y | ry | yb | yt
    parts: list = field(default_factory=list)   # [("text", s) | ("hole", "a.b")]
    lexeme: str = ""          # the literal as written, prefix and quotes included

    @property
    def type(self) -> str:
        return _Y_TYPE[self.prefix]


_Y_TYPE = {"y": "str", "ry": "str", "yb": "bytes", "yt": "template",
           "(": "copy"}


class Copy(YString):
    """An unresolved copy, `(ref)` — SPEC §5.6: a typed copy of the value
    `ref` names, taken once that value is resolved.

    A `YString` on purpose: one hole and no text, so every place the
    resolver waits on an unresolved y-string — a hole's target, a step
    mid-walk, a subscript's key, a call's argument, §5.3's cycle — waits on
    a copy the same way, with no second path to keep in step (trap 9)."""

    def __init__(self, line: int, col: int, ref: str, lexeme: str = ""):
        super().__init__(line, col, "(", [("hole", ref)], lexeme)

    @property
    def ref(self) -> str:
        return self.parts[0][1]


@dataclass
class ResolvedTemplate(Node):
    """A `yt` literal after resolution — SPEC §6.

    `yt` is a y-string that is **not joined**: its holes resolve against the
    document exactly as `y`'s do, and the consumer receives the parts plus the
    resolved values instead of one flat string. The parser cannot produce this
    node; only the resolver can, because only it has done the lookups.

    `parts` alternates ("text", str) and ("hole", ref_text, Node), with the
    resolved node kept whole so `build` can hand over the real value and the
    §5.5 text together.
    """

    parts: list = field(default_factory=list)


@dataclass
class Slot(Node):
    """A slot — SPEC §15: a value its consumer fills, written
    `key<label>: {overrides}`.

    `label` is the tuple of folded names, empty for an abstract slot
    (`<>`); `lexeme` is the label as written. `layers` holds the override
    mappings, innermost first: one as parsed, more once merges and moved
    slots stack them (§15.2, §15.4). A slot is never resolved — filling
    replaces it, and one left at resolution is akan (§15.6)."""

    label: tuple
    layers: list = field(default_factory=list)   # list[Mapping]
    lexeme: str = ""
    key: str = ""             # the key as written, for diagnostics

    @property
    def abstract(self) -> bool:
        return not self.label


_pair_ids = count()


@dataclass
class Pair(Node):
    """One `key: value`. `key` is its identity, or a pending y-string.
    `named` distinguishes names from data keys (SPEC §7); `lexeme` keeps
    the spelling (§4.4), and `key_node` keeps a resolved key's dependencies.
    `identity` is an unresolved Tree location, never data-key equality."""

    key: str | YString
    value: Node
    lexeme: str = ""
    named: bool = True
    key_node: Scalar | None = None
    identity: int = field(default_factory=lambda: next(_pair_ids), compare=False,
                          repr=False)

    def __deepcopy__(self, memo):
        out = object.__new__(type(self))
        memo[id(self)] = out
        out.__dict__ = copy.deepcopy(self.__dict__, memo)
        out.identity = next(_pair_ids)
        return out


@dataclass
class Mapping(Node):
    pairs: list = field(default_factory=list)   # list[Pair], in source order

    def __post_init__(self):
        self.reindex()

    def reindex(self):
        self._pairs_by_key = {p.key: p for p in self.pairs if isinstance(p.key, str)}
        self._names = {k: p for k, p in self._pairs_by_key.items() if p.named}
        self.by_key = {k: p.value for k, p in self._pairs_by_key.items()}

    def pending_key(self):
        return next((p.key for p in self.pairs if isinstance(p.key, YString)), None)

    def key_pair(self, key: str, *, named: bool = False):
        if named:
            return self._names.get(key)
        exact = self._pairs_by_key.get(key)
        return exact if exact is not None else self._names.get(fold_name(key))


@dataclass
class Sequence(Node):
    items: list = field(default_factory=list)   # list[Node]


@dataclass
class MultiMap(Node):
    """An ordered multimap (SPEC §7.1): keyed entries whose keys may repeat.

    Deliberately no `by_key` index — repeats are the point, and the entry
    keys take no part in hole resolution (§5.2)."""

    entries: list = field(default_factory=list)   # list[Pair], in source order

    def key_pairs(self, key: str, *, named: bool = False):
        exact = not named and any(p.key == key for p in self.entries)
        if exact:
            return [p for p in self.entries if p.key == key]
        folded = fold_name(key)
        return [p for p in self.entries if p.named and p.key == folded]


class Expression(YString):
    """A deferred value expression; shares every pending outcome with copies."""

    def __init__(self, line, col, op, args=(), value=None, lexeme=""):
        super().__init__(line, col, "(", [("expression", op)], lexeme)
        self.op, self.args, self.value = op, list(args), value

    @property
    def type(self):
        return "expression"


class Comprehension(Expression):
    """Unevaluated collection construction with one lexical binding frame."""

    def __init__(self, line, col, kind, names, iterable, body, predicate=None,
                 key=None):
        super().__init__(line, col, "comprehension", [iterable, body, predicate, key])
        self.kind, self.names = kind, tuple(names)


class DictionaryComprehension(Comprehension, Mapping):
    """A deferred dictionary contribution on the existing mapping merge path."""

    def __init__(self, *args, **kwargs):
        Comprehension.__init__(self, *args, **kwargs)
        self.pairs = []
        self.reindex()

    def pending_key(self):
        return self._output.pending_key() if getattr(self, "_expanded", False) else self


def deferred_message(kind: str, prefix: str) -> str:
    """Why a record refuses this token (SPEC §12)."""
    if kind in ("BCOMP", "LCOMP", "DCOMP", "MCOMP", "FOR"):
        return "a record holds no comprehensions; collection construction needs the resolver"
    if kind in ("REF", "COMPARE", "AND", "OR", "NOT", "IS", "IN", "DOT", "SAFE_DOT"):
        return "a record holds no expressions; computation needs the resolver"
    if kind == "LPAREN":
        return ("a record admits no parentheses: they group what is computed "
                "(write the value without them, or load with yapyon.loads "
                "for the full form)")
    if kind == "LABEL":
        return ("a record holds no slots: a slot's value comes from outside "
                "the document (SPEC §15)")
    if kind == "COPY":
        return ("a record's leaves must all be literals; a copy (…) takes "
                "its value from elsewhere in the document (load with "
                "yapyon.loads for the full form)")
    return (f"a record's leaves must all be literals; a {prefix}-string "
            f"defers its value (load with yapyon.loads for the full form)")


# --------------------------------------------------------------------------- #
# Token classes and diagnostics
# --------------------------------------------------------------------------- #
_SCALAR_KINDS = frozenset({"STRING", "BYTES", "INT", "FLOAT", "KEYWORD",
                           "YSTR", "YBSTR", "YTSTR", "COPY"})

_DESCRIBE = {
    "NEWLINE": "end of line", "EOF": "end of file",
    "INDENT": "an indented block", "DEDENT": "the end of a block",
    "DASH": "a sequence item ('- ')", "PLUS": "a multimap's '+'",
    "COLON": "':'", "COMMA": "','",
    "LBRACKET": "'['", "RBRACKET": "']'",
    "LBRACE": "'{'", "RBRACE": "'}'",
    "LPAREN": "'('", "RPAREN": "')'", "COPY": "a copy",
    "LABEL": "a slot's label",
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
    "QKEY": "'key: value' pairs",
    "YKEY": "'key: value' pairs",
}


def _bad_key_msg(tok: Token) -> str:
    """GRAMMAR §G7: key forms that cannot produce an ordinary string."""
    if tok.kind == "YTSTR":
        return "a template is not key text; use a plain, y, or ry string"
    if tok.kind in ("BYTES", "YBSTR"):
        return "keys are names or strings; a bytes literal is not a key"
    if tok.kind in ("INT", "FLOAT"):
        return "keys are names or strings; numeric keys are akan"
    if tok.kind == "KEYWORD":
        spelling = tok.lexeme or str(tok.value)
        return f"{spelling!r} is a keyword, not a key"
    return f"expected a key (a name or string), found {_describe(tok)}"


def children(node: Node) -> list:
    """A node's direct children, in document order — slot overrides
    included. The one walk every tree pass shares."""
    if isinstance(node, Expression):
        return [arg for arg in node.args if isinstance(arg, Node)]
    if isinstance(node, (Mapping, MultiMap)):
        pairs = node.pairs if isinstance(node, Mapping) else node.entries
        return [child for pair in pairs
                for child in ([pair.key, pair.value] if isinstance(pair.key, Node)
                              else [pair.value])]
    if isinstance(node, Sequence):
        return list(node.items)
    if isinstance(node, Slot):
        return list(node.layers)
    return []


def stamp(node: Node, source: str) -> None:
    """Record the document every node of `node` was written in."""
    node.source = source
    if isinstance(node, (Mapping, MultiMap)):
        for pair in node.pairs if isinstance(node, Mapping) else node.entries:
            pair.source = source
    for child in children(node):
        stamp(child, source)


def _at_node(node: Node, fallback: Token) -> Token:
    """A token-shaped position for a node, for `_akan`."""
    return Token("", None, getattr(node, "line", fallback.line),
                 getattr(node, "col", fallback.col))


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
    def _at_key(self, n: int = 0) -> bool:
        """A key token and its optional label precede ':' (GRAMMAR §G6)."""
        if self._peek(n).kind not in ("NAME", "QKEY", "YKEY"):
            return False
        nxt = self._peek(n + 1).kind
        return nxt == "COLON" or (nxt == "LABEL"
                                  and self._peek(n + 2).kind == "COLON")

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
        if self.source is not None:
            stamp(node, self.source)
        return node

    # -- block level ---------------------------------------------------------
    def _block_value(self) -> Node:
        if self._at("BCOMP"):
            return self._block_comprehension()
        if self._at("DASH"):
            return self._block_seq()
        if self._at("PLUS"):
            return self._block_mmap()
        if self._at_key():
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
        first_line: dict[str, tuple[int, str]] = {}
        while self._at_key():
            pairs.append(self._pair(first_line))
        if not self._at("DEDENT", "EOF"):
            tok = self._peek()
            if tok.kind in ("DASH", "PLUS"):
                self._akan_mixed("NAME", tok)
            self._akan(f"expected a key, found {_describe(tok)}")
        return Mapping(first.line, first.col, pairs)

    def _akan_mixed(self, own: str, tok: Token):
        """GRAMMAR §G7: a block is a mapping, a sequence, or a multimap."""
        self._akan(f"a block holds {_BLOCK_FORM[own]} or "
                   f"{_BLOCK_FORM[tok.kind]}, not both", tok)

    def _check_key(self, key_tok: Token,
                   first_line: dict[str, tuple[int, str]]) -> str | YString:
        """GRAMMAR §G7's rules on a name in key position, in one place.

        Block pairs and flow maps both come here so the two cannot drift —
        they held separate copies of the duplicate check before.
        """
        if key_tok.kind == "YKEY":
            return YString(key_tok.line, key_tok.col, key_tok.prefix,
                           list(key_tok.parts), key_tok.lexeme)
        if key_tok.kind == "QKEY" and key_tok.prefix:
            self._akan("a literal key is a plain quoted string; "
                       "only y and ry prefixes are allowed on keys", key_tok)
        key = key_tok.value
        why = key_error(key)
        if why:
            self._akan(why, key_tok)
        if key in first_line:
            # Names are compared after folding (SPEC §7), so when either
            # spelling differs from the name, show both: `name` and `ｎａｍｅ`
            # are one key, and the message should not look like a false alarm.
            line, first = first_line[key]
            here = key_tok.lexeme or key
            spelled = (f"; written {first!r} there and {here!r} here"
                       if first != here else "")
            self._akan(f"duplicate key {key!r} (first defined on line "
                       f"{line}{spelled})", key_tok)
        first_line[key] = (key_tok.line, key_tok.lexeme or key)
        return key

    def _pair(self, first_line: dict[str, tuple[int, str]]) -> Pair:
        key_tok = self._advance()                # NAME
        label = self._advance() if self._at("LABEL") else None
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
        return Pair(key_tok.line, key_tok.col, key,
                    self._slot(label, value, key_tok), key_tok.lexeme,
                    named=key_tok.kind == "NAME")

    def _slot(self, label: Token | None, value: Node, key_tok: Token) -> Node:
        """GRAMMAR §G7: a labeled pair's value is its slot's overrides, a
        mapping — `{}` when there are none."""
        if label is None:
            return value
        key = key_tok.lexeme or key_tok.value
        if not isinstance(value, Mapping):
            self._akan(f"{key}{label.lexeme}: a slot's value is its "
                       f"overrides, a mapping; write {{}} for none",
                       _at_node(value, label))
        return Slot(label.line, label.col, label.value, [value],
                    label.lexeme, key)

    def _frame_body(self, marker: Token, parse_body, what: str) -> Node:
        """`MARKER INDENT [ NEWLINE ] body DEDENT` (GRAMMAR §G6).

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
            if tok.kind == "PLUS" or self._at_key():
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
            if tok.kind == "DASH" or self._at_key():
                self._akan_mixed("PLUS", tok)
            self._akan(f"expected a multimap entry ('+ '), found "
                       f"{_describe(tok)}")
        return MultiMap(first.line, first.col, entries)

    def _mmap_entry(self) -> Pair:
        """Exactly one pair (GRAMMAR §G7).  Keys repeat *across* entries."""
        tok = self._peek()
        if not self._at_key():
            if tok.kind in _SCALAR_KINDS or tok.kind in ("LBRACKET", "LBRACE"):
                self._akan("a multimap entry is a 'key: value' pair, not a "
                           "bare value")
            self._akan(f"expected a key, found {_describe(tok)}")
        if self._peek(1).kind == "LABEL":
            self._akan("a slot in a multimap entry is reserved (SPEC §9): "
                       "a slot is found by its key, and a multimap's keys "
                       "repeat", self._peek(1))
        pair = self._pair({})                    # no cross-entry dup check
        if self._at_key():
            self._akan("a multimap entry holds one key: value pair; indent it "
                       "under the key, or open a new '+ ' entry")
        return pair

    # -- flow level ----------------------------------------------------------
    def _flow_value(self) -> Node:
        return self._expression(allow_ref=False)

    def _expression(self, *, allow_ref=True) -> Node:
        value = self._or_expression()
        if isinstance(value, Copy) and getattr(value, "implicit", False):
            if not allow_ref:
                text = value.ref
                if "." not in text and "[" not in text and "?" not in text:
                    self._akan(_bare_word_msg(text), _at_node(value, self._peek()))
                try:
                    parse_ref(text)
                    hint = f", or ({text}) for a copy of that value"
                except RefError:
                    hint = ""
                self._akan(f"{text!r} is a bare word, and yapyon has no plain "
                           f"scalars: write \"{text}\" for the text{hint}",
                           _at_node(value, self._peek()))
            try:
                parse_ref(value.ref)
            except RefError as exc:
                self._akan(str(exc), _at_node(value, self._peek()))
        return value

    def _expr(self, at, op, args, value=None):
        from ._expressions import source
        node = Expression(at.line, at.col, op, args, value)
        node.lexeme = source(node)
        return node

    def _or_expression(self):
        value = self._and_expression()
        while self._at("OR"):
            op = self._advance()
            value = self._expr(op, "or", [value, self._and_expression()])
        return value

    def _and_expression(self):
        value = self._not_expression()
        while self._at("AND"):
            op = self._advance()
            value = self._expr(op, "and", [value, self._not_expression()])
        return value

    def _not_expression(self):
        if self._at("NOT") and self._peek(1).kind != "IN":
            op = self._advance()
            return self._expr(op, "not", [self._not_expression()])
        return self._comparison()

    def _comparison(self):
        first = self._peek()
        args, ops = [self._postfix()], []
        while self._at("COMPARE", "IN", "IS") or (
                self._at("NOT") and self._peek(1).kind == "IN"):
            tok = self._advance()
            op = tok.value if tok.kind == "COMPARE" else tok.kind.lower()
            if tok.kind == "NOT":
                self._advance()
                op = "not in"
            if tok.kind == "IS":
                if self._at("NOT"):
                    self._advance()
                    op = "is not"
            right = self._postfix()
            if tok.kind == "IS" and not (isinstance(right, Scalar) and right.type == "none"):
                self._akan("is and is not test None, not object identity", tok)
            ops.append(op)
            args.append(right)
        return self._expr(first, "compare", args, ops) if ops else args[0]

    def _postfix(self):
        value = self._primary()
        while self._at("LBRACKET", "DOT", "SAFE_DOT"):
            tok = self._advance()
            if tok.kind == "LBRACKET":
                key = self._expression()
                if isinstance(key, Scalar) and key.lexeme.startswith("+"):
                    self._akan("a literal index has no '+' sign", tok)
                self._expect("RBRACKET", "expected ']' after the subscript")
                value = self._expr(tok, "subscript", [value, key])
            else:
                tail = self._peek()
                if tail.kind not in ("NAME", "REF", "COPY"):
                    self._akan("expected a name or call after the dot", tail)
                self._advance()
                text = tail.value if tail.kind != "NAME" else tail.lexeme
                try:
                    parsed = parse_ref(text)
                except RefError as exc:
                    self._akan(str(exc), tail)
                if parsed.root or parsed.parents or parsed.key or parsed.env:
                    self._akan("an anchor or environment variable cannot follow a dot", tail)
                if tok.kind == "SAFE_DOT":
                    first = parsed.call
                    while first is not None and first.receiver and first.args[0].call is not None:
                        first = first.args[0].call
                    if first is None or first.receiver:
                        self._akan("'?.' comes only before a call", tok)
                value = self._expr(tok, "suffix", [value],
                                   (text, tok.kind == "SAFE_DOT"))
        return value

    def _primary(self):
        tok = self._peek()
        if tok.kind in ("LCOMP", "DCOMP", "MCOMP"):
            return self._flow_comprehension()
        if tok.kind == "LBRACKET":
            return self._flow_list()
        if tok.kind == "LBRACE":
            return self._flow_map()
        if tok.kind == "LPAREN":
            return self._group()
        if tok.kind in _SCALAR_KINDS or tok.kind in ("QKEY", "YKEY"):
            return self._scalar()
        if tok.kind in ("NAME", "REF"):
            self._advance()
            text = tok.lexeme or tok.value
            node = Copy(tok.line, tok.col, text, text)
            node.implicit = True
            return node
        self._akan(f"expected a value, found {_describe(tok)}")

    def _clause(self, at, kind, body, key=None, *, block=False):
        self._expect("FOR", "expected one for clause after the comprehension head")
        names, spellings = [], []
        while True:
            name = self._expect("NAME", "expected an iteration variable")
            if is_dunder(name.value):
                self._akan("dunder names belong to yapyon, not iteration bindings", name)
            if name.value in names:
                self._akan("iteration binding names must be distinct", name)
            names.append(name.value)
            spellings.append(name.lexeme or name.value)
            if not self._at("COMMA"):
                break
            self._advance()
            if len(names) == 2:
                self._akan("iteration binds one item or one key/value pair")
        self._expect("IN", "expected in after the iteration binding")
        iterable = self._expression()
        if block:
            self._expect("NEWLINE", "expected end of line after the for clause")
        predicate = None
        if self._at("IF"):
            self._advance()
            predicate = self._expression()
            if block:
                self._expect("NEWLINE", "expected end of line after the if clause")
        if self._at("FOR", "IF"):
            self._akan("a comprehension has one for clause and at most one if clause")
        cls = DictionaryComprehension if kind == "dict" else Comprehension
        node = cls(at.line, at.col, kind, names, iterable, body, predicate, key)
        node.binding_lexemes = tuple(spellings)
        from ._expressions import source
        node.lexeme = source(node)
        return node

    def _flow_comprehension(self):
        at = self._advance()
        kind = {"LCOMP": "list", "DCOMP": "dict", "MCOMP": "multimap"}[at.kind]
        if kind == "multimap":
            self._expect("PLUS", "expected '+' marking the multimap")
        head = self._expression()
        key = None
        if kind != "list":
            key = head
            self._expect("COLON", "expected ':' between the computed key and value")
            head = self._expression()
        node = self._clause(at, kind, head, key)
        self._expect("RBRACKET" if kind == "list" else "RBRACE",
                     "expected the end of the comprehension")
        return node

    def _block_comprehension(self):
        at = self._advance()
        key = None
        if at.value == "list":
            marker = self._expect("DASH", "a block list comprehension has one '-' head")
            def item():
                if self._at_key() or self._at("DASH", "PLUS", "BCOMP"):
                    return self._block_value()
                value = self._expression()
                self._expect("NEWLINE", "expected end of line after the head item")
                return value
            body = self._frame_body(marker, item, "comprehension item")
        else:
            marker = self._advance() if at.value == "multimap" else None
            def head():
                nonlocal key
                key = self._expression()
                self._expect("COLON", "expected ':' after the comprehension key")
                if self._at("NEWLINE"):
                    self._advance()
                    self._expect("INDENT", "indent the comprehension's value")
                    value = self._block_value()
                    self._expect("DEDENT", "expected the end of the value")
                else:
                    value = self._expression()
                    self._expect("NEWLINE", "expected end of line after the head")
                return value
            body = self._frame_body(marker, head, "comprehension entry") if marker else head()
        return self._clause(at, at.value, body, key, block=True)

    def _group(self) -> Node:
        """`(value)` is the value (SPEC §5.6), as in Python. A tuple is not:
        yapyon has none, so `()` and a comma are akan."""
        opener = self._advance()                 # LPAREN
        if self._at("RPAREN"):
            self._akan("'()' would be an empty tuple, and yapyon has no "
                       "tuples", opener)
        value = self._expression()
        if isinstance(value, Copy):
            value.implicit = False
        if self._at("COMMA"):
            self._akan("a comma in parentheses would make a tuple, and "
                       "yapyon has no tuples; use a list", self._peek())
        self._expect("RPAREN", f"expected ')' to close the '(' at line "
                     f"{opener.line}, col {opener.col}, found "
                     f"{_describe(self._peek())}")
        if isinstance(value, Expression) and value.op in ("subscript", "suffix"):
            return self._expr(opener, "group", [value])
        return value

    def _scalar(self) -> Node:
        tok = self._advance()
        if tok.kind == "COPY":
            return Copy(tok.line, tok.col, tok.value, tok.lexeme)
        if tok.kind in ("YSTR", "YBSTR", "YTSTR", "YKEY"):
            return YString(tok.line, tok.col, tok.prefix, list(tok.parts),
                           tok.lexeme)
        if tok.kind in ("STRING", "QKEY"):
            return Scalar(tok.line, tok.col, "str", tok.value,
                          lexeme=tok.lexeme, prefix=tok.prefix)
        if tok.kind == "BYTES":
            return Scalar(tok.line, tok.col, "bytes", tok.value,
                          lexeme=tok.lexeme, prefix=tok.prefix)
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

    def _flow_map(self) -> Node:
        opener = self._advance()                 # LBRACE
        multimap = self._at("PLUS")
        if multimap:
            self._advance()
        pairs: list[Pair] = []
        first_line: dict[str, tuple[int, str]] = {}
        while not self._at("RBRACE"):
            key_tok = self._peek()
            if key_tok.kind not in ("NAME", "QKEY", "YKEY"):
                self._akan(_bad_key_msg(key_tok), key_tok)
            self._advance()
            label = self._advance() if self._at("LABEL") else None
            self._expect("COLON", f"expected ':' after the key "
                                  f"{key_tok.value!r}")
            if multimap and label is not None:
                self._akan("a slot in a multimap entry is reserved (SPEC §9)", label)
            key = self._check_key(key_tok, {} if multimap else first_line)
            value = self._slot(label, self._flow_value(), key_tok)
            pairs.append(Pair(key_tok.line, key_tok.col, key, value,
                              key_tok.lexeme, named=key_tok.kind == "NAME"))
            if self._at("COMMA"):
                self._advance()                  # trailing comma is fine
            elif not self._at("RBRACE"):
                self._akan(f"expected ',' or '}}' in a flow mapping, found "
                           f"{_describe(self._peek())} (commas are mandatory)")
        self._advance()                          # RBRACE
        cls = MultiMap if multimap else Mapping
        return cls(opener.line, opener.col, pairs)


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
    if isinstance(node, Expression):
        from ._expressions import source
        return f"{pad}{node.type} {source(node)} {where}"
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
    if isinstance(node, Slot):
        out = [f"{pad}slot {node.lexeme or '<>'} {where}"]
        for layer in node.layers:
            out.append(dump(layer, level + 1))
        return "\n".join(out)
    if isinstance(node, Copy):
        return f"{pad}copy ({node.ref}) {where}"
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
