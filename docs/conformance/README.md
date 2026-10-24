# yapyon conformance corpus

*A second implementation passes this corpus or it does not conform.*

`docs/SPEC.md` says what yapyon bytes mean and `docs/GRAMMAR.md` says which
bytes are well-formed. This directory is where those words get **checked**.
Every case here is data, not code in a language — a port in Mojo, Rust or
anything else runs the same files against its own loader and gets a yes or
no.

The point is the format's thesis, made testable: **the same bytes mean the
same data**, to every parser, on every machine, always. A claim that grand
needs an oracle.

---

## Layout

```
docs/conformance/
  README.md                 this file
  cases/
    record/   <name>.yap            input: a record (SPEC §12)
              <name>.expected.yap   the same data, as a record
    full/     <name>.yap            input: a full document
              <name>.expected.yap   what it resolves to, as a record
    error/    <name>.yap            input that must be refused
              <name>.meta.json      which rule it refuses, and why
    full/, error/
              <name>.env.json       optional: the environment it loads in
```

**The record is the assertion language.** An expectation is not JSON, not a
Python literal, not a dump of some host type — it is a yapyon record, the
literal-only form that needs no resolver (§12). So the corpus says *"these
bytes denote this data"* in the format's own terms, and the tier model shows
up directly in the file pairs: a full document crosses down to a record, and
that crossing **is** the test.

---

## The three kinds

| kind | loader for input | loader for expected | pass condition |
|---|---|---|---|
| `record/` | `loads_record` | `loads_record` | both load to equal data, same key order |
| `full/` | `loads` | `loads_record` | resolved input equals the record |
| `error/` | `loads`, or `loads_record` if `meta.loader == "record"` | — | the loader raises `akan` |

Two self-checks run on the corpus itself, so a case cannot be quietly
misfiled: a `record/` input must report `tier_of == 1`, and a `full/` input
must **not**. A full-form document parked under `record/` would be testing
the resolver while claiming not to, which is worse than having no case.

### Environments

A `full/` or `error/` case loads in an **empty environment** unless a
`<name>.env.json` beside it declares one, so no case depends on the machine
running it:

```json
{"env": {"HOME": "/h", "API_KEY": "s3cret"}, "allow": "posix-standard"}
```

- `env` — the variables, name to value; `null` means environment access is
  **off** (SPEC §5.1.3).
- `allow` — which names are exposed (§5.1.4): `"posix-standard"` (the
  default), `"windows-standard"`, `"all"`, or a list of names.

Run the case with exactly that environment and exposure, whatever your
host's own. Names in the corpus are written in the case their standard
spells them, so a case means the same on a case-insensitive system.

**Assemblies are not in the corpus.** A document that calls a declared
function (SPEC §13, tier 4) means nothing without a contract and the code
it binds, and that code is per-language — a corpus case could not carry it
portably. Calls to the **built-ins** are covered (`full/19-calls`), and a
call to an undeclared name with no contract is covered as an error.

**Filling slots is not in the corpus either.** A slot (SPEC §15) is filled
by its consumer, through an implementation's own API, so a case cannot
say how to fill one portably. What a document alone determines is
covered: how a slot is written, and that one left unfilled is akan.

---

## Running it

yapyon's own runner:

```sh
python tools/run_conformance.py          # summary
python tools/run_conformance.py -v       # every case
python tools/run_conformance.py -d DIR   # another corpus
```

Exit status is 0 only when every case passes. The suite runs the whole
corpus too, one pytest case per corpus case, so a case cannot rot.

**For a new implementation**, the protocol is the table above and nothing
else. Read the input with your loader, read the expectation with your record
reader, compare data and key order. For an `error/` case, assert that your
loader refuses. You do not need yapyon to run this corpus against yourself.

---

## What is pinned, and what deliberately is not

**Pinned:** the data a document denotes, the type of every value, the order
of every mapping's keys, the order of every sequence, a multimap's entry
sequence, and that certain inputs are refused.

**Not pinned: the text of an error message.** An error case's sidecar
carries a `rule` (`SPEC §4.3`) and a `why`, and those are the contract. A
message is UX and a port should write its own; two implementations that word
a refusal differently are not diverging. What must agree is *that* it
refuses, and *which rule* it is refusing under.

**Key order is pinned** even though most host languages' map equality
ignores it, because order is data in yapyon. A port that sorts every
mapping passes `==` and fails here.

---

## How these cases were written, and why they differ from their input

The obvious way to produce an `<name>.expected.yap` is to run yapyon's own
`expand` over the input and keep what comes out. **That would make this
corpus yapyon comparing itself to itself** — a reader bug would be baked
into the expectation and the case would pass forever while testing nothing.

So every expectation here is written by hand from the spec, and where the
spec says two spellings denote the same data, the two files use
*different* spellings on purpose:

- `b"hi"` against `b64"aGk="` — a reader that mishandles either prefix
  fails the pair.
- `name` against `ｎａｍｅ` — the same identifier after width-fold (§7), so
  the expectation is written folded, which is what a consumer receives.
- block style against flow style — one structure, two layouts.
- `3.140` splicing as `"3.140"` — as a value `3.140 == 3.14`, so only
  the lexeme rule (§5.4) tells them apart, and only a case like this catches
  a port that splices `repr(value)`.

A pair like that is an oracle precisely because the two sides are not
identical. Where they must be identical — a multimap's entry sequence, key
order — the case says so and the runner checks it.

**Every gate here was proved by breaking it on purpose before it was
trusted:** a wrong value, a swapped key order, an error case made valid, a
record-tier file made full-form. Each produced a FAIL. A green gate and an
inert gate look identical from outside, and only the break tells them apart.

---

## Coverage

- **`record/` — the record tier, complete.** Every scalar type, all four
  string quoting forms, the escape table, bytes in both spellings, number
  spellings, empty containers, nesting, block vs flow, multimaps, Unicode
  values, the identifier folding rule, comments, and key order. This is
  what a record-only implementation needs to pass, and it is what unblocks
  a port that has no resolver.
- **`full/` — the core of the full tier.** The lexeme rule (§5.4),
  nearest-wins resolution and the `__ROOT__` escape hatch (§5.2), relative
  references `__PARENT__` / `__KEY__` (§5.1.1), the dot as sugar for the
  bracket, indirect keys, negative indices and the multimap list view
  (§5.1), chained splices through the fixpoint (§5.3), and all four
  serializers including TOML arrays of tables (§5.1.2).
- **`error/` — the major refusals.** Non-canonical base64, invalid base64,
  duplicate keys including duplicates that appear only after folding, tab
  indentation, unknown escapes, reserved quoted keys, dunder keys,
  unbound holes, a serializer on a bare anchor, a multimap in a
  serializer, `None` in TOML, bytes in JSON, a `yt` in `__as_yapyon__()`,
  and a full document refused by `loads_record`.
- **The environment (§5.1.3, §5.1.4)** — `{$NAME}`, `__env__` with and
  without a fallback, an empty value, a `$` reference as a receiver and as
  a bracket key, a variable that is not exposed, a widened exposure; and as
  errors, an unset variable, an unexposed one, a step after `$NAME`, a bad
  name, and access off with a fallback.

**`yt` is deliberately absent from `full/`.** A `yt` value is a template
delivered in parts (§6), and a record cannot express one — `expand_record`
refuses it rather than joining it, because §6 puts rendering with the
consumer. A corpus whose expectations are records therefore cannot carry a
`yt`, and that is the rule working, not a gap. The same rule is why `yt`
appears once, in `error/`: `__as_yapyon__()` writes a record, so a `yt` in
its target is refused.
