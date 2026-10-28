# yapyon — draft specification v0.6

> YAMLちゃうで。やぴょんやぴょん。
> *It's not YAML. It's yapyon.*

yapyon (やぴょん) is a data format combining Python-style typed literals with
YAML-like block structure. Its design goal, in one sentence: **the same bytes
mean the same data, to every parser, on every machine, always.**

## How this document relates to the grammar

yapyon is specified in **two documents**:

| | answers | status |
|---|---|---|
| **`GRAMMAR.md`** | *are these bytes well-formed yapyon?* | self-contained, normative for syntax |
| **this document** | *what do well-formed bytes mean?* | normative for meaning |

**References run one way.** This document cites the grammar; the grammar cites
nothing. A grammar document exists so that someone can write a parser from it
— if it were not self-contained it would fail at its only job, and two
documents that reference each other drift until neither is trustworthy.

**This document never restates a production.** Where syntax is at issue it
cites `GRAMMAR §Gn` and moves on. Sections below that consist only of such a
citation are kept at their original numbers on purpose, so that existing
references to them still land in the right place.

Sections marked *(reserved)* name syntax deliberately akan in v0.6 but held
for future versions.

A yapyon document is one of **four tiers** (ehmon 2): a **record**, in
which every leaf element has a literal value (§12); a **ledger**, which
also splices, applies the format's built-in functions (§5), and composes
values (§16.5); a
**template**, which also holds template strings (§6) or slots (§15), or reads the
environment of the process loading it (§5.1.3); and an **assembly**, which also calls functions declared in a
contract (§13). Records and ledgers are **basic**: their own bytes finish
them. Templates and assemblies are **extra**: something outside finishes
them. §12
states what an implementation of each must support.

---

## 1. Ehmon

*これ、ええもんやでー Jei*

Every rule in both documents follows from seven guiding principles, the
**ehmon** (ええもん, "the good stuff"):

1. **Precision.** A value's type is fixed by its syntax or by a declared
   contract (§13) — for a copy (§5.6), by the syntax of the value it
   copies; it is never inferred from bare text. There are no plain
   scalars: a bare path as an ordinary value is akan, never implicitly a
   string or boolean. Calls (§5.6), expressions, and comprehensions (§16)
   compute typed values; comprehension result kinds are visible in their
   delimiters or block markers. (YAML's implicit typing — the Norway problem — is
   unrepresentable.)
2. **Reducibility.** Computation is driven by data and yields a document. A
   **record** computes nothing: every leaf is a literal, and loading one
   needs no resolver (§12). A **ledger** — a record with references to
   itself — splices named values into strings, copies named values whole
   (§5.6), constructs and composes values and evaluates data expressions
   (§16), and applies only the format's own built-ins — its encodings and casts
   (§5.1.2, §5.1.5) — and reduces to a record that is the same on every system. A **template** is finished by something outside
   the document: it may read the environment of the process loading it
   (§5.1.3), and reduces to a record given that environment, and it may
   hold template strings (§6), whose parts the consumer joins, and slots
   (§15), which the consumer fills, and reduces to a record given those
   fills. An **assembly** may also apply the functions its contract
   declares (§13), and reduces to a record given that contract and
   environment.
3. **Independence.** A document's meaning depends on nothing it does not
   declare. A **record** or a **ledger** depends only on its own bytes. A
   **template** may depend also on the environment it is loaded in, and
   only on variables it names, each at its reference (§5.1.3), and on what
   fills its slots, each named at the slot by its label (§15). An **assembly**
   depends also on the contract it is loaded with: every function it calls
   is named at its call site and declared, with its types, in that
   contract (§13). There is no ambient scope at the format level, and
   nothing reaches a document undeclared. (Loaders and tools may layer such
   things above the format.)
4. **Closure.** A splice is legal iff the target's validity is closed under
   splicing there. (This is what excludes splicing into base64 streams.)
5. **Visibility.** Nothing crosses a type boundary without broadcasting how.
   Text never crosses silently into bytes; containers cross into text only
   via a serializer (§5.1.2, §13). A function (§13) call names the crossing
   explicitly.
6. **Consistency.** A Python spelling may be borrowed iff its meaning
   survives the removal of the enclosing program. `b`/`r` pass (and are held
   bit-exact with Python); `f`/`t`/`u` fail by definition and are akan with
   an explanatory message.
7. **Direction.** Errors yield direction — what is akan, which line and
   column — at load time, before any value reaches the consumer. Malformed
   input is never merely warned about or silently reinterpreted. Well-formed
   input may be `shiran` (§10) when it is probably a mistake, or costly
   enough that implementations may refuse it (§5.3).

---

## 2. Lexical structure

**Syntax: `GRAMMAR §G2`–`§G3`** (source encoding, comments, indentation, dash
and plus frames, flow suppression).

Nothing about lexical structure is semantic, so this section has no content of
its own. It is retained as a pointer.

---

## 3. Types

Nine core types. **Prefixes are *spellings*, not types** — the prefix table is
`GRAMMAR §G4.6`.

| Type | Spelled as | Notes |
|---|---|---|
| str | `'...'`, `"..."`, `"""..."""`, prefixed forms | quotes mandatory, always |
| int | `INT` | signed and unbounded, in decimal or five radixes |
| float | `FLOAT` | **no inf/nan spellings** |
| bool | `True` / `False` | capitals |
| NoneType | `None` | one spelling |
| bytes | `b"..."`, `rb"..."`, and the stream literals `bin dna oct hex c32 b64` | eight spellings, one type |
| list | `[a, b]` flow, `- ` block | |
| dict | `{k: v}` flow, indented block | name or string keys (§7) |
| multimap | `+ ` block; `{+}` when empty | keyed and ordered; keys may repeat (§7.1) |

**Numbers are numbers; bytes are streams.** An integer literal in any radix
(`0b 0q 0o 0x 0z`, `GRAMMAR §G4.3`) is a signed, unbounded integer: leading
zeros mean nothing, and only `-` makes it negative — never two's complement,
so `0xffffffff` is 4294967295. There is one integer type and no unsigned
one. A bytes literal is a **stream** (§4.3): filled from the left, padded at
the end, and unsigned by nature. `0b0101` is the int 5; `bin'0101'` is the
byte `0x50`.

### 3.1 Long decimal integers

Converting a decimal integer to a value and back costs time that grows
faster than its length, so very long ones are limited, in two parts, as
§5.3 limits expansion:

| | Threshold | Exceeding it |
|---|---|---|
| **Warn threshold** — fixed by this specification | 4,300 decimal digits | **shiran** |
| **Refusal ceiling** — chosen by the implementation | implementation-defined, at or above the warn threshold | **akan**, naming the digit count and the ceiling |

The same limits apply wherever an integer becomes decimal text — splicing it
(§5.4) or writing it in any format. An implementation must document its
ceiling and **should** let a consumer move it. Integers in the other radixes
convert in linear time and are not limited. **The host's own limits must not
change meaning:** a decimal within the implementation's ceiling loads on
every host and in every environment.

The tenth type is **Template** (§6), produced only by `yt"..."`: a resolved
y-string handed over in parts rather than joined. It is never present in a
record (§12), since it needs the resolver.

**Every literal carries its source lexeme** beside its value — the grammar
requires the token to keep it (`GRAMMAR §G4.3`): a string with its quotes and
escapes, bytes with their prefix, a number or keyword as written, and a key
as spelled before folding (§7). The **value** is what a document means, and
it is what splicing (§5.4) and the JSON, TOML, and YAML serializers use. The
**lexeme** is how the author wrote it, and it is what a yapyon writer
reproduces (§4.4).

A loaded value does not record which spelling produced it — `bytes` has
several spellings and one type, and `0xff` and `255` are one `int`. A writer
that needs the spelling takes it from the parse tree, not the value.

---

## 4. String literals

**Syntax: `GRAMMAR §G4.4`** (quoting forms and the block dedent),
**`§G4.5`** (escape sequences), **`§G4.6`** (prefixes).

§4.1–§4.3 are retained as pointers; the one section here with semantic content
is §4.4.

### 4.1 Quoting forms

See `GRAMMAR §G4.4`.

### 4.2 Escape sequences

See `GRAMMAR §G4.5`.

### 4.3 Prefixes

See `GRAMMAR §G4.6`.

**Stream literals** spell bytes as symbols in a radix, one prefix per
radix:

| Prefix | Radix | Standard | `b"hi"` |
|---|---|---|---|
| `bin` | 2 | — | `0110100001101001` |
| `dna` | 4 | UCSC `.2bit` (`T C A G` = 0 1 2 3) | `CAATCAAC` |
| `oct` | 8 | Multibase Base8 (draft) | `320644` |
| `hex` | 16 | — | `6869` |
| `c32` | 32 | Crockford's Base32 | `D1MG` |
| `b64` | 64 | RFC 4648 Base64 | `aGk=` |

One name each, and no aliases. **Each accepts what its own standard
accepts**: Crockford's case-insensitivity, glyph aliases (`O` → 0, `I`/`L`
→ 1), and hyphens in `c32`; either case in `dna` and `hex`. Lowercase `dna`
carries no meaning — FASTA's soft-masking is not preserved. `c32` takes no
check symbol.

**Every stream is padded at the end.** Its symbols' bits, most significant
first, fill bytes from the left:

- With 1, 2, or 4 bits per symbol (`bin`, `dna`, `hex`), symbols that end
  partway through a byte are completed with zero bits: `hex'badf00d'` is
  `badf00d0`, the bytes `ba df 00 d0`; `bin'0101'` is `0x50`; `dna'GAC'` is
  `GACT`, `0xe4`.
- With 3, 5, or 6 (`oct`, `c32`, `b64`), the trailing bits that do not make a
  byte are **spare**, and must be zero (`GRAMMAR §G4.6`). `c32` departs here
  from Crockford's numeric reading, which pads at the front; that reading is
  the `0z` integer literal (§3).

**Spare bits must be zero, and the reason is agreement.** The standards say
they should be zero, and no encoder writes them otherwise. But they are not
an explicit mapping: Crockford's `O` → 0 is one, and is accepted, while a
spare bit maps to nothing. Host decoders disagree about them — Python's
`base64` with `validate=True` and Go's decoder accept nonzero spare bits,
Rust's `base64` crate refuses them — so leaving them to each implementation
would let the same document load in one and fail in another. `b"hi"` is
`aGk=`; `aGl=`, `aGm=`, and `aGn=` are akan at the literal, naming the
canonical spelling (ehmon 7).

### 4.4 Canonical spelling

The grammar admits several spellings of one value — `'x'` and `"x"`, `r"a\nb"`
and `"a\\nb"`, a block string and its escaped single-line form. That is
deliberate: an *author* should write what reads best. But a tool that **writes
yapyon** has no taste to exercise and must be deterministic, or two runs over
the same data produce different bytes and every diff is noise.

*(This section is here rather than in the grammar because its content is not a
well-formedness rule. Every spelling it rejects is well-formed; what it
constrains is a writer's choice among them, and it states its requirement as a
property of **loaded values**, which the grammar has no vocabulary for.)*

An implementation that emits yapyon **must write each literal's lexeme**
(§3), so every value the author spelled comes back spelled the same way:
`3.10` stays `3.10`, `0x1f` stays `0x1f`, `'x'` stays `'x'`, and a key stays
as written. Where a value has **no lexeme** — a resolved y-string, the result
of a call — the writer uses its **canonical form**:

- **Strings: double quotes**, with the `"""` block form used exactly when the
  value contains a newline and the block form can hold it unambiguously — that
  is, no whitespace-only-but-non-empty line, no `"""` in the content, and no
  trailing `"`. A value ending in a newline puts the closing delimiter on its
  own line at the anchor.
