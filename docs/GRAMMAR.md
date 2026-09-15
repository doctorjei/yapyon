# yapyon — grammar v0.1

> YAMLちゃうで。やぴょんやぴょん。
> *It's not YAML. It's yapyon.*

**This document answers one question: are these bytes well-formed yapyon?**

It is **self-contained and normative for syntax**. Everything needed to write
a yapyon parser is here, and nothing here depends on any other document. What
well-formed bytes *mean* — the type model, resolution, serializers, templates,
conformance forms — is the subject of the companion specification, which
references this document and never restates a production from it.

*(That pointer is a courtesy, not a dependency. If you are implementing a
reader, you need this file and no other.)*

Sections are numbered **§G1**–**§G8** so that a citation can never be confused
with a section of the specification.

## §G1 Scope, conformance, and notation

An implementation **conforms to this document** if it accepts exactly the
documents this document generates and rejects every other byte sequence.

**Errors are called akan**, are raised at the **line and column of the
offending character**, and are never warnings and never silent
reinterpretations. Where a fix is mechanical, an implementation should name it
in the message. A second register, **shiran**, marks input that is well-formed
but suspicious; a shiran never changes whether a document is accepted. This
document specifies exactly one shiran (§G5.4).

Grammar fragments are EBNF: `::=` defines, `|` alternates, `?` optional, `*`
zero or more, `+` one or more, `( )` groups, `" "` quotes a literal. Names in
`UPPERCASE` are tokens produced by §G3–§G4; names in `lower_case` are
non-terminals.

Two properties hold throughout and are relied on by the rest of the document:

- **All context-sensitivity is lexical.** Indentation, frames and string
  interiors are resolved while producing the token stream (§G3–§G4). The
  phrase grammar (§G6) is a plain LL(1) grammar over that stream, with no
  feedback from parser to lexer.
- **One spelling per meaning.** Where a construct could reasonably be written
  more than one way, exactly one spelling is legal and the others are akan.
  Spelling multiplicity is deliberately not a feature.

## §G2 Source text

- **Encoding is UTF-8.** The interior of a document is Unicode.
- **Comments** run from `#` to end of line, outside string literals.
- **Blank lines and comment-only lines are ignored entirely** and produce no
  tokens.
- A document is a sequence of lines. Line endings are `\n`; a `\r\n` pair is
  accepted and treated as a single line ending.

## §G3 Lines, indentation, and frames

Indentation is resolved by an **indent stack** that emits `INDENT` and
`DEDENT` tokens, and a `NEWLINE` token at the end of each token-bearing line.

- **Indentation is spaces only.** A tab in indentation is **akan**.
- **Dash frames.** A `-` at the start of a line's content, followed by a space
  or end of line, emits `DASH INDENT` and opens a frame **anchored at the
  dash's column + 2**. The frame closes (`DEDENT`) when a line's indentation
  falls below the anchor. Frames stack: `- - "x"` is two frames.
