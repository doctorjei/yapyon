# yapyon — draft specification v0.4

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

Sections marked *(reserved)* name syntax deliberately akan in v0.4 but held
for future versions.

A yapyon document is one of **four tiers** (ehmon 2): a **record**, in
which every leaf element has a literal value (§12); a **ledger**, which
also splices and applies the format's built-in functions (§5); a
**template**, which also holds template strings (§6) or reads the
environment of the process loading it (§5.1.3); and an **assembly**, which also calls functions declared in a
contract (§13). §12
states what an implementation of each must support.

---

## 1. Ehmon

*これ、ええもんやでー Jei*

Every rule in both documents follows from seven guiding principles, the
**ehmon** (ええもん, "the good stuff"):

1. **Precision.** A value's type is fixed by its syntax or by a declared
   contract (§13); it is never inferred from bare text. There are no plain
   scalars: an unquoted word in value position is akan, never a string,
   never a boolean. (YAML's implicit typing — the Norway problem — is
   unrepresentable.)
2. **Reducibility.** Computation is driven by data and yields a document. A
   **record** computes nothing: every leaf is a literal, and loading one
   needs no resolver (§12). A **ledger** — a record with references to
   itself — splices named values into strings and applies only the
   format's own encodings (§5.1.2), and reduces to a record that is the
   same on every system. A **template** is finished by something outside
   the document: it may read the environment of the process loading it
   (§5.1.3), and reduces to a record given that environment, and it may
   hold template strings (§6), whose parts the consumer joins. An **assembly** may also apply the functions its contract
   declares (§13), and reduces to a record given that contract and
   environment.
3. **Independence.** A document's meaning depends on nothing it does not
   declare. A **record** or a **ledger** depends only on its own bytes. A
   **template** may depend also on the environment it is loaded in, and
   only on variables it names, each at its reference (§5.1.3). An **assembly**
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
   an explanatory message. Everything with yapyon-native semantics is spelled
   in the `y` namespace.
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
| dict | `{k: v}` flow, indented block | identifier keys (§7) |
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
preserve them: comment-preserving round-trip is not specified in v0.4. An
emitter is a normalizer, not a round-tripper. *(Reserved: comment retention —
see §9.)*

*Reference implementation: `yapyon.emit`, and `python -m yapyon record`, which
normalizes a record (§12).*

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

A key is always an identifier (`GRAMMAR §G4.1`), so splicing one into text is
closure-safe by construction (ehmon 4). Into a `yb` string it is text→bytes and
akan under ehmon 5, by the ordinary rule and with no special case.

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
body: y"payload={cfg.__AS_JSON__()}"
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
| `__AS_JSON__` | `(Any) -> str` |
| `__AS_TOML__` | `(dict[str, Any] \| multimap[str, Any]) -> str` — a TOML document is a table, with no top-level form for a list or a single value |
| `__AS_YAML__` | `(Any) -> str` |
| `__AS_YAPYON__` | `(Any) -> str` |

`__AS_JSON__` and `__AS_TOML__` take one keyword argument, `lexemes`
(default `True`); `lexemes=False` writes no `@_lexemes` (§14.2). A
built-in's keyword arguments are its own and are listed here; it takes its
positional argument by position only.

`{cfg.__AS_JSON__()}` is the receiver spelling of `{__AS_JSON__(cfg)}`;
both are legal (§13.1). A result is a `str`, and a chain is checked like
any call: `{a.__AS_JSON__().__AS_YAML__()}` writes the JSON text as a YAML
string, while `{a.__AS_JSON__().__AS_TOML__()}` is a type error at the
second link, since `__AS_TOML__` takes a table. **A dunder call that names
no built-in — these four, or `__ENV__` (§5.1.3) — is akan** at the call,
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
the commonest form is an anchor — `{__ROOT__.__AS_JSON__()}` and
`{__PARENT__.__AS_JSON__()}` are **akan**, while
`{__ROOT__.blk.__AS_JSON__()}` and `{a.__AS_JSON__()}` are legal. An anchor
is always an ancestor of the hole that names it, so encoding one needs the
value of the very y-string doing the encoding; no document resolves it.
The mistake is visible in the reference, so ehmon 7 puts the akan there,
at parse.