- **Escape only what must be escaped**: `\` and the enclosing quote, plus
  characters below U+0020 and U+007F. Everything else stays literal, so UTF-8
  remains readable — `"café"`, never `"café"`.
- **Numbers and keywords: their text under §5.4** — an `int` in decimal, a
  `float` as its shortest round-tripping form, `True`, `False`, and `None` as
  themselves.
- **Bytes: `b"..."`**, escaped as a string is, with every byte that is not
  printable ASCII as `\xhh`.

Whatever the source, **layout is the writer's**, since comments, blank lines,
indentation, and the choice of flow or block are not tokens and carry no
lexeme: a sequence that holds no mapping or multimap is written on one line if
it fits, and every other container in block form (§14.1); an empty container
has no block spelling and is written flow (`[]`, `{}`, `{+}`).

Normalization therefore **keeps every spelling and every value, and loses
only layout and comments**. The property an implementation must satisfy is
that **reloading its output yields data equal to reloading its input.**

**Comments do not survive**, and a conforming emitter is not required to
preserve them: comment-preserving round-trip is not specified in v0.6. An
emitter is a normalizer, not a round-tripper. *(Reserved: comment retention —
see §9.)*

**Record normalization and unfinished-source saving are different contracts.**
A replacement separator (§15.2; syntax in `GRAMMAR §G6`) annotates a field,
not its data type. An authored annotation survives normalization of direct
record source, though its input spacing need not survive. An explicit merge
expression (§16.5) is not a record, even with literal operands; a record
emitter must not evaluate it to make one. A proven literal record composed
through structural tree operations may still use the established
record-emission path without a resolver. That data-normalization path does
not replace §15.8's stronger source-history guarantee.

A source writer (§15.8) preserves unfinished contributions, field intent,
and meaningful grouping. Copies, expansion, and data serializers instead
consume completed composition into fresh data, retaining required literal
lexemes and key visibility, not pasting its operation program at a new
location. No key promotion or extra serializer wrapper is implied.

*Reference implementation: `yapyon.emit`, and `python -m yapyon record`, which
normalizes a record (§12); `Tree.to_source()` saves unfinished source (§15.8).*

---

## 5. The y-family: parse-time splicing

### 5.1 Holes and references

**Syntax: `GRAMMAR §G5`** — the `ref` production, what each bracket form
admits, what is akan inside a hole, and the avoidable-bracket shiran. One
grammar, shared by `y`, `yb`, `yt`, and `ry`.

What the grammar does not say is what a reference *names*. That is this
section and §5.2.

- **A subscript's contents yield a key**, and the three bracket forms differ
  in where the key comes from. A quoted literal *is* the key. An integer is a
  list position, and a **negative** one counts from the end as in Python —
  `{xs[-1]}` is the last element, `{xs[-0]}` is `{xs[0]}`. A position outside
  the list, at either end, is akan. A **reference** names the key: `{d[p]}` is "the value of `d`
  at the key stored in `p`".
- **An inner reference resolves in the scope of the y-string's own position**
  (§5.2), *not* in the scope of the node being indexed. So
  `{mind.dialects[protocol].api_uri}` means "the entry named by **my**
  protocol", which is the whole reason the form exists. If an inner reference
  resolves to an integer it indexes, exactly as a written integer would.
- **`__ROOT__` anchors at the document root** (§5.2). One definition, one
  scope: since a `yt` resolves against the document like any other y-family
  literal (§6), there is no second scope for it to mean something else in.
- A **call** applies a function to the values its arguments name — a
  built-in such as a serializer (§5.1.2), or a function a contract declares
  (§13).
- Holes contain **references, calls, and literal arguments**, and nothing
  else: no arithmetic, no operators, and no way to reach outside the
  document except the loading process's own environment (§5.1.3) and a
  declared function. The grammar admits nothing
  more, which is why it is small enough to be implemented identically twice.

### 5.1.1 Relative references: `__PARENT__` and `__KEY__`

`__ROOT__` names an absolute position; these two name relative ones. Their
syntax — that `__PARENT__` leads and repeats, that `__KEY__` ends a reference
— is `GRAMMAR §G5`.

- **`__PARENT__` moves one level outward.** It repeats because moving one
  level is all it does, so a chain is the only way to move several.
- **`__KEY__` names a key rather than a value.** Alone it is the key of the
  pair the hole sits in; after a `__PARENT__` chain it is the key of the block
  that many levels out. `{__PARENT__.__KEY__}` — the name of the enclosing
  block — is the useful form; the bare one is the surprising one.

  That `__KEY__` may follow only an anchor and never data traversal costs
  nothing: after `a.b` the key is the literal `b`, which the author has
  already written. *(Widening later is compatible where narrowing is not.)*

**Both climb the chain §5.2 searches.** Sequence and multimap levels are
transparent to them exactly as they are to the scope search — one notion of
nesting, not two. A list has no key for `__KEY__` to report in any case.

Climbing past the document root is **akan**: the root is not inside anything
and has no key of its own. `{__ROOT__.__KEY__}` is therefore akan too, and
says so.

`__KEY__` yields the key's text, including for a quoted or computed key
(§7). If that key is pending, the reference waits for it; a key depending on
itself is a cycle (§5.3). Its result is text, so splicing it into a `yb`
string is text→bytes and akan under ehmon 5, by the ordinary rule.

```
store: "/cfg"
personas:
  kimi:
    id:     y"{__PARENT__.__KEY__}"                      # "kimi"
    prompt: y"{__ROOT__.store}/{__PARENT__.__PARENT__.__KEY__}/{__PARENT__.__KEY__}.md"
```

The same text in every block, each resolving to its own name — which is what
these exist for. Without them a block cannot be moved or renamed without
editing its contents.

### 5.1.2 Serializers

A container cannot be spliced into text (§5.5), because there is no one
text form for it and picking one would be guessing. A **serializer** is
the author saying which they mean:

```
cfg:
  name: "gw"
  port: 8080
body: y"payload={cfg.__as_json__()}"
```

This is ehmon 5 (Visibility) — *containers cross into text only via a
serializer* — with the **document author** naming the encoding, in the
document, where a reader can see it.

**Serializers are the format's built-in functions.** Each is defined here,
by the format, under a dunder name, and is called exactly as a declared
function is (§13): its argument is type-checked before the call, it waits
for that argument to resolve, and its result is placed by §5.5. No
contract declares a serializer. Every implementation that resolves holes
provides all four; a records-only implementation (§12) has no holes to
call one from. The format defines:

| name | signature |
|---|---|
| `__as_json__` | `(Any) -> str` |
| `__as_toml__` | `(dict[str, Any] \| multimap[str, Any]) -> str` — a TOML document is a table, with no top-level form for a list or a single value |
| `__as_yaml__` | `(Any) -> str` |
| `__as_yapyon__` | `(Any) -> str` |

`__as_json__` and `__as_toml__` take one keyword argument, `lexemes`
(default `True`); `lexemes=False` writes no `@_lexemes` (§14.2). A
built-in's keyword arguments are its own and are listed here; it takes its
positional argument by position only.

`{cfg.__as_json__()}` is the receiver spelling of `{__as_json__(cfg)}`;
both are legal (§13.1). A result is a `str`, and a chain is checked like
any call: `{a.__as_json__().__as_yaml__()}` writes the JSON text as a YAML
string, while `{a.__as_json__().__as_toml__()}` is a type error at the
second link, since `__as_toml__` takes a table. **A dunder call that names
no built-in — these four, `__env__` (§5.1.3), or the casters and
`__get__` (§5.1.5) — is akan** at the call,
naming the built-ins that exist: a dunder call names a built-in or
nothing.

**Every serializer outputs a record.** Its output is the record (§12) its
argument resolves to — no holes, no calls, no templates — written in the
target format. A **`yt` anywhere in the argument is akan**, in every
serializer and in `expand_record`, with one message:

```
akan: yeeted yt; a record cannot hold a template's unjoined parts. Use a y-string to join them.
```

Joining it would render what §6 leaves to the consumer and make `yt`
silently mean `y`.

**An argument may not contain the call site** (§13.1). For a serializer
the commonest form is an anchor — `{__ROOT__.__as_json__()}` and
`{__PARENT__.__as_json__()}` are **akan**, while
`{__ROOT__.blk.__as_json__()}` and `{a.__as_json__()}` are legal. An anchor
is always an ancestor of the hole that names it, so encoding one needs the
value of the very y-string doing the encoding; no document resolves it.
The mistake is visible in the reference, so ehmon 7 puts the akan there,
at parse.

```
blk:
  a: 1
  me: y"{__PARENT__.__as_json__()}"     # akan: me = {"a":1,"me":<me>}
```

**Nothing useful is lost**: an anchor followed by any step leading away
from the hole is the shape authors want. *(Encoding "my parent, excluding
the pair I sit in" was considered and declined: it terminates, but makes
`__as_json__()` mean different things depending on where it is written.)*

**A target that is not resolved yet is not an encoding failure.** The
call defers to a later pass of §5.3's fixpoint (§13.1), so two serializers
whose targets hold each other are reported as the **cycle** they are,
naming every stuck reference.

**Every encoding is deterministic.** This section and §14 fix the output
exactly — layout included — so the same argument gives the same text from
every implementation. In all four, **keys are in document order and never
sorted** (order is data), and non-ASCII is left as itself.

**Where a format cannot carry a value directly, the serializer
approximates it — never refuses, and never guesses.** Each approximation
is fixed by §14, so it is the same everywhere. A reader that knows §14
recovers the yapyon value exactly; a reader that does not still receives
correct plain data in that format — never an error, and never a stream
that reads as a number. Each format's own mechanisms are used first (JSON-LD
shapes and I-JSON in JSON; `%TAG` handles onto YAML's standard tags), and
no marker carries yapyon's name. In brief (§14 has the detail):

- A **multimap** becomes an ordered list of one-entry mappings, marked as
  a multimap.
- **Bytes** become base64url text in JSON and TOML (with the spelling
  recorded beside them) and a tagged string in YAML.
- A **number** is written as its value; a non-decimal spelling is recorded
  beside it (JSON, TOML) or carried by a tag (YAML).
- **TOML** writes `None` by leaving the key out and recording it, and an
  integer outside 64 bits as a string, recorded as an integer.

**An implementation must not prune silently.** Dropping a key because its
value is `None` or `""` is a silent reinterpretation (ehmon 7), and "the
same bytes mean the same data" has to survive a serializer. A consumer
wanting that pruning does it to its own tree first. **The one omission the
format makes is TOML's `None`:** TOML has no null, so `__as_toml__()`
leaves the key out of its table and records it in that table's
`@_lexemes` as `"None"`, from which a yapyon-aware reader restores it.
Nothing is lost; a plain TOML reader sees the key absent, as TOML tools
commonly write a null.

**YAML is emitted defensively.** A scalar is written plain only when
nothing else could read it as another type — so `"no"`, `"3"`, and
`"true"` come out quoted, and in a flow sequence nothing that could end
or open a flow collection is left plain. yapyon exists partly because YAML
guesses; emitting into it must not hand that problem to the reader.

**`__as_yapyon__()` writes yapyon source**, so yapyon's own rules govern
it and it carries everything the data model has. Its output is the
argument as a record (§12) in the spelling §4.4 gives every yapyon writer:
each value as written — its lexeme, so `v: 3.10` stays `3.10` and
`hex'6869'` stays `hex'6869'` — and a value with no lexeme (a resolved
y-string, a function result) in its canonical form.

### 5.1.3 The environment: `$NAME` and `__env__`

A hole may read **the environment of the process loading the document** —
its own, and no other. Two spellings, one lookup:

```
paths:
  home: y"{$HOME}"
  config: y"{__env__('XDG_CONFIG_HOME', default_config)}/app"
  default_config: y"{$HOME}/.config"
```

- **`{$NAME}` is strict** (`GRAMMAR §G5`): the variable's value, and
  **akan** when it is not found — as Python's `os.environ["NAME"]` raises.
- **`__env__(var_name, fallback=None)` is a built-in**: the variable's
  value, or `fallback` when it is not found — as Python's
  `os.getenv(key, default=None)`. With one argument the fallback is `None`,
  which splices as `None` (§5.4) exactly as `f"{os.getenv('X')}"` does; an
  author writing it has asked for that. `var_name` is any argument that is
  a `str` — a literal or a reference — and anything else is a type error
  at the call (§13.3). A name `GRAMMAR §G5`'s `ENVNAME` cannot spell is
  reached only this way: `{__env__("ProgramFiles(x86)")}`. `fallback` may
  be given by position or as `fallback=`, and takes anything an argument
  can; like any argument it is resolved before the call (§13.1), whether
  or not it is used.
- **One lookup.** `{$X}` is `__env__("X")` except that not found is akan
  rather than a fallback. An implementation has one implementation of it.

What the lookup sees:

- **Values are `str`.** An empty value is a value — `""`, not "not set":
  some conventions treat the two alike (the XDG Base Directory
  Specification does), and that is not universal, so a document that wants
  it says so.
- **Not found means not set *or* not exposed** (§5.1.4). A variable the
  load does not expose is indistinguishable from one that is unset: `{$X}`
  is akan and `__env__` returns its fallback. The akan says so — *"`$X` is
  not set, or not exposed by this application"* — because the author who
  meets it is often not the one who can change what is exposed.
- **Names compare as the environment system compares them** (§5.1.4):
  exactly on a POSIX-compatible system, ignoring case on a
  Windows-compatible one. This applies to deciding whether a name is
  exposed and to finding it alike.
- **Read once per load.** Every reference in one load sees the same
  values, whatever the environment does meanwhile.
- **A value that is not valid Unicode text is akan** at the reference. A
  POSIX environment holds bytes, and a value that does not decode cannot be
  a `str` without inventing characters for it.
- **If the loader has turned environment access off**, every environment
  reference is akan — *"environment access is off"* — including `__env__`
  with a fallback: the fallback answers "not set", not "not allowed".

Where the value goes is the ordinary rules': it is a `str`, so it splices
into text (§5.4, §5.5), arrives as a part of a `yt` (§6) whose reference
reads `$NAME`, keys a mapping in a bracket (`{profiles[$USER]}` — a list
position it cannot be), and passes a parameter's type check as any `str`
does (§13.3). **Splicing cannot inject**: the value fills a place in a
document that is already parsed, so no value, whatever it holds, adds
structure the author did not write.

**A document that reads the environment is a template** (§12), and its
meaning depends on its bytes and that environment (ehmon 3): the same bytes
and the same environment give the same data. `expand_record` (§12) writes
the values it read into the record it produces — a secret it read is in
that record.

### 5.1.4 Exposed variables

**Not every variable is exposed.** A process's environment commonly holds
credentials — cloud keys, tokens, database URLs — and a document loaded
from somewhere less trusted than the process must not be able to read
them out. By default a load exposes the **standard variables** of its
environment system and nothing else. A loader may expose a different set,
wider or narrower, or turn environment access off; how it says so is an
API, not part of this specification.

The standard variables are not listed here. They are chosen by **criteria**,
applied to the environment system's own standards:

1. the variable is **defined by a standard of the environment system**
   (below);
2. it describes one of these, for the user or the session:
   - **location** — a directory, a file, or a list of them (`HOME`,
     `PATH`, `XDG_CONFIG_HOME`, `APPDATA`);
   - **identity** — of the user, machine, device, or computational
     instance (`LOGNAME`, `USERNAME`, `COMPUTERNAME`, `USERDOMAIN`);
   - **hardware and processing configuration** — what the machine is and
     how it runs programs (`PROCESSOR_ARCHITECTURE`,
     `NUMBER_OF_PROCESSORS`, `OS`);
   - **locale** — conventions for formatting, collation, and time (`LC_*`,
     `TZ`);
   - **language** — which language, and which message catalog, text
     appears in (`LANG`, `LANGUAGE`, `TEXTDOMAIN`);
   - **presentation** — how output is displayed (`TERM`, `COLUMNS`,
     `LINES`, `MSGVERB`);
3. it is **not** meant to carry a credential, token, or other secret.

**There are two environment systems.** An implementation is on a
**Windows-compatible** system when its host's environment is Windows'
(Python: `os.name == "nt"`) and on a **POSIX-compatible** one otherwise —
Linux, macOS, the BSDs, and environments that present POSIX on Windows
(Cygwin, MSYS2) alike. Each system's standards are pinned, as the Unicode
version is (`GRAMMAR §G4.1`), so that the criteria give the same answer
over time:

- **POSIX-compatible:** *The Open Group Base Specifications*, Issue 8
  (IEEE Std 1003.1-2024), Base Definitions, chapter 8, "Environment
  Variables"; and the **XDG Base Directory Specification**, version 0.8
  (freedesktop.org).
- **Windows-compatible:** the variables the **Win32 API reference**
  documents as set by Windows, pinned by commit in Microsoft's public
  documentation repositories:
  - the **standard** variables listed in the remarks of
    `DoEnvironmentSubst` — Microsoft's own term, "standard and … available
    to both interactive applications and services", and those "only
    available to interactive applications":
    <https://github.com/MicrosoftDocs/sdk-api/blob/39d86831b9eaa91a7c2508da50f103c2aeb6fa99/sdk-api-src/content/shellapi/nf-shellapi-doenvironmentsubsta.md>;
  - the variables WOW64 sets for 32- and 64-bit processes:
    <https://github.com/MicrosoftDocs/win32/blob/367072aa99296ff4236e7c65384d643ca12e1012/desktop-src/WinProg64/wow64-implementation-details.md>;
  - the variables `GetTempPath` reads for the temporary directory:
    <https://github.com/MicrosoftDocs/sdk-api/blob/d43984d7c322f7d7d35704d6d1ad36dc3539703b/sdk-api-src/content/fileapi/nf-fileapi-gettemppathw.md>.

Moving a pin is a change to this specification. A variable added by a
later edition is exposed only once the pin moves, which is compatible; a
pin never moves to remove one.

*Best practice — what the criteria give today (not normative; the criteria
are):*

| System | Exposed |
|---|---|
| POSIX-compatible | `HOME`, `LOGNAME`, `SHELL`, `PWD`, `TMPDIR`, `PATH`, `NLSPATH`, `TEXTDOMAINDIR`, `DATEMSK`, `TERM`, `COLUMNS`, `LINES`, `MSGVERB`, `LANG`, `LANGUAGE`, `TEXTDOMAIN`, `LC_ALL`, `LC_COLLATE`, `LC_CTYPE`, `LC_MESSAGES`, `LC_MONETARY`, `LC_NUMERIC`, `LC_TIME`, `TZ`; `XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, `XDG_CACHE_HOME`, `XDG_RUNTIME_DIR`, `XDG_DATA_DIRS`, `XDG_CONFIG_DIRS` |
| Windows-compatible | `ALLUSERSPROFILE`, `APPDATA`, `LOCALAPPDATA`, `ProgramData`, `ProgramFiles`, `PUBLIC`, `SystemDrive`, `SystemRoot`, `USERPROFILE`, `windir`, `HOMEDRIVE`, `HOMEPATH`, `COMPUTERNAME`, `USERDOMAIN`, `USERNAME`, `LOGONSERVER`, `NUMBER_OF_PROCESSORS`, `OS`, `PROCESSOR_ARCHITECTURE`, `PROCESSOR_IDENTIFIER`, `PROCESSOR_LEVEL`, `PROCESSOR_REVISION`; `ProgramFiles(x86)`, `ProgramW6432`, `CommonProgramFiles`, `CommonProgramFiles(x86)`, `CommonProgramW6432`, `PROCESSOR_ARCHITEW6432`; `TMP`, `TEMP` |

