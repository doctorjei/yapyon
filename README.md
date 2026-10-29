# Yapyon (やぴょん)
> 「YAMLちゃうで。やぴょんやぴょん」 ( *It ain't YAML. It's Yapyon.*🐇)

Yapyon is a Python-style typed literals with YAML-like block structure, including...

```yapyon
# Comments!

features:
  explicit_literal_types: True        # 'no' != False... or Norway
  lexeme_preserving_templates: True   # 3.10 is displayed 3.10, not 3.1!

ambiguous_conversions: None

builtin:
  - 'byte_encodings'           # Standard, base64, crockford32, hex, etc...
  - 'serializers'              # To JSON, YAML, TOML, and of course Yapyon!

types:
  scalar: ['bool', 'int', 'float', 'str (always quoted!)', 'None']
  containers: ['list', 'dict', 'multimap', 'bytes', 'template strings']

encodings:
  + bytes: b'Python-style' # Same as it ever was...
  + bytes: dna'GATTACA'    # Base-4... and more!
  + int: 0z1A              # Crockford base32 (42, naturally)
```

**The pitch:** the same bytes with the same inputs yield the same data, to every parser, on every machine, always. There's no implicit typing: `no` is not `False`, and strings are always quoted; there are no anchors or tags, one null spelling, and one document per file. A repeated key in a map is an error, never an uncaught typo silently overwriting data.

## Quick-Start Guide

Yapyon is just a pip / pipx / uv install away:
```
$ pip install yapyon
```

It can be quickly tested, too:
```python
>>> import yapyon
>>> yapyon.loads('name: "gw"\nport: 8080\naddr: y"{name}:{port}"\n')
{'name': 'gw', 'port': 8080, 'addr': 'gw:8080'}
```

The `loads` and `load` functions return plain Python. Types include builtin Python types as well as `OrderedMultimap` (`+`-syntax) and `Template` (`yt`-string).

Python data can be saved as a record, without evaluating document expressions:

```python
>>> text = yapyon.dumps({"name": "gw", "ports": [8080, 8443]})
>>> print(text, end="")
name: "gw"
ports: [8080, 8443]
>>> yapyon.loads_record(text)
{'name': 'gw', 'ports': [8080, 8443]}
```