```
blk:
  a: 1
  me: y"{__PARENT__.__AS_JSON__()}"     # akan: me = {"a":1,"me":<me>}
```

**Nothing useful is lost**: an anchor followed by any step leading away
from the hole is the shape authors want. *(Encoding "my parent, excluding
the pair I sit in" was considered and declined: it terminates, but makes
`__AS_JSON__()` mean different things depending on where it is written.)*

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
format makes is TOML's `None`:** TOML has no null, so `__AS_TOML__()`
leaves the key out of its table and records it in that table's
`@_lexemes` as `"None"`, from which a yapyon-aware reader restores it.
Nothing is lost; a plain TOML reader sees the key absent, as TOML tools
commonly write a null.

**YAML is emitted defensively.** A scalar is written plain only when
nothing else could read it as another type — so `"no"`, `"3"`, and
`"true"` come out quoted, and in a flow sequence nothing that could end
or open a flow collection is left plain. yapyon exists partly because YAML
guesses; emitting into it must not hand that problem to the reader.

**`__AS_YAPYON__()` writes yapyon source**, so yapyon's own rules govern
it and it carries everything the data model has. Its output is the
argument as a record (§12) in the spelling §4.4 gives every yapyon writer:
each value as written — its lexeme, so `v: 3.10` stays `3.10` and
`hex'6869'` stays `hex'6869'` — and a value with no lexeme (a resolved
y-string, a function result) in its canonical form.

### 5.1.3 The environment: `$NAME` and `__ENV__`

A hole may read **the environment of the process loading the document** —
its own, and no other. Two spellings, one lookup:

```
paths:
  home: y"{$HOME}"
  config: y"{__ENV__('XDG_CONFIG_HOME', default_config)}/app"
  default_config: y"{$HOME}/.config"
```

- **`{$NAME}` is strict** (`GRAMMAR §G5`): the variable's value, and
  **akan** when it is not found — as Python's `os.environ["NAME"]` raises.
- **`__ENV__(var_name, fallback=None)` is a built-in**: the variable's
  value, or `fallback` when it is not found — as Python's
  `os.getenv(key, default=None)`. With one argument the fallback is `None`,
  which splices as `None` (§5.4) exactly as `f"{os.getenv('X')}"` does; an
  author writing it has asked for that. `var_name` is any argument that is
  a `str` — a literal or a reference — and anything else is a type error
  at the call (§13.3). A name `GRAMMAR §G5`'s `ENVNAME` cannot spell is
  reached only this way: `{__ENV__("ProgramFiles(x86)")}`. `fallback` may
  be given by position or as `fallback=`, and takes anything an argument
  can; like any argument it is resolved before the call (§13.1), whether
  or not it is used.
- **One lookup.** `{$X}` is `__ENV__("X")` except that not found is akan
  rather than a fallback. An implementation has one implementation of it.

What the lookup sees:

- **Values are `str`.** An empty value is a value — `""`, not "not set":
  some conventions treat the two alike (the XDG Base Directory
  Specification does), and that is not universal, so a document that wants
  it says so.
- **Not found means not set *or* not exposed** (§5.1.4). A variable the
  load does not expose is indistinguishable from one that is unset: `{$X}`
  is akan and `__ENV__` returns its fallback. The akan says so — *"`$X` is
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
  reference is akan — *"environment access is off"* — including `__ENV__`
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

**Syntax: `GRAMMAR §G4.1`** (identifiers and the Unicode-version requirement),
**`§G4.2`** (the reserved dunder vocabulary), **`§G7`** (keys are bare names;
keywords, dunders, duplicates, and every other key form are akan).

What belongs here is the **consequence**, which is a claim about
addressability rather than about well-formedness:

> **Every key of a mapping is addressable from a hole.**

