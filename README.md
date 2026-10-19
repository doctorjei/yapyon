# yapyon (やぴょん)

> 「YAMLちゃうで。やぴょんやぴょん」
> *It's not YAML. It's yapyon.*

Python-style typed literals with YAML-like block structure. Quoted strings,
`True`/`False`/`None`, indentation blocks, `-` sequences, `+ ` multimaps,
`#` comments — and parse-time splicing that replaces YAML's anchors.

```yapyon
name: "api-gateway"
version: "3.10"
port: 8080
debug: False

paths:
  root: "/srv/gateway"
  logs: y"{root}/logs"          # -> "/srv/gateway/logs"
  banner: y"{name} v{version}"  # -> "api-gateway v3.10"

changes:                        # multimap: keys may repeat, order is data
  + registry: {set: ["Bypass"]}
  + file: {delete: ["Edge"]}
  + registry: {remove: ["Edge Update"]}
```

**The pitch:** the same bytes mean the same data, to every parser, on every
machine, always. No implicit typing (`no` is not `False`; there are no
unquoted scalars at all), no anchors, no tags, no evaluation, one null
spelling, one document per file. A repeated key is an error unless the block
says `+ `, so it can never be mistaken for a typo — or silently collapsed,
the way Python and YAML both drop `{"a": 1, "a": 2}` down to one entry.

## Status

**`0.3.0`**, built to specification **v0.3**. Lexer, parser, resolver,
loader, emitter, the four serializers, and contracts are done and tested,
including a conformance suite that turns the splice matrix and the Python
divergence table into executable cases, and a portable corpus in
`docs/conformance/` that another implementation can run against itself. The
suite is **1416 tests** on the current tree; the number here tracks the tree,
not a release.

A document is one of three kinds, and `yapyon.tier_of` says which (§12.5):
a **record** (1) is literals only and needs no resolver; a **template** (2)
splices and calls built-ins, and resolves from its own bytes alone; an
**assembly** (3) calls functions that a **contract** declares, which the
program loading it supplies. There is no ambient scope, no includes, and no
environment at the format level: a document reaches outside itself only
through a contract its loader was handed, never one it names — so its reach
is something you can *prove* rather than audit.

**The normative specification is published, in two documents under
[`docs/`](docs/):**

| | |
|---|---|
| [`docs/GRAMMAR.md`](docs/GRAMMAR.md) | *are these bytes well-formed yapyon?* — self-contained, normative for syntax |
| [`docs/SPEC.md`](docs/SPEC.md) | *what do well-formed bytes mean?* — normative for meaning |
| [`docs/conformance/`](docs/conformance/) | *does an implementation agree?* — 65 portable cases; the directory's own README is the protocol |

The corpus is not a third normative document: it is **derived from** the
other two, and where they disagree the spec wins and the case is wrong. What
it adds is a check rather than a definition — every case is data, not code
in a language, so a second implementation runs the same files against its
own loader and gets a yes or no.

New to the format? [`docs/TUTORIAL.md`](docs/TUTORIAL.md) walks through it
from first values to contracts, with every example executed by the suite.

References run one way: the spec cites the grammar, the grammar cites
nothing. A parser can be written from the grammar alone, which is the point of
separating them. This README summarizes the format; those documents define it.

**Identifiers are UAX #31, pinned to Unicode 14.0.0, with invisible
characters excluded.** yapyon ships its own table rather than asking the
interpreter, so a key means the same thing on every install and every Python.
Width variants and canonically equivalent spellings are the same name —
`ｎａｍｅ` is `name`, and `é` is `é` however it was composed — while `ﬁ` and
`fi` stay distinct. `yapyon.UNICODE_VERSION` names the pinned version.

```console
$ pip install yapyon
```

```python
>>> import yapyon
>>> yapyon.loads('name: "gw"\nport: 8080\naddr: y"{name}:{port}"\n')
{'name': 'gw', 'port': 8080, 'addr': 'gw:8080'}
```