- **Plus frames.** A `+` at the start of a line's content, followed by a space
  or end of line, emits `PLUS INDENT` and opens a frame by the same rule
  (anchor = the plus's column + 2). Frames of both kinds stack and interleave:
  `- + a: 1` opens a dash frame holding a plus frame.
- **A marker needs its space.** `-` and `+` open a frame only when a space or
  end of line follows. `-5` and `+5` are signed numbers, not frames.
- **Flow suppression.** Inside `[` `]` or `{` `}`, newlines, indentation and
  the dash and plus rules are suppressed entirely — Python's implicit line
  joining. Commas are mandatory separators and a single trailing comma is
  permitted.

## §G4 Tokens

### §G4.1 Names and keywords

- **`KEYWORD`** is one of `True`, `False`, `None`. Capitalized exactly so.
- **`NAME`** is a **UAX #31 identifier**: the first character is `XID_Start`
  or `_`; every later character is `XID_Continue`. Names are matched by
  **exact codepoints** — no NFKC normalization, so visually distinct names
  never silently collide, and NFD text (`e` + U+0301) is an ordinary name
  rather than an error. A bare word that is not a `KEYWORD` is a `NAME`.

  *In Python, `str.isidentifier()` is exactly this test and is the conforming
  implementation; `("a" + ch).isidentifier()` tests a single character for
  `XID_Continue`. `str.isalnum()` is **not** this test — it admits `²` and
  rejects combining marks, wrongly in both directions.*

- **One predicate, two uses.** The same test defines a `NAME` and a hole's
  reference segment (§G5). An implementation **must apply one predicate to
  both**, not two. They are the same rule, and written twice they drift.

- **Implementations must document the Unicode version** their identifier
  tables come from. A codepoint assigned later may be rejected by an older
  implementation. This is the one place where a document's meaning leans on
  something outside its own bytes, and it is why this rule names a standard
  rather than a language: "whatever the host language accepts" would make the
  answer depend on the interpreter.

  An implementation that **inherits** its tables from a host runtime cannot
  name one version, because the host varies per install. It must instead
  document its **floor** — the version guaranteed by the oldest runtime it
  supports — and state that newer hosts accept more. A document whose
  identifiers stay within the floor means the same thing on every install of
  that implementation; beyond the floor, it does not.

  *The reference implementation inherits its tables from the host interpreter
  and documents a floor of **Unicode 14.0.0**, the version carried by the
  oldest Python it supports (3.11). It also exports the running install's
  actual version, so a consumer can ask rather than assume.*

### §G4.2 The reserved dunder vocabulary

A name that **begins and ends with `__`** belongs to yapyon rather than to the
document. `__` and `___` count; `_foo`, `__foo` and `foo__` do not.

- **A dunder name is akan as a key** (§G7).
- **In a hole reference, exactly these are defined**, and every other dunder
  name is akan:

  | Name | Where it is legal |
  |---|---|
  | `__ROOT__` | leads a reference (§G5) |
  | `__PARENT__` | leads a reference, and repeats |
  | `__KEY__` | ends a reference |
  | `__AS_JSON__()` `__AS_TOML__()` `__AS_YAML__()` | ends a reference |

Reserving the whole shape rather than a list of names is deliberate: widening
the reserved set later would break documents, while narrowing it never can.

### §G4.3 Numbers

`INT` and `FLOAT` follow **Python's rules** for spelling:

| Token | Spellings |
|---|---|
| `INT` | decimal, `0x`, `0o`, `0b`, `_` group separators, optional sign |
| `FLOAT` | `3.10`, `1e-6`, `.5`, `3.`, `_` group separators, optional sign |

- **There is no `inf` or `nan` spelling.** Python has none either; they are
  reachable in Python only through a function call.
- **The digits of a numeric literal are ASCII**, as in Python source. Other
  Unicode digits (`٣`, U+0663) are `XID_Continue`, so they are legal *inside*
  a name (§G4.1) and nowhere else. `str.isdigit()` accepts them and is
  therefore the wrong test for a number.
- **A numeric or keyword token retains its source lexeme** alongside its
  value. An implementation must keep the characters the author wrote: `3.10`,
  `0x1f` and `1_000` are distinguishable after tokenizing. *(Consumers of this
  requirement are defined in the specification; a conforming lexer simply
  keeps the spelling.)*

### §G4.4 String literals: quoting forms

- **`'...'` and `"..."`** are single-line. A raw newline inside is **akan**.
- **`"""..."""`** is multi-line, with **content-anchored dedent**. The literal
  may open anywhere a value may appear — on its own line, or inline after a
  key.

  - The **anchor** is the indentation of the first non-blank *continuation*
    line (the first line after the one the literal opens on). The opening
    delimiter's own column is irrelevant, so both of these are clean:

    ```
    motd: """Welcome.
          Please behave."""      # anchor 6
    motd: """Welcome.
             Please behave."""   # anchor 9 — same value
    ```

  - A newline immediately following the opening delimiter is **dropped**, so
    an own-line block does not begin with `\n`.
  - Content begins immediately after the opening delimiter; text on the
    opening line is never dedented, having no leading whitespace to strip.
  - After each newline, exactly `anchor` leading spaces are stripped.
    Indentation deeper than the anchor is content and survives.
  - A non-blank line with *fewer* leading spaces than the anchor is **akan**
    ("outdents past the string's indentation"). **Blank lines are exempt** and
    set no anchor.
  - The closing delimiter may not sit shallower than the anchor: **akan**.
  - Consequence: re-indenting a block moves anchor and content together, so a
    block string's value is indentation-relocatable.

  This dedent is resolved entirely while scanning the literal, in one pass.

  *Precedent: Julia, CoffeeScript and Nix all permit an inline opening and
  derive the strip from the content lines with the first line exempt; Julia
  and CoffeeScript also drop the newline after the delimiter. yapyon differs
  from all three in taking the anchor from **one line** — the first content
  line — rather than the minimum over all of them, so a later under-indented
  line is an error at the point of the mistake rather than a silent
  re-indentation of the whole block. Java, C# and Swift forbid the inline
  opening outright.*

- **A backslash consumes the character that follows it** while scanning, so an
  escaped delimiter does not end the literal: `"a\"b"` is one string. This is
  a scanning rule and applies to raw strings too — `r"a\"b"` keeps the
  backslash in its value and still does not end early, which is Python's
  behaviour. Backslash-newline is excluded from this rule so that the dedent
  above still sees the newline; the continuation is joined afterwards.

### §G4.5 Escape sequences

In non-raw strings, Python's escape table **minus `\N{...}`**:

`\\` `\'` `\"` `\a` `\b` `\f` `\n` `\r` `\t` `\v` &nbsp; `\ooo` (octal) &nbsp;
`\xHH` &nbsp; `\uXXXX` `\UXXXXXXXX` (text only) &nbsp; backslash-newline
(line continuation).

**Backslash-newline joins the lines, dropping both characters** — Python's
rule exactly. It is reachable **only inside `"""`**, and not by exception: a
single-line string akans on the raw newline (§G4.4) before the escape is ever
considered, so the two rules need not know about each other. Inside a raw
string the backslash is literal, so `r"""a\` + newline + `b"""` keeps all
three characters; that too is Python's rule, and it is why the continuation
belongs to the escape table rather than to `"""`.

Stricter than Python in three places:

- An **unknown escape is akan.** Python keeps the backslash and warns. This
  reserves the escape namespace for future versions.
- A `\u`/`\U` escape yielding a **surrogate code point is akan** — yapyon
  strings are sequences of Unicode scalar values. This intentionally rejects
  JSON-style surrogate pairs; write `\U0001F600` directly.
- In a bytes literal, an escape whose **value exceeds 255 is akan.** Python
  truncates `b"\777"` to `b"\xff"` with a warning.

**Bytes literals** (`b"..."`) take the same table without `\u`/`\U`. Any
**literal** character above U+007F is akan — spell it `\xHH`. The restriction
is on literal source characters, not on escape values: `b"\x89"` is the point
of `\xHH`.

**`b64"..."`** content must be valid standard base64; interior whitespace is
permitted and ignored, and invalid content is akan at parse time.

### §G4.6 Prefixes

**Canonical spellings only.** Each prefix has exactly one legal spelling:
lowercase, in the order given. Python accepts `br` as well as `rb`, and any
capitalization (`Rb`, `BR`); yapyon accepts neither variant. An identifier
immediately adjacent to a quote is consumed as a prefix; whitespace between
them yields two tokens.

| Prefix | Token | Formal name | Spoken |
|---|---|---|---|
| *(none)* | `STRING` | string | — |
| `b` | `BYTES` | bytes literal | — |
| `b64` | `BYTES` | base64 bytes literal | — |
| `r` | `STRING` | raw string | — |
| `rb` | `BYTES` | raw bytes | — |
| `y` | `YSTR` | yapyon string | y-string |
| `yb` | `YBSTR` | yapyon byte string | yeeb-string |
| `yt` | `YTSTR` | yapyon template string | yeet-string |
| `ry` | `YSTR` | raw yapyon string | ree-string |

*The `y` is a long-e glide wherever it sits, so its position marks
composition order.*

A `BYTES` token records **which of `b` / `b64` / `rb`** produced it, and a
`YSTR` token records whether it was raw. That distinction is not recoverable
from the value and implementations must keep it.

**Akan, with hints:** `f` ("yapyon has no f-strings"), `t` ("use yt"), `u`,
and every non-canonical order or capitalization (`br` → "use rb", `yr`).
**Reserved:** `yb64`, `ytb`.

**Plain strings are guaranteed inert.** `"{name}"` is six characters under all
compositions, forever. Holes exist only in the four y-family literals.

### §G4.7 Holes

Inside a `YSTR`, `YBSTR` or `YTSTR` literal, braces delimit **holes**.

- **Holes are recognised before escapes decode.** A hole is structure, found
  in the source; an escape that produces a brace is content and never opens
  one, so `y"\x7bname\x7d"` is the six characters `{name}`. This is Python's
  own layering for f-strings, and it is what makes `\{` an akan rather than a
  second way to spell a literal brace.
- **`{{` and `}}` are the only brace escapes.** A backslash never escapes a
  brace, including in non-raw strings: `\{` is akan.
- A `{` that does not open a well-formed hole is **akan**; for `{2,3}`-shaped
  content the message points at `{{n,m}}`. A lone `}` is **akan**.
- A hole's interior is a **reference** (§G5) and nothing else.
- **Braces are the only structure.** Inside a y-family literal, `$`, `%`,
  backtick and every other character are ordinary content. `y"$HOME/x"` is the
  eight characters `$HOME/x` and no substitution of any kind occurs; `y"{$HOME}"`
  is akan, because `$HOME` is not a `NAME` and so cannot be a segment. There is
  exactly one interpolation syntax, and it is the brace.

## §G5 Reference grammar

This is the interior of a hole. **It is one grammar, shared by all four
y-family prefixes**, and an implementation should have exactly one
implementation of it.

```ebnf
hole        ::= "{" ref "}"

ref         ::= key_ref | value_ref

key_ref     ::= parents "." "__KEY__"
              | "__KEY__"

value_ref   ::= path | serialized

path        ::= ( anchor | SEG ) step*

serialized  ::= anchor step+ "." serializer
              | SEG    step* "." serializer

anchor      ::= "__ROOT__" | parents

parents     ::= "__PARENT__" ( "." "__PARENT__" )*

step        ::= "." SEG | subscript

subscript   ::= "[" sub "]"

sub         ::= STRING | INDEX | ref

serializer  ::= "__AS_JSON__" "(" ")"
              | "__AS_TOML__" "(" ")"
              | "__AS_YAML__" "(" ")"

SEG         ::= NAME, excluding every dunder name (§G4.2)
INDEX       ::= INT, unsigned
```

Two asymmetries in that production are deliberate and are the kind of thing a
looser grammar would have hidden:

- **`serialized` requires at least one step after an anchor.** `{a.__AS_X__()}`
  and `{__ROOT__.a.__AS_X__()}` are legal; `{__ROOT__.__AS_X__()}` and
  `{__PARENT__.__AS_X__()}` are **not**. An anchor is always an ancestor of
  the hole naming it, so encoding one would require the value being encoded —
  the reference is circular in every document, which is why it is refused
  here, in the grammar, rather than left for a resolver to discover.
- **`INDEX` is unsigned**, because negative indices are reserved (§G5.1).
  Spelling that in the production rather than beside it is the difference
  between a grammar and a grammar with a footnote.

The production is **complete**: every form an implementation accepts is
generated by it, and every form it generates is accepted. *That claim is
machine-checked against the reference implementation over a combinatorial
corpus — a normative sentence with nothing executing it is indistinguishable
from a false one, and an earlier draft of this production could not generate
`{cfg.__AS_JSON__()}` at all.* The constraints that
earlier drafts carried as prose beside a looser production — that `__PARENT__`
leads and repeats, that `__KEY__` ends, that a serializer ends, that
`__ROOT__` may not follow anything — are expressed **in the grammar itself**,
which is why `SEG` excludes the dunder names rather than admitting them and
apologising afterwards.

### §G5.1 What each form admits

- **`a.b` is sugar for `a["b"]`.** The bracket is the general form and its
  contents yield a key; the dot is a shorthand whose domain is restricted to
  identifiers. They are not two constructs — one reduces to the other, which
  is why "canonical spellings only" (§G4.6) does not object.
- A **quoted literal** in a bracket is a key: `{a["b.c"]}` names the key
  `b.c`. Because the enclosing string's own delimiter would end that string, a
  key must be quoted with the *other* mark — `y"{a['b']}"` or `y'{a["b"]}'`.
  **Escapes inside a quoted key are reserved**; write the characters directly.
- An **integer** in a bracket is a list position: `{xs[0]}`. Brackets only —
  `{xs.0}` is akan, because `0` is not a `NAME` and `SEG` admits none. That
  restriction is exactly what keeps `a.b` ≡ `a["b"]` true. **Negative indices
  are reserved**: `{xs[-1]}` is akan.
- A **reference** in a bracket names the key, and nests without an extra rule:
  `{d[p]}`, `{a[b[c]]}`, `{a[__KEY__]}`.

### §G5.2 Akan inside a hole

- An **empty hole**, `{}`, and an empty segment (`a..b`, a leading dot).
- A **literal as the whole hole**: `{8080}` names nothing. A literal in *key
  position* is a different role and is legal — the axis is literal-vs-
  reference in key position, not static-vs-dynamic.
- A **keyword segment** (`True`, `False`, `None`): keywords are not keys
  (§G7), so such a segment could never name anything.
- An **undefined dunder** name: `{__foo__.a}`.
- **Format specs and conversions** — `{x:...}`, `{x!r}` — are akan and
  reserved.
- A **serializer that is not one of the three defined**, e.g.
  `{a.__AS_BOGUS__()}`, and a serializer with **nothing to encode**,
  `{__AS_JSON__()}`.

### §G5.3 A note on borrowing

This is **Python-the-language's subscript**, not `str.format`'s. A format
string takes a bare literal in brackets *because it has no scope in which to
resolve a name*; a yapyon document has one, so `{d[p]}` may mean what Python
means by `d[p]` and nothing diverges.

### §G5.4 The one shiran

**`{a["bar"]}` where `bar` is an identifier is a shiran** — legal, equivalent,
but `{a.bar}` is the canonical spelling. The warning fires **only where the
bracket is avoidable**: `{a["b.c"]}`, `{xs[0]}`, `{d[p]}` and `{a[__KEY__]}`
are silent, because a dot could not have been written there.

A shiran never changes whether a document is accepted, and taking this one's
advice never changes what a document means.

## §G6 Phrase grammar

Over the token stream of §G3–§G4, the grammar is plain **LL(1)**:

```ebnf
document    ::= block_value EOF

block_value ::= block_map
              | block_seq
              | block_mmap
              | flow_value NEWLINE

block_map   ::= pair+
pair        ::= NAME COLON ( flow_value NEWLINE
                           | NEWLINE INDENT block_value DEDENT )

block_seq   ::= seq_item+
seq_item    ::= DASH INDENT [ NEWLINE ] item_body DEDENT
item_body   ::= block_value
              | INDENT block_value DEDENT

block_mmap  ::= mmap_entry+
mmap_entry  ::= PLUS INDENT [ NEWLINE ] entry_body DEDENT
entry_body  ::= pair
              | INDENT pair DEDENT

flow_value  ::= scalar | flow_list | flow_map
scalar      ::= STRING | BYTES | YSTR | YBSTR | YTSTR
              | INT | FLOAT | KEYWORD
flow_list   ::= LBRACKET [ flow_value (COMMA flow_value)* [COMMA] ] RBRACKET
flow_map    ::= LBRACE [ fpair (COMMA fpair)* [COMMA] ] RBRACE
fpair       ::= NAME COLON flow_value
```

- The optional `NEWLINE` after a marker is the **bare-marker form** (`-` or
  `+` alone on its line); the optional `INDENT … DEDENT` covers a body
  indented deeper than the frame's anchor. Both are layout, not meaning:
  `- 1` and `-` followed by an indented `1` are the same document, exactly as
  `k: 1` and `k:` followed by an indented `1` already are.
- **Any value is a valid document.** A tool wanting a mapping at the top level
  enforces that itself.
- **One document per file.** `---` and `...` are reserved tokens with no
  meaning. *(Reserved: multi-document streams.)*

Note that `scalar` has **eight** alternatives, of which five — `STRING`,
`BYTES`, `INT`, `FLOAT`, `KEYWORD` — are literals readable from their own
bytes, and three — `YSTR`, `YBSTR`, `YTSTR` — are not. That partition is exact
and has no other members; the specification builds a conformance form on it.

## §G7 Static rules

These are well-formedness rules that the phrase grammar cannot express. A
conforming implementation enforces all of them, and needs nothing beyond the
parse tree to do so.

- **Keys are bare `NAME`s.** Quoted keys, numeric keys and every other key
  form are akan. *(Reserved: quoted string keys.)*
- **Keywords are not keys.** `True: 1` is akan.
- **Dunder keys are akan** (§G4.2). A document may not define a name that
  begins and ends with `__`.
- **Duplicate keys within one mapping are akan.** A block whose keys repeat by
  design is a multimap and must say so with `+ `.
- **Each `+ ` frame holds exactly one `key: value` pair.** A second key inside
  one entry is akan: "a multimap entry holds one key: value pair; indent it
  under the key, or open a new `+ ` entry."
- **A block is a mapping, a sequence, or a multimap — never a mix.** Mixing
  `key:`, `- ` and `+ ` markers within one block is akan.
- **An empty item or entry is akan** — a marker, a newline, and nothing:
  "sequence item has no value (write None)". yapyon has no implicit null, and
  layout must not smuggle one back in.
- **An empty document is akan.** `document ::= block_value EOF` admits no
  empty production, and a file of only comments is empty.
- **An unquoted word in value position is akan**, always, and is never a
  string and never a boolean. There are no plain scalars. *(This is the single
  rule that makes YAML's implicit typing — the Norway problem —
  unrepresentable.)*

## §G8 What this document does not decide

Non-normative, and listed so that a reader knows where the edge is.

This document says nothing about what a document **means**: the type model,
how a hole's reference is resolved against the document, what a value splices
as, which splices are legal, what a `yt` hands to a consumer, what the three
serializers emit, which spelling a *writer* must choose among the several this
grammar admits, or what an implementation must state about the form it
implements. All of that is the companion specification's subject.

Two consequences worth stating plainly:

- **A document can be well-formed under this grammar and still be akan** when
  loaded — an unresolvable reference, an illegal splice, a cycle. This
  document's acceptance is necessary, not sufficient.
- **A parser written from this document alone is a useful artifact**, and that
  is the point of separating the two. It can tokenize, build a tree, and
  reject malformed input, without implementing resolution at all.

---

*Errors escalate as indifference (`shiran`), refusal (`akan`), and losing it
entirely (`yakamashiwa`, an implementation's own invariant). On success in
verbose mode: ええやん。*