*Windows keeps no locale or time zone in the environment, so a document
asking for one there is told it is not set. `PROCESSOR_IDENTIFIER` is a
processor model description (`Intel64 Family 6 Model 158 Stepping 10,
GenuineIntel`), shared by every processor of that model — hardware
configuration, despite its name. Microsoft notes that Known Folder APIs
are more reliable than the variables naming the same folders; a consumer
wanting that reliability can provide a declared function (§13).
The interactive-only variables are absent in services. Under the SYSTEM account,
`APPDATA` and `USERPROFILE` point inside
`C:\Windows\System32\config\systemprofile`, not into a person's profile.
Every variable in the POSIX chapter passes today. A variable outside
these standards — `USER`, `HOSTNAME`,
anything an application defines for itself — is exposed only by a loader
that chooses to.*

### 5.1.5 Casters and the getter

Four built-ins **cast** one value to another type. They take **Python's
names** and **yapyon's own parsing**: what each accepts is defined here,
not by any host language, so a document casts the same way everywhere.

| name | takes | gives |
|---|---|---|
| `__int__` | text that is a whole decimal number — an optional sign and ASCII digits, leading zeros allowed (`"03"` is 3), nothing before or after; an int; a float, **truncated toward zero** (`3.7` is 3); a bool (`True` is 1) | `int` |
| `__float__` | decimal text — digits with an optional fraction and an optional exponent (`"2.5e+3"`, `"3"`, `".5"`); a float; an int or a bool, rounded to the nearest float, akan if outside the float range | `float` |
| `__bool__` | the text `true`/`false`, `yes`/`no`, `on`/`off`, or `1`/`0`, in any ASCII case; the numbers 1 and 0 (and 1.0, 0.0); a bool | `bool` |
| `__str__` | an int, float, or bool, written as §5.4 writes it; a string, as it is | `str` |