`loads` and `load` return plain Python. Eight of the ten types are builtins;
a `+ ` block comes back as an `OrderedMultimap`, and a `yt` literal as a
`Template`.

## Templates

`yt` is a y-string that is **not joined**. Its holes resolve against the
document exactly as `y`'s do; the consumer receives the literal text and the
resolved values separately, and renders them itself.

```python
>>> d = yapyon.loads('user: "; rm -rf /"\ncmd: y"echo {user}"\ntmpl: yt"echo {user}"\n')
>>> d["cmd"]
'echo ; rm -rf /'
>>> list(d["tmpl"])
['echo ', Hole('user', '; rm -rf /'), '']
```

`y` : `yt` :: f-string : t-string. A joined string has lost which bytes the
author wrote and which came from the data, and nothing downstream can recover
it; parts keep them apart until a consumer that knows the destination — shell,
SQL, HTML, a registry — decides how each value is made safe.

A hole carries `.value` (typed), `.lexeme` (the document's spelling of that
value, quotes and prefix included, where it has one) and `.ref` (the reference
as written). Carrying is unconstrained — a hole may hold a list or raw bytes,
because yapyon is not the one rendering. `render()` joins canonically and
reproduces exactly what the equivalent `y` produces; it is an explicit call,
never an implicit `str()`, because an easy implicit join would undo the point.

## Records

A **yapyon record** is the restricted form in which *every leaf element has a
literal value* — no splicing, no templates, nothing deferred. It is a strict
subset: every record is a valid yapyon document meaning the same thing.

```python
>>> yapyon.loads_record('name: "gw"\nport: 8080\n')
{'name': 'gw', 'port': 8080}
>>> yapyon.is_record('addr: "{name}:80"\n')   # braces in a plain string are inert
True
>>> yapyon.loads_record('name: "gw"\naddr: y"{name}:80"\n')
Traceback (most recent call last):
yapyon.lexer.AkanError: akan: line 2, col 6: a record's leaves must all be
literals; a y-string defers its value (load with yapyon.loads for the full form)
```

`loads_record` / `load_record` are the whole pipeline minus the resolver, and
a separate function rather than a keyword argument — the safe path should not
be one typo away from the unsafe one. `is_record` answers the question by
lexing, without loading.

This is why an implementation with no resolver can still be a conforming one:
the safe subset is declared up front rather than carved out afterwards — and
why the spec asks every implementation to say which of the two it provides.
**yapyon implements the full form**, and so also loads records.
*(New in `0.1.0a2`.)*

A record also prints back out as yapyon, normalized:

```console
$ python -m yapyon record examples/registry.yap
```

Every literal comes back as the author wrote it — `3.10` stays `3.10` rather
than becoming `3.1`, `'x'` keeps its quotes, `b"..."` is not respelled as
base64 — and only layout is normalized (block containers, the writer's
indentation). It works from the parse tree for that reason; the source
spelling is gone once a value is a Python `float`.
**Comments do not survive**, so this is a normalizer rather than a
round-tripper. `yapyon.emit` is the same thing as a function. A non-record is
refused at the offending prefix, with the record rule as the reason.

## Limits

Resolution has two tiers (SPEC §5.3), and they are different numbers.

| | Threshold | Exceeding it |
|---|---|---|
| Warn tier — fixed by the spec | depth 32, rendered size 1 MiB | `shiran`, and resolution continues |
| Refusal ceiling — this implementation's | depth 128, rendered size 4 MiB | `akan` |

```python
>>> deep = 'a0: "x"\n' + "".join(f'a{i}: y"{{a{i-1}}}"\n' for i in range(1, 41))
>>> yapyon.loads(deep, warn=print)["a40"]
shiran: line 41, col 5: a dependency chain 40 deep passes §5.3's warn threshold
(32); this document is costly to resolve and an implementation may refuse it
-- shorten the chain, or raise max_depth where it is loaded
'x'
```

