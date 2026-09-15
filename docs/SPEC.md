# yapyon — draft specification v0.1

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

Sections marked *(reserved)* name syntax deliberately akan in v0.1 but held
for future versions.

yapyon has **two forms**. The unrestricted one is described in §1–§11 and is
just *yapyon*; the restricted one is a **yapyon record**, in which every leaf
element has a literal value. §12 defines the record and states what an
implementation of each form must support.

---

## 1. Design laws

Every rule in both documents is a corollary of a small set of laws:

1. **No guessing.** Value types are visible in the syntax. There are no plain
   scalars: an unquoted word in value position is an error, never a string,
   never a boolean. (YAML's implicit typing — the Norway problem — is
   unrepresentable.)
2. **Replacement without computation.** The format can splice named values
   into strings; it can never evaluate, transform, or compute. No expressions,
   no environment, no functions.
3. **Self-containment.** A document's meaning depends only on its own bytes.
   No ambient scope, no includes, no environment variables at the format
   level. (Loaders and tools may layer such things *above* the format.)
4. **The closure law.** A splice is legal iff the target's validity is closed
   under splicing there. (This is what excludes splicing into base64 streams.)
5. **The bridge law.** Nothing crosses a type boundary without naming the
   encoding. Bytes cross into text only as base64. Text never crosses into
   bytes. Containers cross into text only via a **named serializer** (§5.1.2).
6. **The borrowing law.** A Python spelling may be borrowed iff its meaning
   survives the removal of the enclosing program. `b`/`r` pass (and are held
   bit-exact with Python); `f`/`t`/`u` fail by definition and are akan with an
   explanatory message. Everything with yapyon-native semantics is spelled in
   the `y` namespace.
7. **Errors at the point of the mistake.** Malformed input is akan (an error)
   at a line and column, at parse time — never a warning, never a silent
   reinterpretation.

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
| int | `INT` | Python rules |
| float | `FLOAT` | **no inf/nan spellings** |
| bool | `True` / `False` | capitals |
| NoneType | `None` | one spelling |
| bytes | `b"..."`, `b64"..."`, `rb"..."` | three spellings, one type |
| list | `[a, b]` flow, `- ` block | |
| dict | `{k: v}` flow, indented block | identifier keys (§7) |
| multimap | `+ ` block | keyed and ordered; keys may repeat (§7.1) |

The tenth type is **Template** (§6), produced only by `yt"..."`: a resolved
y-string handed over in parts rather than joined. It is never present in a
record (§12), since it needs the resolver.

**Numeric and keyword values carry their source lexeme** — the grammar
requires the token to keep it (`GRAMMAR §G4.3`) — and that lexeme is what
y-strings splice (§5.4). This is the one place where a value's *spelling*
survives into the data model, and §4.4 depends on it too.

`bytes` has three spellings and one type, so a loaded value does not record
which was used. An **emitter** needs that distinction and must take it from
the parse tree, not the value (§4.4).

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

An implementation that emits yapyon **must** use these spellings:

- **Strings: double quotes**, with the `"""` block form used exactly when the
  value contains a newline and the block form can hold it unambiguously — that
  is, no whitespace-only-but-non-empty line, no `"""` in the content, and no
  trailing `"`. A value ending in a newline puts the closing delimiter on its
  own line at the anchor.