This holds only because the grammar applies **one predicate** to keys and to
hole segments. Widen either alone and the claim becomes false — which is how
it broke twice: `a²` was admitted as a key by `str.isalnum()` and could be
named by nothing, and `__foo__` was a legal key whose hole akaned.

**A key's identity is its folded name** (GRAMMAR §G4.1: width variants to
their standard form, then NFC). Two spellings that fold alike are **the same
key** — by definition, not by reinterpretation — so:

- `ｎａｍｅ: 1` and `name: 2` in one mapping are a **duplicate key**, akan like
  any other; the diagnostic names both spellings;
- a hole may name a key in any spelling that folds to it: `{name}` and
  `{ｎａｍｅ}` both reach `ｎａｍｅ: 1`, and so does a bracketed key or a key
  held in a value (`{d[p]}`), since a resolved key means what a written one
  means;
- **the consumer receives the folded name.** `ｎａｍｅ: 1` loads as
  `{"name": 1}`. A yapyon writer still writes the key as spelled — its
  lexeme (§3, §4.4) — so `ｎａｍｅ` comes back as `ｎａｍｅ`; a key with no
  lexeme, such as one in a function's result (§13.4), is written as its
  folded name.

Nothing warns about a folded spelling. A warning would say the author may have
meant something else, and here there is nothing else to mean.

**Addressability and searchability are different claims, and only the first is
universal.** Sequence items and multimap entries have no keys of their own and
so take no part in §5.2's scope search — but both are **reachable by explicit
traversal**: `{xs[0]}` indexes a list, and `{mm.k}` is the list view of a
multimap key.

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
  as the block marker does. A flow multimap *with* entries is reserved (§9).

Why a marker rather than simply permitting repeated keys in a mapping: ehmon 1.
A repeated key would otherwise be indistinguishable from a typo, and the
choice between "the second wins" and "collect both" would be a guess. The `+ `
says which was meant, in the document's own bytes.

---

## 8. Grammar

**`GRAMMAR §G6`** holds the phrase grammar, and `GRAMMAR §G7` the static rules
it cannot express.

One property of that grammar is load-bearing here and is cited by §12:
`scalar` has **eight** alternatives, of which exactly five are literals
readable from their own bytes and exactly three are the y-family. The
partition is exact and has no other members.

---

## 9. Reserved for future versions

Syntax that is akan in v0.4 with the door explicitly open: `yb64` and `ytb`
prefixes; **quoted keys** (the key side of the grammar's `a["b.c"]`, whose
reference side is built); a flow spelling for multimaps with entries (`{+ a: 1}`; the empty `{+}`
is built, §7.1); format
specs and conversions in holes; list interpolation; **default and variadic
parameters** for declared functions (§13.7); positional access to a multimap's entries
(`{mm[0]}`);
`---` multi-document streams; r-combos beyond `rb`/`ry`; timestamp and date
literal prefixes; **comment retention across an emit** (§4.4 normalizes, and a
round-tripper needs a design v0.4 does not have).

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

v0.4 specifies **five**, and none of their fixes changes what a document
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
| dict keys | any hashable | bare identifiers only |
| duplicate dict keys | last wins, silently | akan; `+ ` multimap if repeats are meant (§7.1) |
| identifier folding | NFKC | width variants, then NFC — `ｎａｍｅ` ≡ `name`, but `ﬁ` ≢ `fi` (GRAMMAR §G4.1) |
| identifier character set | the interpreter's Unicode version | pinned to Unicode 14.0.0; no invisible characters |
| set / tuple / complex literals | types | akan (not in the data model) |

---

## 12. Conformance: the yapyon record

A document is a **record**, a **ledger**, a **template**, or an
**assembly** (ehmon 2), and each tier contains the one before it: a record
is a ledger that splices nothing, a ledger is a template that holds no
`yt` and reads no environment, and a template is an assembly that calls no declared
function. The record is the restricted form — records are implied to be
fixed, and this one is. The tier a document needs is computable from its
bytes: a `y`, `yb`, or `ry` literal makes it a ledger, a `yt` literal or
an environment reference (`$NAME` or a call to `__ENV__`) a template, and a call to a declared
function an assembly.

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