**Anything else is akan** at the call, naming what the cast takes:
`"3.0"`, `"42abc"`, `" 42"`, and `"4_2"` as an int (text must be the whole
number — no host's habit of reading a prefix and dropping the rest);
`"inf"`, `"nan"`, `"2,5"`, and `"0x1p3"` as a float; `"y"` and `"maybe"` as
a bool; bytes for `__str__`, since text from bytes needs a named encoding
(ehmon 5); any container. **`None` is akan** too — unless the call is
written after `?.` (§13.1), which skips it.

`__get__(container, key, default=None)` is Python's `dict.get`, for
sequences as well: the value at a **key** of a mapping (compared as names,
§7) or an **index** of a list (negative counts from the end, §5.1), or
`default` when there is none. A **multimap** gives the list view of the key
(§5.2) — every value filed under it, `[]` when none — so its default is
never used. `default` may be given by position or keyword.

    persona:
      mind:
        model_list: []
    port_text: "8080"
    port: port_text.__int__()                                   # 8080
    FABLE: persona.mind.model_list.__get__(0)?.__str__()        # None

**A call's result is a separate value**, as a copy is (§5.6): changing one
loaded value never changes another. That is what can be observed, not how
it is built — an implementation shares whatever cannot be told apart,
every single value included.

### 5.2 Resolution scope: nearest wins

A reference's first segment resolves by searching outward from the y-string's
position; subsequent segments are plain child traversal.

1. **Sibling** — the same parent mapping (excluding the current key).
2. **Ancestors, nearest level first** — at each level, the ancestor's own key,
   then the ancestor's siblings. A near uncle beats a far ancestor; cousins
   are never searched.
3. **Root** — simply the outermost level of the same search.

Local shadows root. `{__ROOT__.name}` bypasses the search and anchors at the
document root — the escape hatch.

**Shadowing is not a diagnostic.** A reference that resolves locally while an
outer candidate of the same name exists is ordinary, correct resolution: the
search is total and deterministic, so nothing is ambiguous and there is
nothing to report. Implementations **must not** warn on it. *(v0.1 briefly
specified shiran here. It was removed 2026-09-14: it fired on correct
layered configuration — `path: y"{path}/claude"` refining an outer `path`,
once per derived value — and the `{__ROOT__.name}` spelling it offered as the
fix resolves to a different value, so following the advice broke the
document.)*

**Multimaps are not searched.** A multimap's entry keys take no part in steps
1–3: a bare `{registry}` must never find a multimap entry. Only explicit
traversal into a *named* multimap reaches one.

**By-key traversal of a multimap yields a LIST VIEW.** `{mm.registry}` names
**every** value filed under `registry`, in order, as a list: 0 entries give an
empty list, 1 gives one element, N give N. `{mm.registry[0]}` then indexes it.
Nothing is picked, so ehmon 1 is satisfied — the reference names the whole view
rather than choosing among candidates. Splicing the view into a string is akan
exactly as for any list (§5.5), so `y"{mm.registry}"` is an error while
`y"{mm.registry[0]}"` is not.

The view is **total**, and that is the point: a reference's legality never
depends on how many entries the data happens to hold. The alternative —
permitting `{mm.k}` only where `k` occurs exactly once — would make a
document's validity depend on its data, so adding a second entry would break a
reference that did not change.

Positional access to the multimap itself (`{mm[0]}`) is reserved (§9): it
would name an entry's value while discarding its key.

### 5.3 Resolution order

References resolve over the completed tree to a fixpoint (chaining is
supported; forward references work). A pass that makes no progress while
references remain means a missing target or a cycle: akan, listing the stuck
references with positions.

**Expansion limits come in two parts, and they are different numbers.**

| | Threshold | Exceeding it |
|---|---|---|
| **Warn threshold** — fixed by this specification | resolution depth 32; total rendered size 1 MiB per document | **shiran** |
| **Refusal ceiling** — chosen by the implementation | implementation-defined, at or above the warn threshold | **akan** |

Passing the warn threshold is `shiran` (§10) and resolution continues: the
document is *expensive*, which is a fact about the machine, not a mistake in
the bytes. An implementation **may** refuse a document above a ceiling of its
own; one that does **must document where that ceiling is**, and **should**
allow a consumer to move it.

An implementation is **strongly advised to have a ceiling**. Chained doubling
makes growth exponential, so a document of a few dozen lines can demand
unbounded memory; a resolver with no ceiling is a denial-of-service in any
program that parses configuration it did not write. This specification
declines to fix one ceiling for every implementation — it does not suggest
having none.

*Both limits are about resource cost only. They are unrelated to the cycle rule
above, which stays akan: a cycle or a missing target can never resolve, so
the document is wrong and ehmon 7 puts the error at the point of the mistake.*

**Depth is measured as the dependency chain**, not as a count of fixpoint
passes. A pass counter makes the answer depend on the order keys happen to
appear in the document, which a format whose thesis is "the same bytes mean
the same data" cannot permit.

### 5.4 What splices: the value

A hole splices its **value**, never its lexeme, as Python's `str()` writes
it — the behavior of every mainstream language's interpolation, and the only
rule that also covers values with no lexeme, such as a call's result (§13).
Equal values therefore always splice as equal text.

- **`int`**: decimal, with a `-` if negative. `0xFF` splices as `255`,
  `1_000` as `1000`.
- **`float`**: the shortest decimal that reads back as the same float. It is
  written positionally when the decimal exponent lies in −4 … 15, always with
  a fractional part (`3.10` splices as `3.1`, `1e3` as `1000.0`); otherwise
  as a mantissa, `e`, a sign, and at least two exponent digits (`1e+16`,
  `1e-05`, `1.5e+300`). Negative zero splices as `-0.0`.
- **`bool` and `None`**: `True`, `False`, `None`.
- **`bytes`**: Python's repr — `b`, a quote, the bytes, the same quote.
  The quote is `'` unless the bytes contain `'` and no `"`. `\` and the
  quote are escaped, as are tab, newline, and carriage return (`\t`, `\n`,
  `\r`); every other byte outside printable ASCII is `\xhh`, lowercase.
  `b"hi"`, `rb"hi"`, and `b64"aGk="` all splice as `b'hi'`: the `b'…'`
  marks the crossing (ehmon 5).
- **Strings** splice their **content** (the decoded value, not the quoted
  lexeme), so chains compose.
- Resolved y-strings splice their resolved result. Result strings are inert.

### 5.5 The splice matrix

| Hole in… | str | bytes | int/float/bool/None | container | yt value |
|---|---|---|---|---|---|
| `y` / `ry` | ✓ content | ✓ repr (§5.4) | ✓ text (§5.4) | akan¹ | akan² |
| `yb` | akan³ | ✓ the bytes | ✓ ASCII of the text | akan | akan |
| `yt` carry (§6) | ✓ | ✓ | ✓ | ✓ | akan² |
| `yt` render (§6) | *as `y`* | *as `y`* | *as `y`* | *as `y`* | — |

¹ container = list, dict, or multimap: "cannot interpolate a list, dict, or
multimap into a string" *(the named bridge is a serializer, §5.1.2)*.
&nbsp; ² "cannot splice a template into a string." &nbsp; ³ no implicit
encode, ever (PEP 461's wall, both sides).

**A `yt` has no matrix of its own.** It *carries* anything, because nothing
crosses into text when a value is handed over rather than joined; and its
canonical render (§6.3) reproduces the `y` row cell for cell, which is what
makes it an unjoined y-string rather than a second construct. The one
difference is *when* a refusal lands: a `y` is always joined, so it akans at
parse; a `yt` akans only if a consumer asks for the join.

### 5.6 Copies: `(ref)`

**Syntax: `GRAMMAR §G4.8`.** In value position, a reference in parentheses
is a **copy**: the value is the value the reference names, kept as what it
is — a list stays a list, a mapping a mapping.

    wanted: ["responses", "chat"]
    supported_dialects: (wanted)    # ["responses", "chat"]

- **The same lookup as a hole.** `(mind.dialects[protocol])` names what
  `{mind.dialects[protocol]}` names, by §5.1 and §5.2, and is akan where
  that hole would be. `(__PARENT__.__KEY__)` is the key, and `($HOME)` the
  variable (§5.1.3), each a `str`.
- **Resolved first, then copied.** A copy waits, as a hole does (§5.3),
  until everything in the value it names is resolved, and then takes that
  value. Nothing in the copy is resolved again where it lands: with
  `prod: (base)`, a `{__PARENT__.__KEY__}` inside `base` is `"base"` in
  both places. A copy holds finished values.
- **A copy, never the same node.** No node appears in the tree twice, so a
  consumer never receives one object at two places: after
  `supported_dialects: (wanted)`, changing one list in a loaded document
  does not change the other. (Python's `foo = (bar)` binds the same object;
  this is the one difference, and it shows only after loading.) Every
  literal in a copy keeps its lexeme (§3): with `b: 0xff`, a serializer
  writes `(b)`'s value as it writes `b`'s.
- **A copy cannot contain itself.** `a: [(__ROOT__.a)]`, `(__PARENT__)`,
  and `(__ROOT__)` are akan; two copies naming each other are §5.3's
  cycle.
- **A call's result can be copied.** `(f(x))` is the value the call
  returns, typed by its declaration (§13.4) and rebuilt as a fresh value,
  so it is owned where it lands; a document copying a declared function's
  result is an assembly, as one splicing it is. A built-in's result is
  copied the same way: `(__env__("X"))` is `None` when `X` is unset,
  where `y"{__env__('X')}"` is the text `None`.
- **A value ending in a call may stand bare**: `port: port_text.__int__()`
  means `port: (port_text.__int__())` (`GRAMMAR §G4.8`). A value written
  in a document must not be **owned somewhere else** in the tree — naming
  one is fine, moving it is not. In this version **every call's result is
  owned by nobody**, so a call may land where it is written; a bare
  **path** names a value owned elsewhere and stays akan, to be quoted as
  text or copied in parentheses.
- **Limits.** A copy is one link of a dependency chain, and adds what it
  copies to the rendered size — the length of each string and bytes value
  in it, and one for each other value — so copies that double their input
  meet §5.3's ceiling as y-strings do.

**Parentheses around a literal only group it**, as in Python: `(1)` is
`1`, `("x")` is `"x"`, and `((a))` is `(a)`. There are no tuples, so `()`
and a comma inside parentheses are akan. Parentheses are not literal
syntax: a document using them, even as `(1)`, is not a record (§12).

---

## 6. yt — template strings

**A `yt` literal is a y-string that is not joined**, and a document that
holds one is a **template** (§12): it is finished by the consumer, so it
cannot reduce to a record. Its holes resolve against
the document at parse time by §5.2's ordinary rules, exactly as `y`'s do. The
difference is delivery: `y` joins the parts into a string; `yt` hands the
consumer the literal text parts and the resolved values, separately.

    y : yt  ::  f-string : t-string

Interior syntax is identical to any other y-family literal (`GRAMMAR §G5`) —
one scanner, one divergence-table row. An unbound hole is akan **at parse**,
like any other unresolved reference: the mistake is in the document, so it
lands on the document's author (ehmon 7).

### 6.1 Why the parts are kept apart

A joined string has lost which bytes the author wrote and which came from the
data, and nothing downstream can recover the distinction:

```
user_input: "; rm -rf /"
cmd: y"echo {user_input}"          # -> "echo ; rm -rf /"
```

Parts keep them separable until a consumer that knows the destination — shell,
SQL, HTML, a registry — decides how each value is made safe.

This is the constructive half of the format's position on text substitution.
The destructive half is that **yapyon does not resolve names it cannot
define**: `$VAR` and `~` are ordinary characters (`GRAMMAR §G4.7`), because
`$HOME` does not name a value — it names *a lookup in an unspecified place*,
and picking one would be guessing (ehmon 1). Pre-parse text substitution is also
where injection lives: a value containing a quote and a newline can add a
key its author never wrote, whereas splicing replaces a value in the parsed
tree and is structurally incapable of that.

### 6.2 What a consumer receives

An implementation **must** deliver, per literal:

- the **literal text parts**, in order, and
- for each hole, its **resolved value**, the **source lexeme** of that value
  where it has one (§3), and the **reference as written**.

The lexeme is required, not decorative: `version: 3.10` resolves to a value
that in most languages is indistinguishable from `3.1`. The canonical join
(§6.3) uses the value, as `y` does; a consumer that wants the author's
spelling has it.

The alternation is **total**: text, value, text, value, … text. A literal
begins and ends with a text part, and an empty text part sits between adjacent
holes, so a consumer never special-cases a leading, trailing, or doubled hole.
There are always exactly one more text parts than holes.

### 6.3 Carrying versus rendering

**Carrying is unconstrained.** A hole may carry any value a document can hold,
containers and b-spelled bytes included. §5.5 constrains what may cross into
*text*, and nothing crosses into text here — the consumer that wants hex
rather than a repr receives the bytes and encodes them itself — a consumer is
code and can name its own encoder.

**Canonical rendering is constrained**, by §5.5 exactly as for `y`. An
implementation **must** provide a canonical join, and it **must** produce what
the equivalent `y` produces — that equality is what "an unjoined y-string"
means. Where §5.5 refuses, the join is akan; unlike `y`, which is always
joined and so akans at parse, a `yt` akans only if a consumer asks for the
join.

A canonical join **must be explicit**. An implementation must not render a
template implicitly through its language's default string conversion: an easy
implicit join is exactly the mistake the parts exist to prevent.

### 6.4 A template is not a value a string can absorb

Splicing a `yt` into a `y`, `yb`, or another `yt` is **akan**. Joining one
would discard the parts it exists to preserve.

A `yt` is **not** permitted in a record (§12), for the same reason `y` is not:
it requires the resolver, and a record is the form that needs none.

---

## 7. Keys

**Syntax: `GRAMMAR §G4.1`** (names), **`§G4.2`** (dunders), and
**`§G6`–`§G7`** (name, plain quoted, and `y`/`ry` keys).

> **Every name key of a mapping is addressable from a hole.**

A bare identifier is a **name key**. A quoted key is **not a name**, even
when its text is an identifier: `model:` and `"model":` have the same data
key but different visibility. Only name keys participate in §5.2's scope
search and dotted traversal. Quoted and computed keys are reached by a
subscript through a named container, never by spelling their text as a name.

**A name's identity is its folded name** (GRAMMAR §G4.1: width variants,
then NFC). The consumer receives that folded string, and the emitter keeps
the original key lexeme. Nothing warns about folding; it defines equality.
A plain quoted key retains its exact decoded text, with no name folding.
A computed `y`/`ry` key resolves like a string value at the pair's position
(§5.2–§5.5), then retains that exact text. It never becomes a name.

**Key equality is equality of the resulting strings**, not equality of
expressions. Two entries in one mapping with equal keys are duplicate-key
akan, even if one key is a name and the other is quoted, or their computed
expressions differ. Two name spellings that fold alike are also duplicates.
Computed duplicates are diagnosed when their keys resolve. Multimaps still
allow repeated keys (§7.1).

Subscripts first select an exact data key. If no exact key exists, a folded
name may be selected; non-name keys are never folded. Both literal and
indirect subscripts use this rule. They wait for pending computed keys before
selecting or reporting absence. A dotted step selects only a name key and
must not warn that a necessary subscript should be replaced by a dot.

```yapyon
provider: "moonshot-ai"
providers:
  y"{provider}":
    endpoint: "https://example.invalid"
chosen: (providers[provider])
```

Here `providers` is a name; its child is not. `providers[provider]` reaches
that child, while searching for `moonshot-ai`, or writing it as a dotted
segment, cannot. Even `"model":` requires a subscript rather than `.model`.

**Every key is nonempty, does not begin with `@`, and is not a dunder.**
These checks apply to literal text at parse time and computed text at
resolution, at the key's position. Empty keys are reserved for now. The `@`
restriction protects the serializer metadata vocabulary (§14).

Plain quoted keys are literal and legal in records (§12). A `y`/`ry` key
requires at least a ledger, even without holes; environment access or
contract calls raise its tier just as they do in a value. Record writers
keep literal key lexemes and write resolved computed keys as ordinary quoted
strings, never as names merely because their text resembles an identifier.

Sequence items and multimap entries take no part in §5.2's scope search.
Explicit traversal reaches them: `{xs[0]}` indexes a list, and `{mm.k}` is
the list view of a named multimap key; subscripts also reach non-name keys.

### 7.1 Multimaps

A block whose entries are introduced by `+ ` is a **multimap**: an ordered
sequence of key/value entries in which keys may repeat. Its syntax — one pair
per entry, no mixing of markers within a block — is `GRAMMAR §G7`.

```yapyon
changes:
  + registry:
      set: [["...\\LabConfig", "BypassTPMCheck", 1]]
  + file:
      delete: ["Program Files (x86)/Microsoft/Edge"]
  + registry:            # repeating is the point; order is significant
      remove: ["...\\Uninstall\\Microsoft Edge"]
```

- The key obeys §7. The value is any block value, including a nested multimap.
- **Order is significant and preserved.** Two multimaps are equal iff their
  entry sequences are equal; **a multimap is never equal to a mapping**, even
  when its keys happen to be unique.
- Entry keys are **invisible to holes** (§5.2).
- **`{+}` is the empty multimap** (`GRAMMAR §G6`) — a block needs an entry,
  so this is its one spelling when it holds none. **`{}` is a mapping**, as
  everywhere: the `+` is what says "multimap", in the document's own bytes,
  as the block marker does. A nonempty flow multimap is
  `{+ a: 1, a: 2}`: one leading `+`, comma-separated ordinary pairs, and
  an optional trailing comma. The block form still marks each entry.

Why a marker rather than simply permitting repeated keys in a mapping: ehmon 1.
A repeated key would otherwise be indistinguishable from a typo, and the
choice between "the second wins" and "collect both" would be a guess. The `+ `
says which was meant, in the document's own bytes.

---

## 8. Grammar

**`GRAMMAR §G6`** holds the phrase grammar, and `GRAMMAR §G7` the static rules
it cannot express.

The grammar's `scalar` has **nine** alternatives: five literal kinds and
four deferred kinds (the y-family and the copy). Expressions and
comprehensions (`GRAMMAR §G9`, §16) add structured computed forms beyond
that scalar partition. §12's literal-only restriction excludes those forms
as well as scalar computation.

---

## 9. Reserved for future versions

Syntax that is akan in v0.6 with the door explicitly open: `yb64` and `ytb`
prefixes; **empty string keys**; format
specs and conversions in holes; list interpolation; **default and variadic
parameters** for declared functions (§13.7); positional access to a multimap's entries
(`{mm[0]}`);
`---` multi-document streams; r-combos beyond `rb`/`ry`; timestamp and date
literal prefixes; **comment retention across an emit** (§4.4 normalizes, and a
round-tripper needs a design v0.6 does not have); **filling slots from
files** (§15.1 leaves finding a filler to the consumer); slot labels with
subscripts (`<base.items[0]>`); slots in multimap entries.

**A reservation is a promise, not a plan.** Items arrive on this list by being
argued individually; nothing should be built from it because it appears here,
and nothing should be inferred to be wanted because it sits beside something
that is.

*Built and therefore no longer reserved: `__PARENT__` and `__KEY__` (§5.1.1);
the four serializers (§5.1.2), which now take a single value as well as a
container; escapes in a hole's string literals (`GRAMMAR §G5.1`); quoted hole segments (`{a."b.c"}` → `{a["b.c"]}`)
and interior addressing of lists and multimaps (`{xs.0}` → `{xs[0]}`,
`{mm.key}` → a list view), both subsumed by the subscript rather than added
beside it; negative indices, which take Python's meaning (§5.1); keyword
arguments to declared functions (§13.1). `self` was withdrawn rather than built — it named a consumer's own
key convention, not anything the format needed.*

---

## 10. Diagnostics

| Register | Meaning | Example |
|---|---|---|
| `shiran:` | legal but suspicious; parsing continues | a bracket where a dot would do, `{a["bar"]}` (`GRAMMAR §G5.4`) |
| `akan:` | error; the document does not parse/resolve | bare word in value position |
| `yakamashiwa:` | internal invariant violated — a bug in the implementation, not the document | indent stack underflow |

Every akan carries a line and column and, wherever a fix is mechanical, names
it in the message ("write `{{` for a literal brace"; "use rb").

**Shiran must fire only where something is probably a mistake**, not merely
where it is unusual, and shiran whose suggested fix would change what a
document means is not a warning but a trap.

v0.6 specifies **five**, and none of their fixes changes what a document
means. The avoidable bracket is about spelling alone. §5.3's two warn
thresholds and §3.1's long decimal assert nothing about what the author
intended — they report that a document is costly and may be refused
elsewhere, which is true whatever was meant — and their fixes (shorten the
chain or the number, or raise the consumer's ceiling) leave the resolved
value identical. The fifth reports that JSON output has no place for a
lexeme (§14.3); its fix, `lexemes=False`, says that only the values were
wanted, and the values are the same either way.

*The grammar states the akan and shiran registers too (`GRAMMAR §G1`), because
it must be readable alone. That overlap is the concept only; this table is
authoritative for the three registers.*

---

## 11. Divergence table (vs Python)

**Everything not listed is Python-exact.** Anything Python allows that yapyon
does not is akan — never silently reinterpreted. That closure statement is
normative; the individual rows are cross-references to the rule's own home.

| Construct | Python | yapyon |
|---|---|---|
| unquoted words | names/expressions | akan (no plain scalars) |
| `"""` leading whitespace | kept verbatim | dedented to the first content line's indentation |
| newline after opening `"""` | kept | dropped |
| unknown escapes | kept, warning | akan |
| `\N{NAME}` | named character | akan (excluded) |
| surrogate `\u` escapes | lone surrogates allowed | akan |
| octal escape above `\377` in bytes | truncates to a byte, warns | akan |
| `f"..."` / `t"..."` / `u"..."` | formatted / template / no-op | akan with hint (ehmon 6) |
| `y*` prefixes | syntax error | yapyon-native (holes, §5) |
| prefix spelling | `rb`/`br`, any capitalization | canonical only (`rb`, lowercase) |
| `inf` / `nan` | via `float()` | no spelling |
| `0q`, `0z` integer prefixes | syntax error | base 4 and Crockford base 32 (`GRAMMAR §G4.3`) |
| `bin dna oct hex c32 b64` string prefixes | syntax error | bytes stream literals (§4.3) |
| decimal integers over 4,300 digits | `ValueError` by default (3.11+) | shiran; akan only above the implementation's ceiling (§3.1) |
| dict keys | any hashable | names or strings; quoted keys are not names (§7) |
| duplicate dict keys | last wins, silently | akan; `+ ` multimap if repeats are meant (§7.1) |
| identifier folding | NFKC | width variants, then NFC — `ｎａｍｅ` ≡ `name`, but `ﬁ` ≢ `fi` (GRAMMAR §G4.1) |
| identifier character set | the interpreter's Unicode version | pinned to Unicode 14.0.0; no invisible characters |
| set / tuple / complex literals | types | akan (not in the data model) |
| `(name)` as a value | the same object | a copy of its value (§5.6) |
| `a \| b` | bitwise OR, or dictionary union | value composition under §15.2, at the lowest value-operator precedence (§16.5) |
| `key:= value` in a pair | no such dictionary-field form; `:=` is an assignment expression elsewhere | replace that field's earlier value with the complete incoming value (§15.2) |

---

## 12. Conformance: the yapyon record

A document is a **record**, a **ledger**, a **template**, or an
**assembly** (ehmon 2), and each tier contains the one before it: a record
is a ledger that splices nothing, a ledger is a template that holds no
`yt` or slot and reads no environment, and a template is an assembly that calls no declared
function. The record is the restricted form — records are implied to be
fixed, and this one is. The tier a document needs is computable from its
bytes: a `y`, `yb`, or `ry` literal, a copy or bare call (§5.6), any
parenthesis, or an expression or comprehension (§16), including either
merge-pipe form, makes it at least a ledger; a `yt` literal, a slot (§15), or
an environment reference (`$NAME` or a call to `__env__`) a template, and a call to a declared
function an assembly. A replacement separator alone does not raise the tier:
otherwise literal data annotated for replacement remains a record. An explicit
pipe requires at least a ledger even with literal operands or in a branch that
would not execute. Operator characters inside strings are inert.

The tiers fall into two **styles**. **Basic** documents — records and
ledgers — are finished by their own bytes: a basic document reduces to the
same record on every machine, the base case every document reduces toward.
**Extra** documents — templates and assemblies — are finished by something
outside them: the environment, the consumer joining a `yt`'s parts or
filling a slot, or a contract. Basic means self-contained, not limited; extra means it needs
more than its bytes, not that it is better.

### 12.1 The rule

> **Every leaf element has a literal value.**

A literal is readable from its own bytes: a quoted string, a bytes literal, a
number, or a keyword (§3). Nothing about a leaf's value depends on anything
else in the document. Containers — mapping, sequence, multimap — are structure
rather than leaves, so the rule reaches all the way down.

This is ehmon 3 stated at the leaf: independence, made local. It also
explains why the existing akans are the right ones — a bare word is not a
literal (ehmon 1, no plain scalars), and `key:` with nothing after it is not a
literal either (`GRAMMAR §G7`, no implicit null).

### 12.2 The mechanical test

The five literal scalar kinds (§8) and ordinary literal collections need
no resolver. A record refuses y-family literals/keys, copies and bare calls,
parentheses, labels, expression operators/reference atoms/postfixes, and
comprehension markers (`GRAMMAR §G9`), including `PIPE` and `BPIPE`
(`GRAMMAR §G6`). Contextual words used as ordinary keys and punctuation
inside literals do not count as computation. Neither does a replacement
separator's optional equals token. A nonempty literal flow multimap (§7.1)
and a literal field annotated for replacement remain record-compatible.

An implementation can test those lexical kinds without resolving anything:
**a record is identifiable by lexing alone.** As always, subset membership
does not replace the grammar's validity checks.

### 12.3 Being a record is a property, not a declaration

- **No directive, no header, nothing to add.** yapyon has no directives and
  `---` is reserved-meaningless; the property is already visible.
- **Compositional.** The marker is the prefix, per string. It is not something
  the document announces as a whole.
- **A strict subset.** Every record is a valid yapyon document with the same
  meaning: a ledger, template, or assembly implementation loading a record returns
  exactly what a record implementation returns.
- **Unambiguous in a minimal implementation.** A plain string containing
  `{foo}` is six characters under every composition (`GRAMMAR §G4.6`), so an
  implementation with no resolver never has to decide anything.

Being a record describes the **document**, not the pipeline. A consumer may
take a plain string out of a record and choose to process it later; "this is a
record" must not be read as "this value reaches the application unchanged".

### 12.4 What a record does not have

| | yapyon record | yapyon |
|---|---|---|
| y-family prefixes `y` `yb` `yt` `ry` | **akan** | permitted |
| copies and parentheses (§5.6) | **akan** | permitted |
| expressions, including explicit merge pipes, and comprehensions (§16) | **akan** | permitted |
| replacement separator on an otherwise literal field (§15.2) | permitted | permitted |
| slots (§15) | **akan** | permitted (template and above) |
| §5 parse-time splicing | n/a | yes |
| §6 templates | n/a | yes |
| Resolver required | **no** | yes |
| The avoidable-bracket shiran | never fires (no holes) | may fire |
| §5.3 expansion limits | n/a | apply |
| Values produced | str, bytes, int, float, bool, None, list, dict, multimap | the above, plus Template |

A multimap (§7.1) is permitted in a record. It is a yapyon-specific type, but
it is plain keyed data rather than deferred structure; the criterion is
"nothing deferred", not "builtin types only".

### 12.5 Conformance

An implementation **must state which tier it implements**. There are four:

- **Record** — the literal subset of `GRAMMAR.md` identified by §12.2,
  excluding y-family prefixes/keys, holes, copies, parentheses, labels,
  computed expressions/comprehensions, and explicit merge pipes
  (`§G4.6`–`§G4.9`, `§G5`, `§G6`, `§G9`); plus this document's §3, §7,
  §10, §11, and §12. Literal replacement annotations are included.
- **Ledger** — all of the above, plus `GRAMMAR §G4.7`, `§G5` except
  `ENV`, and this document's §4.4, §5 except §5.1.3–§5.1.4, and §14, and
  §13 as it applies to the built-ins other than `__env__`, and §16 with
  `GRAMMAR §G9` excluding environment/declared-function access, and §15.2's
  value-combination rules as used by §16.5. Explicit merge pipes in
  `GRAMMAR §G6`/`§G9` require this tier; literal replacement annotations do not.
- **Template** — all of the above, plus `yt` (§6), `ENV`,
  §5.1.3–§5.1.4, `__env__`, `LABEL` (`GRAMMAR §G4.9`), and slots (§15).
- **Assembly** — all of the above, plus the whole of §13: contracts, their
  types, and calls to declared functions.

A record implementation is genuinely conforming. It needs no resolver, no
fixpoint, no template machinery, and no evaluator, which is the point: the safe
subset is declared first rather than carved out afterwards.

Of §9's reserved syntax, the items that concern holes — `yb64` and `ytb`,
format specs and conversions, list interpolation, default and variadic
parameters, positional multimap access — are **ledger and above**,
since a record has no holes at all. §5.1.1's relative references are
ledger and above for the same reason. The rest — empty string keys,
`---` streams and timestamp prefixes — would
concern both forms. Plain quoted keys are already legal in records; the
key-position `YKEY` token is deferred just as a value-position `YSTR` is.

On meeting a y-family prefix, a record implementation is **akan at that
prefix's line and column**, and says so as the record rule rather than as a
syntax error: the document is well-formed yapyon, it is simply not a record.
In the same way, a ledger implementation meeting a `yt` literal, a slot, or an
environment reference is akan there, saying that it needs a template
implementation.

*Reference implementation: `yapyon.loads_record` and `yapyon.load_record` load
a record; `yapyon.is_record` performs the §12.2 test without loading.*

---

## 13. Functions and contracts

A document may **call functions** inside a hole (`GRAMMAR §G5`):
`{match_first(supported, mind.dialects)}`, or in the receiver form
`{supported.match_first(mind.dialects)}`. A dunder name calls a
**built-in**, defined by this specification (§5.1.2, §5.1.3); any other name calls a
function **declared** in a **contract** (§13.2) that the program loading the
document supplies.

### 13.1 Calls

A **call** applies a function to arguments. Its result depends on exactly
three things: the contract, the name, and the argument values. **An
argument's value may be a borrow**: a reference argument naming a mapping,
list, or multimap lends the function that node — not a copy of it, not a
literal rendering of it, and not ownership of it.

- **Built-in or declared.** A dunder name names a built-in; any other name
  names a function the contract declares. A name neither defines is akan at
  the call site.
- **The receiver form is sugar.** `{a.f(x)}` is `{f(a, x)}`.
- **`?.` skips a call on `None`.** In `{a.f()?.g().h()}`, if `a.f()` is
  `None`, neither `g` nor `h` is called and the whole chain is `None` — as
  in JavaScript, C#, and Swift. Otherwise `?.` is `.`. It protects only its
  own chain: an argument is a chain of its own. Without it, a call given
  `None` is akan where its parameter does not take `None` (§5.1.5).
- **Keyword arguments name a parameter.** A keyword takes anything a
  positional argument can, and follows every positional argument, as in
  Python. For a **declared** function the keywords are its parameter names
  (§13.2), compared as identifiers (§7): positional arguments, the receiver
  first, fill the parameters in declared order, and keywords fill the rest
  by name — `{f(a, y=b)}` and `{f(y=b, x=a)}` are one call to
  `f(x, y)`. **Every parameter is filled exactly once**: a parameter left
  empty, one filled twice, and a keyword naming no parameter are akan at
  the call, naming the parameters. The function receives its arguments in
  declared order however the call spelled them, so a binding's own
  parameter names never matter. A **built-in**'s keywords are its own
  (§5.1.2): `{cfg.__as_json__(lexemes=False)}`. A keyword a built-in does
  not define is akan at the call.
- **Tier.** A document that calls a declared function is an **assembly**;
  one that holds a `yt` or reads the environment (`$NAME` or `__env__`)
  and calls no declared function is a **template**; calls to the other built-ins alone
  leave it a **ledger**. A record holds no calls
  (§12).
- **Inside-out, left to right.** Every argument resolves to a value before
  the call that takes it; a chain applies its links in order.
- **Arguments must be resolved.** A call is applied only once every argument
  has resolved to a value. For a borrow that means **the whole node**: no
  hole anywhere in its subtree is still pending, so nothing the function
  reads can be unresolved. Until then the call **defers** to a later pass of
  §5.3's fixpoint — at every level of nesting and every link of a chain — so
  two calls waiting on each other are reported as the **cycle** they are.
- **A borrow is read-only and downward.** The function can read the node's
  kind, its keys and entries in document order, and its descendants; it
  cannot reach the node's parent or change anything. The node keeps its
  identity (the same node passed twice is the same node) and its source
  position, so a type mismatch inside it is reported where it is written
  (§13.3). **A borrow is valid only during the call it was passed to; a
  function must not keep it.** Like determinism (§13.6) this is an
  obligation on the function, which an implementation may be unable to
  check; a binding whose values point into the loaded document depends on
  it.
- **No argument may contain the call site.** A reference argument naming an
  ancestor of the hole is akan. For an anchor this is visible in the syntax,
  which does not generate it (`GRAMMAR §G5`); for any other reference it is
  checked when the reference resolves, and reported at parse. A nested
  call's *result* is a fresh value with no position and is never checked.
- **Depth and size** count toward §5.3 exactly as splices do.

### 13.2 Contracts

A **contract** declares the functions a document may call. It is a yapyon
**record** (§12), so every implementation reads it with no resolver:

```
match_first:
  params:
    keys: "list[str]"
    items: "dict[str, dict[str, str]]"
  returns: "str"
  impl:
    python:
      from: "persona_grata.dialects"
      symbol: "match_first"
    c:
      from: "persona_grata"
      symbol: "pg_match_first"
```

- Each top-level key is a **function name** — an identifier (§7), and so
  never a dunder: a dunder key is akan in every record. Dunders are the
  format's alone.
- `params` — **required**; an ordered mapping from parameter name to type
  (§13.3). Its order is the positional argument order, and its names are
  the keyword argument names (§13.1). An empty mapping `{}` declares
  no parameters.
- `returns` — **required**; a type.
- `impl` — **required**; maps a **language** to where that language finds
  the code. **Each language defines its own entry's keys.** For `python`
  and `c` they are `symbol` (required) and `from` (optional). **With
  `from`**, the implementation locates the code itself: a Python module
  path, or a library name **without** a platform suffix (`.so`, `.dll`, and
  `.dylib` are added per platform). **Without `from`**, the program loading
  the document provides the code.
- **Languages.** This version defines `python` and `c`. An implementation
  reads only its own language's entry and **ignores every other entry
  entirely** — its name, its keys, and whatever it holds — so one contract
  can serve bindings an implementation lacks, and a binding defined later
  may give its entry keys this version does not know. A function with no
  entry an implementation can use is akan **when the contract is loaded**,
  naming the function.
- **Any other key is akan** — in the contract's own structure (a
  function's keys, its `params`), and in the entry for the implementation's
  own language.
- A contract is given to the **loader**, never named by a document
  (ehmon 3).

### 13.3 Types

A type is written as a string, in Python's typing spelling over §3's type
names:

```ebnf
type    ::= alt ( "|" alt )*
alt     ::= "str" | "bytes" | "int" | "float" | "bool" | "None" | "Any"
          | "list"     "[" type "]"
          | "dict"     "[" "str" "," type "]"
          | "multimap" "[" "str" "," type "]"
```

Spaces and tabs may appear between any two tokens (`list[ str ]`,
`dict[str,int]`, `int|None`), as in a Python annotation. Writers use the
PEP 8 form: `dict[str, int]`, `int | None`.

- A bare `list`, `dict`, or `multimap` is akan — the contained type is
  required.
- **`Any`** is Python's `typing.Any`, or its equivalent in each binding. It
  accepts everything a document can hold, and a container's contents below
  it are not checked; a value received as `Any` is checked again at any
  later call that declares a narrower type. It is written, never implied:
  `list[Any]`, not `list`.
- `dict` and `multimap` write their key type, which must be `str`: keys are
  strings under §7, whether names, quoted text, or computed text. It is written
  so that a later version can admit other key types without respelling.
- No type names a template (§6), so a `yt` value is never a valid argument
  or result.

**Checking — before every call, and on every result.**

- An argument is checked against its parameter's type **before the call**;
  a mismatch is akan **at the offending value's own line and column**,
  naming the function and the parameter. **The check is deep**: every
  element of a container is checked against the contained type, all the way
  down, stopping only at `Any`. It reads types only, so it needs no
  evaluation, and an implementation may cache it per node.
- A function's result is checked against `returns` the same way; a mismatch
  is akan at the call site, naming the function.
- A **union** matches if any alternative does. An **exact** match beats
  widening: `float | int` keeps `3` an `int`. Where several alternatives
  match — an empty list against `list[str] | list[int]` — the **first
  declared** is taken.
- **`bool` is not `int`**: yapyon's types decide, never a host language's
  subtyping.
- **`int` is accepted where `float` is declared**, and arrives as a `float`
  in every binding. Every `int` up to 2⁵³ in magnitude converts exactly;
  beyond that, not every integer has a float, and the nearest is taken, ties
  to even, as Python converts (`2**53 + 1` → `9007199254740992.0`). An `int`
  outside the float range is akan. The same rule applies to results and
  inside containers.
- **Order is data**: a function sees a `dict`'s keys and a `multimap`'s
  entries in document order, in every binding.

### 13.4 Results

A result is placed by §5.5, unchanged: a `str` splices into a `y`; a list in
a `y` is akan as any list is; other scalars splice by value (§5.4). A
function cannot return a node of the document; its result is fresh data.
**Returned data must be yapyon data**: a returned mapping's keys are legal
strings (§7). Keys with retained name/non-name information keep it; otherwise
a writable identifier is a name and is folded, and any other legal string
is a non-name key. Duplicate resulting keys are akan at the call, naming the
function. A returned string is Unicode scalar values, as a written one is
(`GRAMMAR §G4.5`), so one holding a lone surrogate is akan there too. A
result has no lexemes; a yapyon writer gives it canonical form (§4.4).

### 13.5 Errors

All at the call site, in the existing register: an unknown name; the wrong
number of arguments, which is checked at parse against the contract; an
unknown, repeated, or misplaced keyword; a parameter filled twice or left
empty; an argument or result of the wrong type; an
argument containing the call site; and **a function that fails** — reported
as akan naming the function and its message, never as a host-language
traceback.

### 13.6 Determinism

A declared function **must** be deterministic: same contract, name, and
arguments, same result. An implementation cannot check this; it is an
obligation on whoever provides the function. Its consequence is stated
plainly: **two loaders with different contracts produce different data from
the same bytes** — which is why the contract is explicit, named in ehmon 3,
and never discovered.

### 13.7 Not in this version

Returning a node; a key or index after a call **inside a hole**
(`{f(x)[0]}`, `{f(x).name}`); default or variadic parameters; a template
in a signature; contracts a document can name.

Bare calls as values (`foo: f(x)`) and copies of results (`(f(x))`) are
already supported (§5.6). Value expressions support postfix traversal of
call results (§16.4); hole interiors retain the narrower reference grammar
(`GRAMMAR §G5`), where only another call may follow a call.

---

## 14. Serializer output

This section fixes, exactly, the text each serializer (§5.1.2) produces,
so that every implementation writes the same output for the same
argument. A serializer's output is a `str`. TOML, YAML, and yapyon output
end with a newline; JSON output does not.

### 14.1 Width and layout

The **width** of a line is the sum of the widths of its code points, by
the Unicode 14.0.0 database (the same pin as identifiers, §7):

- **0** for a combining mark (`Mn`, `Me`), a format character (`Cf`), or
  any other `Default_Ignorable_Code_Point`;
- **2** for `East_Asian_Width` `W` or `F`;
- **1** otherwise;
- except that **U+FE0F** (emoji presentation) makes the character before
  it count 2 — so `❤️` counts 2. The model may overcount a rendering; it
  never undercounts one, so a long line is broken early, never late.

A container **fits** if its one-line form, on its line — indentation,
key, and any trailing comma included — has width **at most 100**.
Layout goes **outermost first**: a container that fits is written on one
line; one that does not is written one member per line, indented two
spaces deeper than its opening line, and each member is judged the same
way.

Which containers may take a one-line form depends on the format:

| Format | One line if it fits | Always broken |
|---|---|---|
| JSON | every array and object | — |
| TOML | arrays | tables (sections); an inline table is always one line, at any width |
| YAML, yapyon | a sequence holding no mapping or multimap | mappings, multimaps |

### 14.2 Lexemes beside values — `@_lexemes` (JSON, TOML)

JSON and TOML write each value as plain data in that format and record,
beside it, what a plain value cannot say. The record is a member named
**`@_lexemes`** in the object (table) that holds the value. Its entries
are yapyon source text — the value's lexeme (§4.4).

**What gets an entry:**

- an integer written in a **non-decimal radix** (`0x`, `0o`, `0b`, `0q`,
  `0z`) — its lexeme;
- **every bytes value** — its lexeme, or, with none, its canonical form
  (`b"..."`, §4.4), so bytes are never mistaken for text;
- in TOML only: an **integer outside −2⁶³ … 2⁶³−1** — its lexeme, or its
  decimal digits with none — and **`None`** — the entry `"None"`.

Decimal numbers, strings, booleans, and (in JSON) `None` get no entry:
the plain value is the yapyon value. *(A decimal's spelling — `1_000`,
`3.10` — is not kept; only yapyon output keeps every lexeme.)*

**Entry keys.** A value that is a member of the object is keyed by its
key. A value inside an array is keyed by a **path** from the nearest
containing object: the member's key, then each index, joined with `/` —
`"ports/0"`, `"matrix/0/1"`. Each segment uses JSON Pointer's escaping
(RFC 6901): replace `~` with `~0`, then `/` with `~1`; there is no leading
slash. This applies to a member key on its own too, so a literal key
`ports/0` has the entry `ports~10`, distinct from index 0 under `ports`.
**In a multimap node** the table is the node's own, and a path is
`entries/<i>` — the entry, not its key, since an entry holds exactly one
value — continuing with indices only if that value is an array
(`entries/0/1`). Entries are in document order.

**Placement.** In JSON, `@_lexemes` is the **last** member of its object
. In TOML, it is one inline table if that line fits (§14.1);
otherwise a `["@_lexemes"]` section (`[server."@_lexemes"]` for a nested
table) written after the table's own keys.

A key beginning with `@` can never be yapyon data (§7), so neither the
side table nor any wrapper below can be mistaken for content. The name is
not keyword-shaped under JSON-LD (`"@"` followed by letters only), so
JSON-LD processors drop it or keep it as a property without warning;
I-JSON readers ignore it (RFC 7493 §4.2).

### 14.3 JSON

Output is I-JSON (RFC 7493). One-line spacing is `", "` between members
and `": "` after a key; a broken container puts each member on its own
line with its comma at the end, and its closing bracket at the opening
line's indentation. `[]` and `{}` are written so. Strings: `"` and `\` escaped, U+0000–U+001F as `\b \f \n \r \t` where those exist
and `\u00XX` otherwise, lowercase hex; everything else, non-ASCII
included, as itself.

| yapyon value | JSON |
|---|---|
| `True`, `False`, `None` | `true`, `false`, `null` |
| `str` | a string |
| decimal integer | the number |
| non-decimal integer | its decimal value, plus an entry: `{"port": 255, "@_lexemes": {"port": "0xff"}}` |
| integer beyond 2⁵³ | the number as-is — valid JSON; a reader that parses numbers as doubles may change it, which is that reader's limit |
| `float` | the shortest text that reads back as the same float (`1.5`, `1e+16`, `1e-05`, `-0.0`) |
| bytes | padded base64url (RFC 4648 §5; RFC 7493 §4.4), plus an entry: `{"data": "aGk=", "@_lexemes": {"data": "hex'6869'"}}` |
| mapping | an object, keys in document order |
| list | an array |
| multimap | `{"@type": "multimap", "entries": {"@list": [{"registry": "a"}, {"file": "b"}]}}` — one single-member object per entry, in order |
| a list or single value as the whole output | written plain, **never wrapped**; a lexeme it holds has no object to live in, so it is dropped, with shiran naming `lexemes=False` |

The multimap node is valid JSON-LD.

### 14.4 YAML

Block style; scalars are never line-wrapped. Every marker is a **`%TAG`
handle resolving to YAML's standard prefix** `tag:yaml.org,2002:`, so an
ordinary loader constructs a standard type and the handle's name is the
hint. A handle is declared only if the output uses it, in order of first
use, and `---` follows the declarations; output with no handle
has neither.

```yaml
%TAG !multimap! tag:yaml.org,2002:
%TAG !hex! tag:yaml.org,2002:
%TAG !x! tag:yaml.org,2002:
---
foo: !multimap!pairs
  - registry: a
  - file: b
data: !hex!str "6869"
port: !x!int 0xff
```

| yapyon value | YAML |
|---|---|
| `True`, `False`, `None` | `true`, `false`, `null` |
| decimal integer | plain |
| `0x` / `0o` / `0b` integer | `!x!int 0xff`, `!o!int 0o377`, `!b!int 0b11111111` — the lexeme, negatives included |
| `0q` / `0z` integer | `!q!int 255`, `!z!int 255` — the **value**, since YAML cannot read the lexeme |
| `float` | plain, as JSON writes it, **with `.0` inserted** when the mantissa has no `.` (`1.0e+16`, `1.0e-05`): YAML 1.1 reads `1e+16` as a string |
| `b64` bytes | `!!binary "<lexeme>"` |
| other bytes spellings, `b`, `rb` | `!<spelling>!str "<lexeme>"` (`!hex!str "6869"`) |
| bytes with no lexeme | `!!binary "<base64>"` |
| multimap | `!multimap!pairs`, then a block sequence of one-entry mappings |

One handle may serve two suffixes — `!b!str` (b-bytes) and `!b!int`
(a binary integer); the pair is the meaning. **Bytes are always quoted**,
so a lost tag never turns a stream into a number.

**Emitted defensively** (§5.1.2): a scalar is plain only if every YAML
1.1 and 1.2 reader would read it as the intended type; any other string is
quoted. **In a flow sequence**, a string holding `,`, `[`, `]`, `{`, or `}`
is also quoted.

**Never written:** bare custom tags (`!hex`), which make `safe_load` fail
the whole document; JSON-LD keys; `!!pairs` alone.

A YAML tool that rewrites the output may drop the handles (YAML treats
them as presentation); the data stays correct.

### 14.5 TOML

**TOML output reads as the same tree as JSON output** (§14.3), with two
differences TOML forces: it has no null, and its integers are 64-bit.

| yapyon value | TOML |
|---|---|
| `True`, `False` | `true`, `false` |
| `None` in a table | **the key is left out**, and recorded: `"@_lexemes"` entry `"None"` |
| `None` in an array | the string `"None"`, recorded the same way (`"xs/1" = "None"`) — leaving it out would shift every later index |
| integer in −2⁶³ … 2⁶³−1 | its decimal value (plus an entry if non-decimal — TOML's own `0x`/`0o`/`0b` are unsigned-only, and readers discard the spelling) |
| integer outside that range | **a string** of its decimal digits, recorded as an integer by its entry (TOML readers must reject the number) |
| `float` | as JSON writes it |
| bytes | padded base64url, plus an entry |
| mapping | a table: `[a.b]` |
| list of mappings, non-empty | an array of tables: `[[a.b]]` |
| any other list | an inline array (`a = [{}]` for a mixed one) |
| multimap | `foo."@type" = "multimap"` and `foo.entries = [{registry = "a"}, {file = "b"}]` — an array of single-entry inline tables |
| list or single value as the argument | **akan** — TOML has no top-level form for either (operator, 2026-10-13); refused by `__as_toml__`'s signature |
| multimap root | `"@type" = "multimap"` and `entries = [...]` at the top level |

**Layout:** an array is one line if it fits (§14.1); otherwise `[` stays
on the key's line (TOML requires it), one element per line indented two
spaces, with no trailing comma. An inline table is one line at any width
(TOML 1.0 cannot break it).

**Order.** A table's own keys come before its sub-tables and its
`["@_lexemes"]` section; a table defined by dotted keys is never given a
header later, and an inline table is never extended. Keys are bare when
they are TOML bare keys — ASCII letters, digits, `_`, `-` — and quoted
otherwise.

### 14.6 yapyon

`__as_yapyon__()` writes the argument as a **record** (§12), every value
in its lexeme as written, or in its canonical form when it has none
(§4.4): a string as a double-quoted literal, a number in decimal, a float
as JSON writes it, bytes as `b"..."`, `True` / `False` / `None` as
themselves. Layout is §14.1's: a sequence holding no mapping or multimap
is one line if it fits; mappings and multimaps are block, a multimap's
entries marked `+ `.

### 14.7 Reading output back

A reader that knows this section recovers the yapyon value from JSON or
TOML output:

- An `@_lexemes` entry **overrides the plain value's type**: a number
  lexeme restores the integer and its spelling; a bytes lexeme makes the
  string bytes; a number lexeme on a string makes it an integer; `"None"`
  restores a left-out key, or replaces its stand-in in an array.
- **A stale entry is akan**: a lexeme that does not produce the plain value
  beside it; a `"None"` entry for a table key that is present; or a
  `"None"` entry for an array element that is not the string `"None"`.
  The akan names the key and both values, and the fixes: update
  the entry, delete it, or read with lexemes ignored.
- A reader **may be told to ignore lexemes**, and then takes the plain
  values as they are.
- `@type: multimap` nodes are restored to multimaps.

YAML output has no side table — its lexemes are its content, under the
handles — so it cannot go stale. A yapyon-aware YAML reader reads the
handles from the token stream, before a loader discards them.

### 14.8 Known limits

- **Key order.** Order is data in yapyon; JSON and TOML do not promise to
  keep it, though most readers do. A multimap's order is safe — it is an
  array.
- **JSON and TOML differ** exactly where §14.5 says: `None`, and integers
  outside 64 bits.
- **A plain reader sees the approximation**, not the yapyon value: bytes
  as base64url text, a non-decimal integer in decimal, a multimap as a
  tagged list. That is the design: correct plain data for every reader,
  and the exact value for a reader that knows §14.

---

## 15. Slots

A **slot** is a value that marks a place in a document for something from
outside to fill. A document says where it is and what fills it; its
consumer supplies the filler. A slot is spelled as a **label** after a key:

```yapyon
name: "local_ultron"
path: y"{agent_store}/{name}"

persona<llamacpp>:                     # persona's value is a slot, labeled llamacpp
  mind:
    endpoint: "http://localhost:9931"  # an override

harness<claude>: {}                    # a slot with no overrides
```

`persona`'s value is a slot with the label `llamacpp` and these
**overrides**. Its complete right-hand side is one structural dictionary
override contribution: an ordinary dictionary, a dictionary comprehension,
or a grouped/pipe combination of those forms (`GRAMMAR §G6`–`§G7`, `§G9`).
A scalar, list, multimap, or arbitrary reference/call as the overrides is
akan. Literal `{}` means no overrides, even for a non-dictionary filler;
it is not an incompatible empty dictionary applied over that filler. Only
a proven harmless literal empty override, with no retained operation or
validation history, may be skipped. A pending comprehension is not empty
merely because it has no known entries yet. Whitespace may surround and
fill the label (`persona <llamacpp>:`);
`persona<llamacpp>:` is the canonical spelling.

A document that holds a slot is a **template** (§12): something outside
finishes it. Slot-specific operations require that tier. The shared merge
rules (§15.2) also govern ledger value composition (§16.5); a literal
replacement annotation alone remains record-compatible (§12).

### 15.1 A slot is passive

A label is a name and does nothing by itself. **It says what fills the
slot — never how to find it.** Which file, preset, or branch a label
stands for is the consumer's business; yapyon reads no file and searches
nothing on a slot's behalf. A slot is not reachable from a hole: no
reference names a label, and nothing in the document refers to one.

Labels are names (`GRAMMAR §G4.9`), compared as keys are (§7). The same
label may appear under different keys; each is a separate place.

*A slot sits where YAML writes an anchor (`harness: &h`), and the likeness
ends there: an anchor exists so the document can reuse its own content,
which yapyon does with holes (§5) and copies (§5.6). A slot points the
other way — out of the document, at something its consumer supplies.*

### 15.2 Merging

Filling, structural tree composition, and explicit value composition (§16.5)
use **one merge operation**. An earlier contribution is **lower**; an incoming
contribution is **higher**. Unset means absence of a contribution, not `None`
and not a new literal. A single supplied field assigns its value; two absent
fields do not create a `None` entry.

**Pair separators select the field operation** (`GRAMMAR §G4.10`, `§G6`):

- The ordinary separator combines the earlier and incoming values at that key.
- The replacement separator uses the **complete incoming right-hand value**
  and discards the earlier value, including its pending computation. A pipe
  expression on the right belongs wholly to that value, not just its first
  operand. Replacement works with any supplied value, including empty
  collections, `None`, and a new slot. A replacement slot still fills normally.
- Replacement is not deletion or immunity to later overrides. `field:= {}`
  keeps an empty dictionary at `field`; `field:= None` forces `None` even
  over a container. A later contribution can change either again.
- The separator changes the value operation, not the matched key's identity,
  position, spelling, or name/non-name kind. Replacement intent is contribution
  information, not another data type, and is retained where later composition
  needs it.

For **established ordinary values**, let **A** mean `str`, `bytes`, `int`,
`float`, `bool`, or `Template`, and **D**, **L**, and **M** mean dictionary,
list, and multimap. `Template` is not thereby a scalar literal or record
value. Rows are earlier/lower; columns are incoming/higher:

| Earlier / incoming | None | A | D | L | M |
|---|---|---|---|---|---|
| None | None | incoming | incoming | incoming | incoming |
| A | incoming None | incoming | incoming | incoming | incoming |
| D | earlier D | incoming | dictionary merge | incoming | incoming |
| L | earlier L | incoming | incoming | list merge | incoming |
| M | earlier M | incoming | incoming | incoming | multimap merge |

Thus `None` yields to **every container in either order**, including an empty
one. Against a non-container it follows higher-wins precedence. Compatible
empty collections yield rather than clear or normalize the other's authored
repetitions. Incompatible kinds use the incoming whole value without a cast,
even when it is an empty container of a different kind. Zero, `False`, and
empty text are actual values, not unset. Explicit field replacement bypasses
this ordinary matrix.

Unknown keys, kinds, or values stay deferred until the operation has enough
information. Parse, merge, and source preparation must not execute expressions
early to obtain that information. The matrix is about eventual values, not
parser classes: a copy or call contributes established fresh data (§5.6),
whereas structural dictionary operands retain their unfinished bodies for
merging before those bodies resolve (§16.4). An unfilled slot is not assigned
a guessed ordinary-value kind; it follows §15.2.4.

### 15.2.1 Dictionary matching

Dictionaries match keys by their resulting strings under §7, not expression
spelling. Each input retains its contribution identity. The earlier key
keeps its position, spelling, and name/non-name kind; new incoming keys
append in incoming order. Matching values combine under §15.2, or take the
incoming field's explicit replacement. Different keys are never deduplicated
because their values happen to match. **No merge promotes a quoted or
computed key into a name**, including an explicit field replacement.

Only dictionary unique keys provide recursive matching. A matched list or
multimap uses §15.2.3; do not infer member identity from an index, a repeated
multimap key, or a field named `id` or `name`.

Equal keys across contributions combine; duplicates **within one contribution**
remain akan. Statically known duplicates are parse errors, and computed
duplicates are checked when their keys are required or resolved. A whole
discarded contribution is not evaluated merely to discover a dynamic error
in code that no longer contributes. Syntax and static validity still apply
to the whole document.

### 15.2.2 Typed merge equality

Merge duplicate comparison is recursive data equality with **exact kind
distinctions**. `True`, `1`, and `1.0` are distinct. Within a kind:

- **None** equals `None`.
- **Bool, int, and float** compare their same-kind values, ignoring source
  radix, separators, and spelling. Finite float signed zeros compare equal;
  the selected representation retains its spelling and sign.
- **Text and bytes** compare exact decoded contents. Do not fold text or
  infer an encoding.
- **Lists** compare lengths and typed elements in order.
- **Dictionaries** compare string-key/value associations using recursive
  typed equality, independent of entry order and key kind or spelling.
- **Multimaps** compare ordered complete entry sequences, including repeated
  string keys and typed values. They never equal dictionaries.
- **Templates** compare delivered text/hole structure in order. Each hole
  has equal reference text, delivered value lexeme, and recursively typed
  value. Diagnostic filenames and positions are not equality data. No
  rendering occurs; equal rendered text does not imply equal templates.

This equality is **specific to merge deduplication**. §16.3's ordinary
expression equality, including its numeric behavior, is unchanged. Host
bool/int subtyping, hashes, source-expression identity, and serialized text
are not substitutes for this comparison. Replacement annotations do not
make otherwise equal data unequal.

### 15.2.3 Collection counts, order, and representation

Lists combine **whole elements**; multimaps combine **whole key/value pairs**.
The same multimap key with a different value is a different entry, not a
request for recursive by-key merging. For each equal value or pair under
§15.2.2, retain the **greater occurrence count in either input**, not the sum
and not necessarily one. Standalone and force-replaced collections retain
their authored repeats.

The occurrence pairing is:

1. Keep the earlier occurrences in their original positions.
2. Visit incoming occurrences in incoming order, matching each to the first
   equal, not-yet-matched occurrence from the **original earlier input**.
3. A match keeps that position and takes the complete incoming representation.
   Do not recursively merge matched values.
4. With no available match, append the incoming occurrence. Appended
   occurrences are not new match targets in this binary merge.
5. Unmatched earlier occurrences keep their representations. One incoming
   occurrence is not broadcast over every equal earlier repeat.

For example, `["a", "b"] | ["b", "c", "b"]` yields
`["a", "b", "c", "b"]`: the first incoming `"b"` matches, then `"c"`
and the extra `"b"` append. `[0x1, True] | [1.0, 1]` yields
`[1, True, 1.0]`; only the ints match, and the incoming int spelling wins.

A dictionary-valued list item takes the whole higher item, including its
key kind, order, and available lexemes, at the retained position. This is
not direct dictionary merging, whose matched keys keep the earlier
provenance (§15.2.1). The same whole-representation rule applies to a
matched multimap pair. Source operation history is not an extra data kind.

### 15.2.4 Slot selection and pending contributions

Slot selection precedes application of the selected filler and overrides.
An incoming explicit field replacement discards inherited slot/default
history; if its value is a new slot, that slot fills normally. For ordinary
combination:

| Earlier | Incoming | Result |
|---|---|---|
| a named slot `x<a>` | a dictionary | the slot, with the complete incoming dictionary appended as its last override contribution |
| a named slot `x<a>` | None, a list, a multimap, or a value of unknown kind | retain the slot and ordered pending combination until the filler kind is known |
| a named slot `x<a>` | a known A value, or a slot | the incoming value or slot |
| `x<>` | a slot `x<b>` | `x<b>`, with both override histories, earlier first |
| `x<>` | `x<>` | `x<>`, with both override histories, earlier first, retaining the abstract obligation |
| `x<>` | any contribution that is not a slot | the incoming value, selecting that value for the abstract position |
| anything not a slot | a slot | the slot |

An unfilled named slot followed by `None` cannot simply be discarded: a
container filler survives that `None`, while a scalar filler does not.
Likewise, a later list combines with a list filler but replaces a dictionary
filler. Retain any still-needed slot as discoverable and fillable; resolving
without filling it remains akan. A dominating atomic value or explicit
replacement that discards the slot also removes the need to fill it.

A labeled field's **complete RHS is one dictionary override contribution**.
Several sequential additions to an unfilled slot are not equivalent to one
premerged RHS. Each later addition acts on the result of the preceding
operation; grouping inside a contributed dictionary stays inside it. §15.8
preserves these boundaries in saved source.

### 15.3 Filling

**A slot filled with a tree applies its retained override program over
that tree**: the filler first, then each override contribution in order,
using §15.2. Literal empty overrides mean no operation (§15), not a cast to
a dictionary. A premerged dictionary is one contribution, not a sequence
of operations on the filler. The filler is copied in (§5.6's linearity):
one tree may fill many slots, and each receives its own.

> **For the same retained assembly and fixed slot selections, equivalent
> fills give the result of filling to literal, merging, and repeating.**
> Slot choices are selected under §15.2.4; the selected filler's nested
> slots and override program determine the result. An implementation may
> fill in any order or keep operations waiting, provided it preserves that
> result.

Two consequences, stated because they are easy to get wrong:

- **A slot's overrides apply only if the slot is filled.** A later value
  that discards the slot discards its overrides with it.
- **Equivalent fill order does not change the same retained assembly.**
  Overrides apply innermost first, preserving their contribution order.
  This does not equate merging independently prefilled inputs with selecting
  between unfilled slots: the former combines ordinary data, while the
  latter may select only the higher named slot (§15.2.4).

A filler that contains the slot it would fill is akan.

### 15.4 A label may reach into its filler

A label is one name or several, joined by dots. **The first names the
filler; the rest is a path inside it**, followed as dotted keys are:

```yapyon
# base.tmpl
agent:
  name: "agent_base"
```

```yapyon
# example_agent.tmpl
agent<base.agent>:
  name: "example"
```

`agent<base.agent>` fills with the `agent` branch of what `base` stands
for, not with all of it — without this, every layer would nest the last
one a level deeper. The consumer is given the **whole label** and supplies
the tree its first name stands for; the implementation follows the rest.
A key the path does not find is akan, naming the label.

A path may **end on a slot**: that slot, its overrides included, takes the
place of the one being filled, with the filled slot's overrides applying
over its own, and is filled in turn. A path that would pass **through** a
slot not yet filled is akan: fill that slot first.

### 15.5 Abstract slots: `<>`

An empty label is an **abstract slot**: what fills it is not yet chosen.

```yapyon
# template.tmpl
agent:
  harness<>:
    timeout: 30
```

```yapyon
# an agent file filling from it
agent<template.agent>:
  harness<claude>: {}
```

**A fill that brings in an abstract slot obliges the slot doing the
filling to give that key a value in its overrides**, at the same place.
Any value meets it:

- `harness<claude>: {}` names what fills it (§15.2: the label is taken,
  and the template's overrides still apply under the agent file's);
- `harness<>: {}` passes the obligation on, explicitly, to whatever fills
  from this document in turn;
- a value that is not a slot — `harness: {}`, `harness: None` — replaces
  the abstract slot, and its overrides with it.

A fill whose overrides leave an abstract slot without a value is akan at
that fill, naming the abstract slot. If checking the obligation requires a
computed key's text, the comparison waits for resolution and any error still
names the fill; it must not compare expression spellings or resolve an input
early. Keep the responsible fill's own contributions, provenance, and error
location while the comparison is pending. A later edit that happens to supply
the missing key is not retroactive fulfillment by that fill. Discarding an
obligation is valid only when the responsible branch/program is actually
discarded, not merely because its current structural view changes.

An abstract slot that no fill brings in — at the top of the document a
consumer starts from — is the consumer's to fill directly.

### 15.6 Resolving

**Holes resolve after filling, once, where the content has landed.** A
filled tree is part of the document it fills, and its holes follow §5.2
from where they now sit: a hole in a filled harness finds the sibling
persona, and `{name}` finds the nearest `name`, wherever that came from.

**A retained slot still unfilled when the document resolves is akan** — an
abstract slot saying it needs a label or a fill, any other naming its label.
`loads` supplies no fillers, so it refuses a document whose composition
still needs a slot. A slot discarded by a later dominating contribution
is no longer an obligation to fill.

Diagnostics name the document each value was written in, at its own line
and column, however the tree was assembled.

### 15.7 What an implementation offers

The operations above are the format's: an implementation of the template
tier offers a consumer a way to **parse** a document without resolving it,
**walk** its structurally known places, **merge** trees, **fill** a slot,
**remove** a value, and **resolve** once. Their names and shapes are the
implementation's; parser nodes need not be exposed.

Known mapping views retain their string keys and locations for unresolved
key entries. An unresolved collection's final indices, length, or iteration
must not be guessed or forced by evaluation: effective-position operations
are available only where the structure proves the effective view. Retained
slots must nevertheless remain discoverable and fillable through their
source-contribution locations, even when eventual collection positions are
unknown. A discarded slot is not enumerated for filling.

Consumer operations copy supplied content, and resolution uses a private
working tree: editing a composition does not mutate either input, another
fill, or the original source during resolution. Location-based handles keep
reading their location, rather than a stale node. A removed location raises
the implementation language's ordinary missing-location error, not an alias
to a different contribution. A copied view of slot overrides is inspection,
not a promise that applying one premerged dictionary to any filler replays
the complete sequential override program.

*Reference implementation: `Tree`, `Handle`, and opaque `Key` tokens provide
these operations without exposing AST nodes. `Tree.slots` discovers
retained slots, including those inside pending contributions. Unknown
effective collection positions cannot be indexed as though already resolved.
A removed handle path raises `KeyError` or `IndexError`. Handles and key tokens
belong to their original tree; a reparse obtains fresh corresponding locations.*

### 15.8 Saving an unfinished document

An implementation may offer a **source writer** for an unresolved tree.
It writes a single parseable yapyon document preserving subsequent
equivalent fills, edits, merges, and resolution, given the same environment
and contract. One matching current result, or a fill with an empty mapping,
is not enough: the unfinished program's continuation behavior must survive.

**Saving never evaluates.** No hole lookup, environment access, declared or
built-in call, cast, serializer, comprehension iteration, template rendering,
or runtime duplicate comparison runs, even when its inputs appear available.
The writer may inspect structural facts and re-indent source lexemes, but
must not have a separate value-combination policy. Saving does not mutate
the original tree, its keys, handles, warnings, or diagnostic provenance, or
relax §15.6's requirement to fill still-needed slots at resolution.

**Preserve operations and contribution boundaries.** Write retained
contributions as explicit layers (`GRAMMAR §G6`, `§G9`). Keep each input's
identity, lexical bindings, operation order, replacement intent, and
behaviorally significant grouping. Potentially equal keys from separate
dictionaries must not become duplicate entries in one dictionary; a
same-contribution duplicate must not become a legal cross-layer merge.
Comprehensions remain comprehensions, each with its own head, clauses,
and lexical scope. Computed keys stay exact-text non-name keys; saving
never promotes them, substitutes the environment, or compares expression
spellings as key identities.

A field's separator applies to its complete right-hand value. Preserve
right-grouped merge programs rather than flattening them as though merge
were associative. For a postfix on a merge result, parenthesize the whole
result rather than attaching the postfix only to the right operand. An
authored pipe remains computation even with literal operands: source
saving does not evaluate it to lower its tier.

**Sequential slot overrides may need surrounding dictionary layers.** A
labeled field contributes its complete RHS as one dictionary value. Several
sequential operations on its filler cannot generally be written inside that
RHS. For example, these are distinct complete documents:

```yapyon
part<base>:
  config: "reset"
|
part:
  config:
    new: 2
```

```yapyon
part<base>:
  config: "reset"
  |
  config:
    new: 2
```

With a filler `config: {old: 1}`, the first yields
`part: {config: {new: 2}}`; the second yields
`part: {config: {old: 1, new: 2}}`. The second RHS is one premerged override;
the first retains two sequential operations on the filler. The writer must
not interchange them. Likewise, later `None`, list, or multimap contributions
to a retained named slot belong outside its dictionary-only overrides, lifted
into the nearest representable containing dictionary with grouping preserved.

Explicit layers replace the former save-time refusals for potentially
matching computed keys, pending override replacement boundaries, and a
dictionary comprehension combined with another nonempty contribution **only
when they faithfully represent the retained state**. The writer must not
freeze inputs, drop contributions, or merely remove a safety check. Two
remaining refusals are:

- **A completed fill's still-undecided historical abstract-slot obligation
  (§15.5).** If the responsible fill's own overrides still require a
  computed-key comparison, saving remains akan at that fill until the
  obligation is actually settled or faithfully representable. An ordinary
  new abstract slot does not encode a condition on a prior fill. Do not
  evaluate a key or rely on a later convenient edit to evade this refusal.
- **An unattached slot.** A slot has source spelling only when attached to
  its dictionary field and label. A root value that is an unattached slot
  cannot be saved as a standalone document.

Any further refusal must identify a concrete unrepresentable state, with a
specific reason and location, not broadly reject supported layers or mixed
forms. Save-time refusal does not change in-memory merging, filling, or
resolution; a refused tree may still resolve in memory.

**Spelling and layout.** Keep literal lexemes and required expression
spellings. The initial generated style uses two-space indentation, ordinary
`key: value`, replacement `key:= value`, and a standalone pipe aligned with
its contribution heads, without automatic blank lines around it. Input
whitespace is wider (`GRAMMAR §G4.10`). A grouped operand uses valid flow
forms inside parentheses, where indentation is not syntax. Shared expression
spelling applies there. Layout and comments need not survive (§4.4);
redundant parentheses may be removed, but meaningful grouping may not.

Reloading gives the saved document its new source name and positions, not
the former files' diagnostic locations. The original in-memory tree keeps
its provenance (§15.6). Opaque handles and key-location tokens belong to
their original tree; continuations on the reparse obtain fresh corresponding
locations. Normalized source is idempotent, and later equivalent operations
must preserve successful results and expected errors alike.

*Reference implementation: `Tree.to_source()` returns newline-terminated
source text without writing a file. Record `emit()` remains record-only;
it does not evaluate authored pipes. Its structural literal-record data
path (§4.4) is not a substitute for this unfinished-source contract.*

## 16. Expressions and collection comprehensions

**Syntax: `GRAMMAR §G9`.** A comprehension constructs a list, dictionary,
or multimap by applying one locally bound head to an ordered source
collection, optionally excluding items with one condition. It is data
construction, not an in-document function definition or a generator.

### 16.1 Sources, bindings, and result kinds

The source and result kinds are independent:

| Source | Binding | Iteration order |
|---|---|---|
| list | one name for each typed item | list order |
| dictionary | two names: string key, typed value | dictionary entry order |
| multimap | two names: string key, typed value | every entry in order, including repeats |

Other source kinds or a binding count that does not match the source are
akan at the comprehension. A list item is not unpacked, even if it is a
list of two values. A multimap source is not its grouped by-key list view.
Empty input constructs the corresponding empty result (`[]`, `{}`, `{+}`).

The iterable expression resolves in the surrounding context, before the new
binding exists. Each item introduces a lexical binding frame over the
predicate, key, and value body, including nested copies and y-strings.
An inner frame shadows an outer frame; lexical bindings precede ordinary
§5.2 document search. They are not injected mapping entries, do not leak,
and do not mutate any outer value or input item.

```yapyon
persona:
  name: "example"
  mind:
    model_list: ["m1", "M/2"]
model_rows: {
  target: {provider: (persona.name), remote_model_id: (target)}
  for target in persona.mind.model_list
}
```

Here `target` computes each result key. It does not name the literal key
"target". The inner `provider` and `remote_model_id` remain ordinary name
keys, and their copies retain existing syntax. Block heads are equivalent:

```yapyon
persona: {name: "example", mind: {model_list: ["m1", "M/2"]}}
model_rows:
  target:
    provider: (persona.name)
    remote_model_id: (target)
  for target in persona.mind.model_list
```

### 16.2 Construction and evaluation

Evaluate in source order: bind the item, test its predicate if present,
then evaluate its key (if keyed) and value body. An excluded item's output
key/body is not evaluated. Syntax and static validity still apply to the
whole document. Missing references, failed calls, and other errors are
never silently interpreted as false or as omission.

Each included item constructs fresh typed data under §5.6's observable
linearity. Containers, None, empty values, zero, and False are not pruned.
Generated expressions use their actual output locations for ordinary
§5.2/relative scope, plus the lexical bindings above. References into input
values retain those values' resolved meaning; copies do not reinterpret them.
Pending dependencies and forward references into the surrounding document
use §5.3's ordinary fixpoint and cycle rule, not a second evaluator.

A comprehension is **eager**: its whole result is evaluated before a postfix
operation selects from or calls on it. Selecting index zero must not hide an
error in a later iteration. Nested comprehensions use the same binding and
evaluation rules. They do not add a second for clause to the enclosing one.

A generated dictionary/multimap key must be a string. Keep its exact text,
without name folding or implicit string conversion. It is a non-name key
under §7, including when its text resembles an identifier. Existing nonempty,
non-dunder, non-@ key checks apply at the head's source position. Equal keys
within one dictionary comprehension are duplicate-key akan. Multimap
comprehensions preserve repeated keys and entry order. A head's replacement
annotation (`GRAMMAR §G9`) belongs to each produced entry, not the enclosing
collection. It neither permits same-contribution dictionary duplicates nor
introduces unique-key matching for multimap entries (§15.2.3).

### 16.3 Conditions and operators

A condition accepts **True** (include), **False** or **None** (exclude).
Every other type is akan, including numeric 0/1, strings, bytes, and containers.
There is no implicit caster call or Python truthiness. The explicit __bool__
caster (§5.1.5) is unchanged and continues to refuse None and containers.

`and`, `or`, and `not` use that condition rule and always return booleans.
`and` stops at a false left operand; `or` stops at a true left operand.
Unevaluated operands are not type-checked or executed. These are logical
operators, not Python's operand-returning fallback selectors.

Equality and inequality compare data values, not source lexemes or key kind.
Numbers use ordinary numeric comparison, including bool as 0/1; strings and
bytes compare their exact values, lists compare elementwise, dictionaries
compare their data entries, and multimap equality is §7.1's entry sequence.
Template equality compares the delivered parts, including hole reference and
lexeme metadata (§6), without rendering them. Ordering is numeric, lexicographic for text/bytes, and lexicographic for lists
whose compared elements support it. Incompatible ordering is akan, not host
object ordering. A chained comparison evaluates each middle operand once and
stops at the first failed comparison.

`in`/`not in` test list values, dictionary/multimap keys, or compatible
text/bytes containment. Unsupported containment types are akan. `is None`
and `is not None` test absence, not general object identity. In particular,
an explicit non-None test retains empty containers and False:

```yapyon
supported_dialects: ["responses", "chat"]
persona: {mind: {dialects: {responses: None, chat: {}}}}
protocol: [dialect for dialect in supported_dialects
           if persona.mind.dialects.__get__(dialect) is not None][0]
```

### 16.4 Postfix operations, composition, and persistence

Constructed values, comprehensions, groups, and call results support the same
postfix traversal/call facilities as other expressions. Subscripts and dotted
steps follow §5.1/§7, calls follow §13's one path, and None passthrough retains
its receiver-chain boundary. Selecting `[0]` from an empty result is ordinary
out-of-range akan; calling `.__get__(0)` returns None, or an explicit default.
Neither operation converts errors during comprehension evaluation to absence.

A dictionary comprehension is a **deferred dictionary contribution** for
§15.2 merging. Retain its layer and precedence without evaluating inputs
at merge time; once keys are known, equal keys across layers merge normally.
For such a structural contribution, evaluate its predicate/keys to establish
entries, then merge before resolving the retained value bodies. A replaced
body is not evaluated, and retained references see their final overridden
siblings. Lexical bindings belong to comprehension-authored syntax, not to
separately authored override values. Same-input duplicates remain errors.
List and multimap results combine by §15.2.3's whole-element/whole-pair
comparison, counts, order, and representation rules, not recursive member
matching. The same value-kind matrix applies to literal, copied, called,
and constructed results. Retained comprehensions remain eager; selecting
an early item must not hide a later error. A whole discarded contribution
need not be evaluated merely because it was written as a comprehension.
Save retained contributions as unevaluated layers under §15.8, preserving
their independent scopes and later behavior rather than flattening or
materializing them.

Comprehensions and expression operators require at least the ledger tier.
Environment access, yt, slots, and declared functions raise the tier exactly
as in any other value, even in a branch that would later be excluded. A
record has no comprehension or expression evaluation. §5.3's expansion limits
apply to materialized construction as well as copies/splicing; implementations
must bound generated work rather than allocate an unbounded result first.

### 16.5 Explicit value composition

**Syntax: `GRAMMAR §G6`, `§G9`.** A merge pipe composes complete values using
§15.2, at the **lowest value-operator precedence**, below logical `or`.
Existing logical, comparison, and postfix operators keep their relative
precedence. Unparenthesized pipes associate **left to right**, including
chains mixing block and flow operands. Parentheses make one contributed
operand; a right-grouped merge is not flattened.

Merge is not generally associative across replacement boundaries. For
example, this complete document yields `config: {new: 2}`:

```yapyon
{config: {old: 1}} | {config: "reset"} | {config: {new: 2}}
```

This different complete document retains both `old` and `new`:

```yapyon
{config: {old: 1}} | ({config: "reset"} | {config: {new: 2}})
```

An inline pipe after a pair's separator composes that pair's whole value;
it does not implicitly merge the surrounding dictionary. Block pipes
separate operands at the enclosing value's indentation. A pipe may be alone
on its line or followed by a flow expression; an unbraced block operand
begins on the following logical line. Grouping remains meaningful in every
layout. A bare name/path may be an expression operand but remains invalid
as a standalone ordinary value.

Structural dictionary operands retain unfinished bodies at their output
locations and merge before retained body resolution (§16.4). Copies and
calls contribute established fresh data (§5.6), not symbols to paste into
a different scope. Unknown result-producing operands stay deferred, and
use the **same eventual-kind matrix**, not a second policy based on parser
classes. Pending dependencies use §5.3's existing fixpoint and cycle path.
Source saving preserves these operations without executing them (§15.8).

An explicit pipe requires at least a ledger, even with literal operands.
A replacement annotation alone does not (§12). This value-expression
extension does not widen holes or call arguments: both still use
`GRAMMAR §G5`, not arbitrary expressions, and no callable-value form is added.

Necessary materialization and duplicate comparison participate in documented
resource limits before unbounded work or allocation. Limits must account for
work on inputs and comparisons, not only the final deduplicated output.

---

*Mascot: an Osaka rabbit. Severities escalate as indifference, refusal, and
losing it entirely. On success in verbose mode: ええやん。*