- **Escape only what must be escaped**: `\` and the enclosing quote, plus
  characters below U+0020 and U+007F. Everything else stays literal, so UTF-8
  remains readable — `"café"`, never `"café"`.
- **Numbers and keywords: the source lexeme, verbatim.** `3.10` emits as
  `3.10`, `1_000` as `1_000`, `0x1f` as `0x1f`. This is §5.4's rule serving a
  second purpose, and it is why an emitter must work from the parse tree: the
  spelling is gone once the value is a host-language float.
- **Bytes: whichever of `b` / `b64` the document used.** An emitter must not
  choose an encoding on the author's behalf — the same reason §6 hands a
  consumer the bytes rather than a rendering of them.
- **Containers: block form**, except that an empty container has no block
  spelling and is written flow (`[]`, `{}`).

Normalization therefore **loses spelling but never value**. The property an
implementation must satisfy is that **reloading its output yields data equal
to reloading its input.**

**Comments do not survive**, and a conforming emitter is not required to
preserve them: comment-preserving round-trip is not specified in v0.1. An
emitter is a normalizer, not a round-tripper. *(Reserved: comment retention —
see §9.)*

*Reference implementation: `yapyon.emit`, and `python -m yapyon record`, which
normalizes a record (§12).*

---

## 5. The y-family: parse-time splicing

### 5.1 Holes and references

**Syntax: `GRAMMAR §G5`** — the `ref` production, what each bracket form
admits, what is akan inside a hole, and the avoidable-bracket shiran. One
grammar, shared by `y`, `yb`, `yt` and `ry`.

What the grammar does not say is what a reference *names*. That is this
section and §5.2.

- **A subscript's contents yield a key**, and the three bracket forms differ
  in where the key comes from. A quoted literal *is* the key. An integer is a
  list position. A **reference** names the key: `{d[p]}` is "the value of `d`
  at the key stored in `p`".
- **An inner reference resolves in the scope of the y-string's own position**
  (§5.2), *not* in the scope of the node being indexed. So
  `{mind.dialects[protocol].api_uri}` means "the entry named by **my**
  protocol", which is the whole reason the form exists. If an inner reference
  resolves to an integer it indexes, exactly as a written integer would.
- **`__ROOT__` anchors at the document root** (§5.2). One definition, one
  scope: since a `yt` resolves against the document like any other y-family
  literal (§6), there is no second scope for it to mean something else in.
- A **serializer** names an encoding of the value reached (§5.1.2).
- Holes contain **references, not expressions**. There is no arithmetic, no
  call syntax beyond the fixed serializer set, and no way to reach outside the
  document. This is law 2, and it is why the grammar is small enough to be
  implemented identically twice.

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
closure-safe by construction (law 4). Into a `yb` string it is text→bytes and
akan under law 5, by the ordinary rule and with no special case.

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

### 5.1.2 Named serializers

A container cannot be spliced into text (§5.5), because there is no one text
form for it and picking one would be guessing. A **named serializer** is the
author saying which they mean:

```
cfg:
  name: "gw"
  port: 8080
body: y"payload={cfg.__AS_JSON__()}"
```

This is law 5's reserved extension — *containers cross into text only via a
named serializer* — and it stands to a container exactly as `b64"..."` stands
to bytes: the **document author** names the encoding, in the document, where a
reader can see it.

**It is not a function call, and law 2 still holds.** A serializer takes no
arguments, cannot be composed, and the set of them belongs to the *format*
rather than to the consumer. Naming an encoding is not computing a value. That
is the boundary between this and consumer-registered functions, which v0.1
does not have.

The three names and the call syntax are `GRAMMAR §G5`; **v0.1 defines
`__AS_JSON__()`, `__AS_TOML__()` and `__AS_YAML__()`**, and a serializer
applies to a **list or a mapping**. Applying one to a single value is akan and
*reserved*.

**A serializer may not be applied to a bare anchor**, and this is a rule
rather than an accident. `{__ROOT__.__AS_JSON__()}` and
`{__PARENT__.__AS_JSON__()}` are **akan**; `{__ROOT__.blk.__AS_JSON__()}` and
`{a.__AS_JSON__()}` are legal.

**The reason is circularity, not anchors.** An anchor is *always* an ancestor
of the hole that names it — `__PARENT__` is by definition the mapping the hole
sits in, and `__ROOT__` contains it. So encoding an anchor would require the
value of the very y-string doing the encoding:

```
blk:
  a: 1
  me: y"{__PARENT__.__AS_JSON__()}"     # akan: me = {"a":1,"me":<me>}