`dump(value, fp)` writes to an already-open text stream. `dump_safe(value, path)`
adds checked file replacement and recovery reporting; its verified file-protection
support is currently Linux-only. See [exporting Python values](docs/DETAILS.md#exporting-python-values)
for limits, permissions, recovery, and caller-owned input synchronization.
Use `Tree.to_source()` instead when unfinished expressions or slots must survive.

Some other quick commands:
```
$ python -m yapyon record examples/registry.yap  # A Yapyon record
$ python -m yapyon lexer  examples/gateway.yap   # token dump
$ python -m yapyon parser examples/gateway.yap   # AST dump
$ python -m yapyon tier   examples/gateway.yap   # tier 3 — it carries a yt
$ python -m yapyon expand examples/bridge.yap    # a ledger in, a record out
```

## Read More

- [Tutorial](https://github.com/doctorjei/yapyon/blob/main/docs/TUTORIAL.md) — learn the format by example
- [Details](https://github.com/doctorjei/yapyon/blob/main/docs/DETAILS.md) — the long-form guide: every feature, the API, and the CLI
- [Specification](https://github.com/doctorjei/yapyon/blob/main/docs/SPEC.md) — what yapyon bytes mean (normative)
- [Grammar](https://github.com/doctorjei/yapyon/blob/main/docs/GRAMMAR.md) — which bytes are well-formed yapyon (normative)
- [Collection comprehensions](docs/DETAILS.md#collection-comprehensions) — typed list, dictionary, and multimap construction
- [Merging values](docs/DETAILS.md#merging-values) — composition, field replacement, and unfinished-source persistence
- [Conformance corpus](https://github.com/doctorjei/yapyon/tree/main/docs/conformance) — portable test cases for a second implementation
- [Changelog](https://github.com/doctorjei/yapyon/blob/main/CHANGELOG.md)

## Diagnostic Terminology

`shiran:` (warning) → `akan:` (error) → `yakamashiwa:` (internal bug).
Verbose success prints `ええやん`.

## Document Variants

A document is one of four kinds (discoverable via `yapyon.tier_of()`):
- **record**: literals only (no resolver / resolution process)
- **ledger**: splices, constructs and composes values, and calls built-ins; resolves internally
- **template**: holds slots or `yt` strings, or reads the loading process's environment
- **assembly**: calls functions that a **contract** declares; can be assembled from multiple files

Yapyon has no ambient scope nor includes and is built to be completely auditable / verifiable.

## Value composition and unfinished source

The **`0.6.0` line** adds explicit composition and faithful
saving of unfinished layers. `|` combines complete values; `:` uses ordinary
combination at a field, while `:=` replaces that field's complete value:

```yapyon
settings:
  paths: ["base", "shared"]
  reset: ["old"]
  |
  paths: ["shared", "new", "shared"]
  reset:= []
```

Here `paths` becomes `["base", "shared", "new", "shared"]`, and `reset`
becomes `[]`. Dictionaries match unique keys recursively. Lists match whole
typed elements, and multimaps match whole key/value pairs: each equal item
keeps the larger count from either input, not the sum. Earlier positions
stay; unmatched incoming occurrences append, and matches take the complete
higher representation. `True`, `1`, and `1.0` are distinct for this comparison.
`None` yields to containers in either order; explicit `:= None` forces it.
Quoted/computed keys never become names through merging.

A pipe has the lowest value-operator precedence and associates left to right.
Grouping matters: `a | (b | c)` need not mean `a | b | c`. Block and flow
operands may mix. Pipes require at least a ledger, even with literal operands;
a replacement annotation alone can remain a record. Holes retain their
existing reference/call grammar, without pipes.

`Tree.to_source()` preserves unfinished expressions, contribution order,
replacement intent, and meaningful grouping without resolving anything.
Save the text and parse it again to continue filling slots and composing.
Historical fill obligations that still need computed-key comparisons and
unattached slots remain save-time refusals; see the
[details](docs/DETAILS.md#save-now-finish-later).

## Element References

A hole names a value. `a.b` selects a **name key**; `a["b"]` can also select a quoted or computed key. Quoted keys never become names, even when their text looks like an identifier.

```yapyon
protocol: "messenger"
mind:
  endpoint: "https://api.server"
  dialects:
    messenger:
      api_uri: y"{endpoint}/v1"  # reaches its 'uncle' (mind.endpoint)
    icq:
      api_uri: y"{endpoint}/chat"
  chosen: y"{dialects[protocol].api_uri}"   # "https://api.server/v1"
```

| Spelling | Means |
|---|---|
| `{a.b}` | the key `b` — canonical for identifiers |
| `{a["b.c"]}` | a key a dot cannot reach |
| `{xs[0]}` | a list position; brackets only, since `0` is no identifier |
| `{d[p]}` | the key *stored in* `p`, resolved in the y-string's own scope |
| `{mm.k}` | every value filed under `k` in a multimap, in order, as a list |

`{a["bar"]}` where a dot would do is shiran — legal, but say `{a.bar}`.
Either quote mark works inside a hole, including the enclosing string's own:
`y"{a["b"]}"` and `y"{a['b']}"` are both valid. A hole is scanned before the
string's closing delimiter is sought, following modern Python's quote-reuse
rule.

## Relative References

`__ROOT__` names an absolute position; `__PARENT__` and `__KEY__` name
relative ones, so a block can refer to where it *is*:

```yapyon
store: "/cfg"
personas:
  kisama:
    id:     y"{__PARENT__.__KEY__}"              # -> "kisama"
    prompt: y"{__ROOT__.store}/{__PARENT__.__PARENT__.__KEY__}/{__PARENT__.__KEY__}.md"
```

The same text in every block, each resolving to its own name — without them a
block cannot be renamed or moved without editing its contents. `__PARENT__`
repeats (`{__PARENT__.__PARENT__.x}`) and leads a reference; `__KEY__` ends
one. Bare `{__KEY__}` is the *pair's own* key, which is rarely what you want.

## Serializers

A container cannot be spliced into text — there is no one text form and
picking one would be guessing. Naming the encoding is how it crosses:

```yapyon
store:
  model: "m1"
  host: "https://api.example.com/v1"
body: y"{store.__as_toml__()}"
```

```toml
model = "m1"
host = "https://api.example.com/v1"
```

`__as_json__()`, `__as_toml__()`, `__as_yaml__()`, and `__as_yapyon__()` are
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
and `"3"` survive as strings. `{cfg.__as_json__(lexemes=False)}` writes the
plain values alone.

`__as_yapyon__()` writes the block as a yapyon **record**, every value as
written: `3.10` still spelled `3.10`, multimaps and bytes as themselves. The
only thing any serializer refuses is a `yt`, which has no record form, and
`__as_toml__()` refuses what is not a table, since TOML has no top-level form
for anything else.

A serializer names the value it encodes, so it cannot name a *bare* anchor:
`{__PARENT__.__as_json__()}` would have to encode the string it is computing,
and is akan. Reach past the anchor — `{__ROOT__.blk.__as_json__()}` — which is
the shape you want anyway.

## Functions and contracts

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
Arguments may be named, as in Python — `{match_first(supported,
items=mind.dialects)}` — by the contract's parameter names.
Arguments are checked against the declared types before the call — deep,
and reported where the offending value is written — and a container
argument arrives as a read-only, ordered **borrow** of the document's node.
The result is checked against `returns` and becomes fresh data. Calls nest
and chain, and wait for their arguments like any hole, so two calls waiting
on each other are reported as the cycle they are. A function that raises is
akan naming it, never a traceback. The serializers are the format's
**built-in** functions, called the same way and declared by the spec itself.

## Resolving a reference from code

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

## Prefixes (Encodings)
Various binary representations are built into Yapyon to simplify data transfer.

### bytes (byte strings)

| Prefix | Meaning | Example | Notes |
|---|---|---|---|
| `b` | Standard bytes | b'Python-style' | Same as it ever was... |
| `b64` | RFC 4648 base64 | b64'base64//RFC4648=' | 4-symbol blocks (padded with '=') |
| `c32` | Crockford base32 | c32'AllYerCrockford-base 0' | Read c32'A11YERCR0CKF0RDBASE0' |
| `hex` | Hexadecimal | hex'badbeef' | Read hex'badbeef0' (0-padded, right) |
| `oct` | Octal | oct'10111052' | Read oct'10111052' (hex: 20 92 2A) |
| `dna` | DNA Seq. (base4) | dna'GATTACA' | Read dna'GATTACAT' (hex E0 98) (0-padded, right) |
| `bin` | Binary | bin'100' | Read bin'10000000' (hex 80) (0-padded, right) |

### int (integers)

| Prefix | Meaning | Example | Notes |
|---|---|---|---|
| None | Base 10 | 4 | Invented for counting on fingers |
| `0b` | Binary | 0b1000 | Read 0b00001000 (0-padded, left) |
| `0q` | Quaternary | 0q33 | Read 0q0033 (0-padded, left) |
| `0o` | Octal | 0o20 | Read 0o020 (0-padded, left) |
| `0x` | Hexadecimal | 0x17 | Read 0x17 (0-padded left; not shown) |
| `0z` | Crockford base32 | 0z1A | Read 0z01A (0-padded, left) |


### Variants: bytes / str

| Prefix | Meaning | Example | Pronunciation | Notes |
|---|---|---|---|---|
| `r` | Raw str  | r'chubby\bunny🐇' | are-string | Same as Python raw str |
| `rb` | Raw bytes | rb'Look\ma\no\escapes!' | reeb string | Same as Python raw bytes |
| `y` | yapyon str | y'Head like a {desc}' | why-string | str, spliced at parse |
| `yb` | yapyon bytes | yb'Head like a {desc}' | yeeb-string | bytes, spliced at parse (holes must be bytes or numbers) |
| `yt` | yapyon template string | yt'{part1}, {part2}' | yeet-string | Template, unjoined |
| `ry` | raw yapyon string | ry'{part1}\{part2}' | ree-string | str, backslash literal |

`f"..."`, `t"..."`, `u"..."` are errors with hints — their meaning depends on
an enclosing scope, and a data file has none.