Move the ceiling with `loads(..., max_depth=…, max_size=…)`. The warn tier is
not an argument: a consumer chooses what it will *refuse*, not what the format
calls suspicious.

The ceiling is not optional and is deliberately finite — chained doubling is
exponential, so a document of a few dozen lines can demand unbounded memory,
and a resolver with no ceiling is a denial-of-service in anything that parses
configuration it did not write. The spec declines to fix one ceiling for every
implementation; it does not suggest having none.

Both tiers are about cost alone. A **cycle or a missing target is always an
akan** at any depth, because it can never resolve.

From a checkout, the stages will also dump what they see:

```console
$ pip install -e ".[dev]" && pytest -q
$ python -m yapyon lexer  examples/gateway.yap   # token dump
$ python -m yapyon parser examples/gateway.yap   # AST dump
$ python -m yapyon tier   examples/gateway.yap   # 2 — this one needs the resolver
$ python -m yapyon expand examples/bridge.yap    # level 2 in, a record out
```

Every stage writes its output to stdout and its diagnostics to stderr, and
**shows shirans by default** — the library hides them behind `warn=`, but a
person at a terminal asked. A shiran does not change the exit status; an akan
exits 1.

## References

A hole names a value. `a.b` is sugar for `a["b"]` — the bracket is the
general form, and its content yields a key.

```yapyon
protocol: "claude"
mind:
  endpoint: "https://api"
  dialects:
    claude:
      api_uri: y"{endpoint}/v1"        # reaches its uncle by §5.2 scope
    codex:
      api_uri: y"{endpoint}/responses"
  chosen: y"{dialects[protocol].api_uri}"   # -> "https://api/v1"
```

| Spelling | Means |
|---|---|
| `{a.b}` | the key `b` — canonical for identifiers |
| `{a["b.c"]}` | a key a dot cannot reach |
| `{xs[0]}` | a list position; brackets only, since `0` is no identifier |
| `{d[p]}` | the key *stored in* `p`, resolved in the y-string's own scope |
| `{mm.k}` | every value filed under `k` in a multimap, in order, as a list |

`{a["bar"]}` where a dot would do is a `shiran` — legal, but say `{a.bar}`.
Because the enclosing string's delimiter ends it, quote a key with the other
mark: `y"{a['b']}"`.

### Relative references

`__ROOT__` names an absolute position; `__PARENT__` and `__KEY__` name
relative ones, so a block can refer to where it *is*:

```yapyon
store: "/cfg"
personas:
  kimi:
    id:     y"{__PARENT__.__KEY__}"              # -> "kimi"
    prompt: y"{__ROOT__.store}/{__PARENT__.__PARENT__.__KEY__}/{__PARENT__.__KEY__}.md"
```

The same text in every block, each resolving to its own name — without them a
block cannot be renamed or moved without editing its contents. `__PARENT__`
repeats (`{__PARENT__.__PARENT__.x}`) and leads a reference; `__KEY__` ends
one. Bare `{__KEY__}` is the *pair's own* key, which is rarely what you want.

### Serializers

A container cannot be spliced into text — there is no one text form and
picking one would be guessing. Naming the encoding is how it crosses:

```yapyon
store:
  model: "m1"
  host: "https://api.example.com/v1"
body: y"{store.__AS_TOML__()}"
```

```toml
model = "m1"
host = "https://api.example.com/v1"
```