```

There is no document in which such a reference resolves, which is what makes
this akan **at parse** rather than a cycle reported later: the mistake is
visible in the reference itself, so law 7 puts the error there. The message
names the real reason and the fix, rather than claiming the anchor names no
value — it names one perfectly well.

**Nothing useful is lost.** An anchor followed by any step leading away from
the hole is legal and is the shape authors actually want:
`{__ROOT__.blk.__AS_JSON__()}` encodes a named block, and
`{__PARENT__.blk.__AS_JSON__()}` encodes a sibling.

*(The alternative — defining the anchor form as "encode my parent, excluding
the pair I sit in" — was considered and declined. It terminates, but it makes
`__AS_JSON__()` mean something different depending on where it is written,
which is a carve-out the format does not otherwise have.)*

**Every encoding is canonical**, or the same bytes would not mean the same
data. In all three, **keys are in document order and never sorted** — order is
data in yapyon — and non-ASCII is left as itself.

| | shape |
|---|---|
| `__AS_JSON__()` | indented two spaces |
| `__AS_TOML__()` | nested mappings become tables (`[a.b]`); newline-terminated |
| `__AS_YAML__()` | block style, scalars never line-wrapped; newline-terminated |

**An implementation must not prune.** Dropping a key because its value is
`None` or `""` is a silent reinterpretation (law 7), and "the same bytes mean
the same data" has to survive a serializer. A consumer wanting that pruning
does it to its own tree first.

**A target that is not resolved yet is not an encoding failure.** If the
container still holds an unresolved y-string, the encoding **defers** to a
later pass of §5.3's fixpoint rather than refusing. Two serializers whose
targets hold each other are therefore reported as the **cycle** they are,
naming every stuck reference, rather than as a failure to encode — the
distinction is between *never encodable* and *not encodable yet*, and only the
first is akan on sight.

**Where a format cannot carry a value faithfully, the encoding is akan** —
never approximate (law 1: refuse rather than pick a reading).

- A **multimap** is akan in all three: its keys repeat, and none of these
  formats can hold that.
- **Bytes** are akan in all three: none of them names an encoding for bytes,
  so the bridge law has nothing to name.
- **`None` is akan in TOML**, which has no null. JSON and YAML write it.
- `__AS_TOML__()` requires a **mapping**: a TOML document is a table.
- Numbers encode by the **target format's** rules, not §5.4's lexeme. Inside
  JSON, `3.10` and `3.1` are one number; the lexeme rule governs splicing
  yapyon source, which this is not.

**YAML is emitted defensively.** A scalar is written plain only when nothing
else could read it as another type — so `"no"`, `"3"` and `"true"` come out
quoted. yapyon exists partly because YAML guesses; emitting into it must not
hand that problem to the reader.

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
specified a shiran here. It was removed 2026-09-14: it fired on correct
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
Nothing is picked, so law 1 is satisfied — the reference names the whole view
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

**Expansion caps** (loader-overridable defaults): resolution depth 32; total
rendered size 1 MiB per document. Exceeding either is akan. (Chained doubling
makes growth exponential; the cap is load-bearing.)

**Depth is measured as the dependency chain**, not as a count of fixpoint
passes. A pass counter makes the answer depend on the order keys happen to
appear in the document, which a format whose thesis is "the same bytes mean
the same data" cannot permit.

### 5.4 What splices: the lexeme rule

- Non-string scalars splice their **source lexeme**: `version: 3.10`
  referenced from a y-string splices the characters `3.10`; `0xFF` splices as
  `0xFF`; `1_000` keeps its underscores; `True` and `None` splice as
  themselves. What the author wrote is what appears.
- Strings splice their **content** (the decoded value, not the quoted lexeme),
  so chains compose.
- Resolved y-strings splice their resolved result. Result strings are inert.

This is only possible because resolution happens at parse time, while lexemes
still exist; `GRAMMAR §G4.3` is what guarantees they do.

### 5.5 The splice matrix

| Hole in… | str | b-bytes | b64-bytes | int/float/bool/None | container | yt value |
|---|---|---|---|---|---|---|
| `y` / `ry` | ✓ content | akan¹ | ✓ as base64 text | ✓ lexeme | akan² | akan³ |
| `yb` | akan⁴ | ✓ decoded | ✓ decoded | ✓ ASCII lexeme | akan | akan |
| `yt` carry (§6) | ✓ | ✓ | ✓ | ✓ | ✓ | akan³ |
| `yt` render (§6) | *as `y`* | *as `y`* | *as `y`* | *as `y`* | *as `y`* | — |

¹ b-spelled bytes have no text form; the akan says "respell as b64 to splice
into text." &nbsp; ² container = list, dict, or multimap: "cannot interpolate
a list, dict, or multimap into a string" *(the named bridge is §5.1.2's
`__AS_JSON__()`)*. &nbsp; ³ "cannot splice a template into a string."
&nbsp; ⁴ no implicit encode, ever (PEP 461's wall, both sides).

**A `yt` has no matrix of its own.** It *carries* anything, because nothing
crosses into text when a value is handed over rather than joined; and its
canonical render (§6.3) reproduces the `y` row cell for cell, which is what
makes it an unjoined y-string rather than a second construct. The one
difference is *when* a refusal lands: a `y` is always joined, so it akans at
parse; a `yt` akans only if a consumer asks for the join.

---

## 6. yt — the yapyon template

**A `yt` literal is a y-string that is not joined.** Its holes resolve against
the document at parse time by §5.2's ordinary rules, exactly as `y`'s do. The
difference is delivery: `y` joins the parts into a string; `yt` hands the
consumer the literal text parts and the resolved values, separately.

    y : yt  ::  f-string : t-string

Interior syntax is identical to any other y-family literal (`GRAMMAR §G5`) —
one scanner, one divergence-table row. An unbound hole is akan **at parse**,
like any other unresolved reference: the mistake is in the document, so it
lands on the document's author (law 7).

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
and picking one would be guessing (law 1). Pre-parse text substitution is also
where injection lives: a value containing a quote and a newline can add a
key its author never wrote, whereas splicing replaces a value in the parsed
tree and is structurally incapable of that.

### 6.2 What a consumer receives

An implementation **must** deliver, per literal:

- the **literal text parts**, in order, and
- for each hole, its **resolved value**, the **source lexeme** of that value
  where it has one (§5.4), and the **reference as written**.

The lexeme is required, not decorative: `version: 3.10` resolves to a value
that in most languages is indistinguishable from `3.1`, and without the
spelling no consumer could render it faithfully.

The alternation is **total**: text, value, text, value, … text. A literal
begins and ends with a text part, and an empty text part sits between adjacent
holes, so a consumer never special-cases a leading, trailing or doubled hole.
There are always exactly one more text parts than holes.

### 6.3 Carrying versus rendering

**Carrying is unconstrained.** A hole may carry any value a document can hold,
containers and b-spelled bytes included. §5.5 constrains what may cross into
*text*, and nothing crosses into text here — the consumer that wants hex
rather than base64 receives the bytes and encodes them itself. This is what
the bridge law (law 5) was asking for: a document author has no code to run
and must spell `b64"..."`, while a consumer is code and can name its own
encoder.

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

Splicing a `yt` into a `y`, `yb` or another `yt` is **akan**. Joining one
would discard the parts it exists to preserve.

A `yt` is **not** permitted in a record (§12), for the same reason `y` is not:
it requires the resolver, and a record is the form that needs none.

---

## 7. Keys

**Syntax: `GRAMMAR §G4.1`** (identifiers and the Unicode-version requirement),
**`§G4.2`** (the reserved dunder vocabulary), **`§G7`** (keys are bare names;
keywords, dunders, duplicates and every other key form are akan).

What belongs here is the **consequence**, which is a claim about
addressability rather than about well-formedness:

> **Every key of a mapping is addressable from a hole.**

This holds only because the grammar applies **one predicate** to keys and to
hole segments. Widen either alone and the claim becomes false — which is how
it broke twice: `a²` was admitted as a key by `str.isalnum()` and could be
named by nothing, and `__foo__` was a legal key whose hole akaned.

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
- Entry keys are **invisible to holes** (§5.2). There is no flow spelling in
  this version (§9).

Why a marker rather than simply permitting repeated keys in a mapping: law 1.
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

Syntax that is akan in v0.1 with the door explicitly open: `yb64` and `ytb`
prefixes; **quoted keys** (the key side of the grammar's `a["b.c"]`, whose
reference side is built); a flow spelling for multimaps (`{+ a: 1}`); format
specs and conversions in holes; list interpolation; **negative indices**
(`{xs[-1]}`); **escapes inside a quoted hole key**; **applying a serializer to
a single value**; positional access to a multimap's entries (`{mm[0]}`);
`---` multi-document streams; r-combos beyond `rb`/`ry`; timestamp and date
literal prefixes; **comment retention across an emit** (§4.4 normalizes, and a
round-tripper needs a design v0.1 does not have).

**A reservation is a promise, not a plan.** Items arrive on this list by being
argued individually; nothing should be built from it because it appears here,
and nothing should be inferred to be wanted because it sits beside something
that is.

*Built and therefore no longer reserved: `__PARENT__` and `__KEY__` (§5.1.1);
all three named serializers, `__AS_JSON__()`, `__AS_TOML__()` and
`__AS_YAML__()` (§5.1.2); quoted hole segments (`{a."b.c"}` → `{a["b.c"]}`)
and interior addressing of lists and multimaps (`{xs.0}` → `{xs[0]}`,
`{mm.key}` → a list view), both subsumed by the subscript rather than added
beside it. `self` was withdrawn rather than built — it named a consumer's own
key convention, not anything the format needed.*

---

## 10. Diagnostics

| Register | Meaning | Example |
|---|---|---|
| `shiran:` | legal but suspicious; parsing continues | a bracket where a dot would do, `{a["bar"]}` (`GRAMMAR §G5.4`) |
| `akan:` | error; the document does not parse/resolve | bare word in value position |
| `yakamashiwa:` | internal invariant violated — a bug in the implementation, not the document | indent stack underflow |

Every akan carries a line and column and, wherever a fix is mechanical, names
it in the message ("write `{{` for a literal brace"; "respell as b64").

**A shiran must fire where something is probably a mistake**, not merely
unusual, and a shiran whose suggested fix would change what a document means
is not a warning but a trap. v0.1 specifies exactly one, and it is about
spelling alone: taking its advice changes nothing.

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
| `f"..."` / `t"..."` / `u"..."` | formatted / template / no-op | akan with hint (borrowing law) |
| `y*` prefixes | syntax error | yapyon-native (holes, §5) |
| prefix spelling | `rb`/`br`, any capitalization | canonical only (`rb`, lowercase) |
| `inf` / `nan` | via `float()` | no spelling |
| dict keys | any hashable | bare identifiers only |
| duplicate dict keys | last wins, silently | akan; `+ ` multimap if repeats are meant (§7.1) |
| NFKC identifier folding | applied | not applied (exact codepoints) |
| set / tuple / complex literals | types | akan (not in the data model) |

---

## 12. Conformance: the yapyon record

yapyon has two forms. The unrestricted one is just **yapyon**, and is what
§1–§11 and the grammar together describe. The restricted one is a **yapyon
record** — records are implied to be fixed, and this one is.

### 12.1 The rule

> **Every leaf element has a literal value.**

A literal is readable from its own bytes: a quoted string, a bytes literal, a
number, or a keyword (§3). Nothing about a leaf's value depends on anything
else in the document. Containers — mapping, sequence, multimap — are structure
rather than leaves, so the rule reaches all the way down.

This is law 3 stated at the leaf: self-containment, made local. It also
explains why the existing akans are the right ones — a bare word is not a
literal (law 1, no plain scalars), and `key:` with nothing after it is not a
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
  meaning: a full implementation loading a record returns exactly what a
  record implementation returns.
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
| §5.3 expansion caps | n/a | apply |
| Values produced | str, bytes, int, float, bool, None, list, dict, multimap | the above, plus Template |

A multimap (§7.1) is permitted in a record. It is a yapyon-specific type, but
it is plain keyed data rather than deferred structure; the criterion is
"nothing deferred", not "builtin types only".

### 12.5 Conformance

An implementation **must state which form it implements**. There are two:

- **Record** — the whole of `GRAMMAR.md` except the y-family prefixes
  (`§G4.6`), holes (`§G4.7`) and the reference grammar (`§G5`); plus this
  document's §3, §7, §10, §11 and §12.
- **Full** — all of the above, plus `GRAMMAR §G4.7`, `§G5`, and this
  document's §4.4, §5 and §6.

A record implementation is genuinely conforming. It needs no resolver, no
fixpoint, no template machinery and no evaluator, which is the point: the safe
subset is declared first rather than carved out afterwards.

Of §9's reserved syntax, the items that concern holes — `yb64` and `ytb`,
format specs and conversions, list interpolation, negative indices, escapes
inside a quoted hole key, serializers on a single value, positional multimap
access — are **full form only**, since a record has no holes at all. §5.1.1's
relative references are full form only for the same reason. The rest — quoted
keys, a flow spelling for multimaps, `---` streams, timestamp prefixes — would
concern both forms.

On meeting a y-family prefix, a record implementation is **akan at that
prefix's line and column**, and says so as the record rule rather than as a
syntax error: the document is well-formed yapyon, it is simply not a record.

*Reference implementation: `yapyon.loads_record` and `yapyon.load_record` load
a record; `yapyon.is_record` performs the §12.2 test without loading.*

---

*Mascot: an Osaka rabbit. Severities escalate as indifference, refusal, and
losing it entirely. On success in verbose mode: ええやん。*