The grammar's `scalar` has eight alternatives (§8): the five literal kinds,
plus `YSTR`, `YBSTR`, `YTSTR`. The y-family is therefore *exactly* the
non-literal set, with nothing else in it, so

> a document is a record iff no string in it carries a y-family prefix

is equivalent to §12.1. The first is the definition; the second is how an
implementation tests it. The test reads the token stream and nothing else:
**a record is identifiable by lexing alone.**

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

- **Record** — the whole of `GRAMMAR.md` except the y-family prefixes
  (`§G4.6`), holes (`§G4.7`), and the reference grammar (`§G5`); plus this
  document's §3, §7, §10, §11, and §12.
- **Ledger** — all of the above, plus `GRAMMAR §G4.7`, `§G5` except
  `ENV`, and this document's §4.4, §5 except §5.1.3–§5.1.4, and §14, and
  §13 as it applies to the built-ins other than `__ENV__`.
- **Template** — all of the above, plus `yt` (§6), `ENV`,
  §5.1.3–§5.1.4, and `__ENV__`.
- **Assembly** — all of the above, plus the whole of §13: contracts, their
  types, and calls to declared functions.

A record implementation is genuinely conforming. It needs no resolver, no
fixpoint, no template machinery, and no evaluator, which is the point: the safe
subset is declared first rather than carved out afterwards.

Of §9's reserved syntax, the items that concern holes — `yb64` and `ytb`,
format specs and conversions, list interpolation, default and variadic
parameters, positional multimap access — are **ledger and above**,
since a record has no holes at all. §5.1.1's relative references are
ledger and above for the same reason. The rest — quoted
keys, a flow spelling for multimaps, `---` streams, timestamp prefixes — would
concern both forms.

On meeting a y-family prefix, a record implementation is **akan at that
prefix's line and column**, and says so as the record rule rather than as a
syntax error: the document is well-formed yapyon, it is simply not a record.
In the same way, a ledger implementation meeting a `yt` literal or an
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
  (§5.1.2): `{cfg.__AS_JSON__(lexemes=False)}`. A keyword a built-in does
  not define is akan at the call.
- **Tier.** A document that calls a declared function is an **assembly**;
  one that holds a `yt` or reads the environment (`$NAME` or `__ENV__`)
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
  (§13.3).
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
  the code: `symbol` (required) and `from` (optional). **With `from`**, the
  implementation locates the code itself: a Python module path, or a library
  name **without** a platform suffix (`.so`, `.dll`, and `.dylib` are added
  per platform). **Without `from`**, the program loading the document
  provides the code.
- **Languages.** This version defines `python` and `c`. An implementation
  reads only its own language's entry and **ignores the others**, whatever
  their names, so one contract can serve bindings an implementation lacks. A
  function with no entry an implementation can use is akan **when the
  contract is loaded**, naming the function.
- **Any other key is akan**, at any level of the contract.
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
- `dict` and `multimap` write their key type, which must be `str` (keys are
  identifiers). It is written so that a later version can admit other key
  types without respelling.
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
**Returned data must be yapyon data**: a returned mapping's keys obey the
identifier rule and are folded (§7), so a key that is not an identifier, or
two keys that fold alike, is akan at the call, naming the function. A
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

Bare calls as values; returning a node; a key or index after a call
(`{f(x)[0]}`); default or variadic parameters; a template in a signature; contracts a document can
name.

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
`"ports/0"`, `"matrix/0/1"`. (Keys are identifiers, §7, so no key holds a
`/`.) **In a multimap node** the table is the node's own, and a path is
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
| list or single value as the argument | **akan** — TOML has no top-level form for either (operator, 2026-10-13); refused by `__AS_TOML__`'s signature |
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

`__AS_YAPYON__()` writes the argument as a **record** (§12), every value
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

*Mascot: an Osaka rabbit. Severities escalate as indifference, refusal, and
losing it entirely. On success in verbose mode: ええやん。*