`__AS_JSON__()`, `__AS_TOML__()`, `__AS_YAML__()`, and `__AS_YAPYON__()` are
the format's built-in functions, all written without a runtime dependency, and
their output is fixed exactly by SPEC §14 — layout included, so every
implementation writes the same text. Keys stay in document order and nothing
is pruned. Where a format cannot carry a value directly, the serializer
**approximates** it by that format's own means rather than refusing: bytes
become base64url text and a `0xff` its value, each with its yapyon spelling
recorded beside it in an `@_lexemes` member; a multimap becomes a JSON-LD
node, TOML dotted keys, or YAML `!!pairs` under a `%TAG` handle; TOML leaves
out a `None` and records it. A reader that knows the conventions gets the
yapyon value back; one that does not still gets correct plain data. YAML
scalars are quoted unless every reader would read them as strings, so `"no"`
and `"3"` survive as strings. `{cfg.__AS_JSON__(lexemes=False)}` writes the
plain values alone.

`__AS_YAPYON__()` writes the block as a yapyon **record**, every value as
written: `3.10` still spelled `3.10`, multimaps and bytes as themselves. The
only thing any serializer refuses is a `yt`, which has no record form, and
`__AS_TOML__()` refuses what is not a table, since TOML has no top-level form
for anything else.

A serializer names the value it encodes, so it cannot name a *bare* anchor:
`{__PARENT__.__AS_JSON__()}` would have to encode the string it is computing,
and is akan. Reach past the anchor — `{__ROOT__.blk.__AS_JSON__()}` — which is
the shape you want anyway.

### Functions and contracts

A hole may call a function — `{match_first(supported, mind.dialects)}`, or
the receiver form `{supported.match_first(mind.dialects)}` — if the loader is
given a **contract** declaring it. A contract is itself a record:

```yapyon
match_first:
  params:
    keys: "list[str]"
    items: "dict[str, dict[str, str]]"
  returns: "str"
  impl:
    python: {from: "persona_grata.dialects", symbol: "match_first"}
```

```python
import yapyon

with open("functions.yap") as fp:
    contract = yapyon.load_contract(fp)
with open("persona.yap") as fp:
    data = yapyon.load(fp, contract=contract)
```

Without `from`, the loader supplies the code: `provide={"match_first": fn}`.
Arguments are checked against the declared types before the call — deep,
and reported where the offending value is written — and a container
argument arrives as a read-only, ordered **borrow** of the document's node.
The result is checked against `returns` and becomes fresh data. Calls nest
and chain, and wait for their arguments like any hole, so two calls waiting
on each other are reported as the cycle they are. A function that raises is
akan naming it, never a traceback. The serializers are the format's
**built-in** functions, called the same way and declared by the spec itself.

### Resolving a reference from code

A consumer that assembles a tree from several loaded documents can resolve a
reference against it **by the same rules a hole uses**, without writing its
own copy of the search:

```python
tree = yapyon.loads(base)
tree["harness"] = harness = yapyon.loads(harness_doc)
yapyon.lookup(tree, harness, "mind.dialects[protocol].api_uri")
```

`current` is the node you are holding, and the answer is the one a
`y"{...}"` written inside it would get: its own keys first, then outward,
nearest winning — which is why the tree comes too, since a dict does not
know its parents. The whole hole grammar works, serializers included, and
an indirect key like `[protocol]` resolves from `current`. It is the
resolver's own search, so the two cannot disagree. A refusal is an
`AkanError` naming where `current` sits.

## Prefixes

| Spelling | Name | Spoken | Result |
|---|---|---|---|
| `b` | bytes literal | — | bytes |
| `bin dna oct hex c32 b64` | stream literals: symbols in a radix | — | bytes |
| `r`, `rb` | raw | — | str, bytes |
| `y` | yapyon string | y-string | str, spliced at parse |
| `yb` | yapyon byte string | yeeb-string | bytes, spliced at parse |
| `yt` | yapyon template string | yeet-string | Template, unjoined |
| `ry` | raw yapyon string | ree-string | str, backslash literal |

`f"..."`, `t"..."`, `u"..."` are errors with hints — their meaning depends on
an enclosing scope, and a data file has none.

## Diagnostics

`shiran:` (warning) → `akan:` (error) → `yakamashiwa:` (internal bug).
Verbose success prints `ええやん`.
