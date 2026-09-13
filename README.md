# yapyon (やぴょん)

> 「YAMLちゃうで。やぴょんやぴょん」
> *It's not YAML. It's yapyon.*

Python-style typed literals with YAML-like block structure. Quoted strings,
`True`/`False`/`None`, indentation blocks, `-` sequences, `+ ` multimaps,
`#` comments — and parse-time splicing that replaces YAML's anchors.

```yapyon
name: "api-gateway"
version: 3.10
port: 8080
debug: False

paths:
  root: "/srv/gateway"
  logs: y"{root}/logs"          # -> "/srv/gateway/logs"
  banner: y"{name} v{version}"  # -> "api-gateway v3.10"   (lexeme, not 3.1)

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

Pre-alpha, and `0.1.0a2` means it. Lexer, parser, resolver and loader are
done and tested — 318 tests, including a conformance suite that turns the
splice matrix and the Python divergence table into executable cases.

The normative specification is a working draft held by the author. It is
intended for publication, split into a grammar document and a broader spec;
until then this README summarises the format rather than defining it.

**Identifiers are UAX #31, and the guaranteed floor is Unicode 14.0.0** —
the tables Python 3.11 carries, 3.11 being the oldest version yapyon
supports. The spec asks every implementation to say where its tables come
from; yapyon inherits the host interpreter's, so a newer Python accepts
codepoints assigned after Unicode 14 that an older one rejects. Keys drawn
from Unicode 14 mean the same thing on every supported install.

```console
$ pip install --pre yapyon
```

```python
>>> import yapyon
>>> yapyon.loads('name: "gw"\nport: 8080\naddr: y"{name}:{port}"\n')
{'name': 'gw', 'port': 8080, 'addr': 'gw:8080'}
```

`loads` and `load` return plain Python. Eight of the ten types are builtins;
a `+ ` block comes back as an `OrderedMultimap`, and a `yt` literal as an
unfilled `Template`.

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

From a checkout, the stages will also dump what they see:

```console
$ pip install -e ".[dev]" && pytest -q
$ python -m yapyon.lexer examples/gateway.ypy    # token dump
$ python -m yapyon.parser examples/gateway.ypy   # AST dump
```

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

## Prefixes

| Spelling | Name | Spoken | Result |
|---|---|---|---|
| `b`, `b64` | bytes literals | — | bytes |
| `r`, `rb` | raw | — | str, bytes |
| `y` | yapyon string | y-string | str, spliced at parse |
| `yb` | yapyon byte string | yeeb-string | bytes, spliced at parse |
| `yt` | yapyon template string | yeet-string | Template, deferred |
| `ry` | raw yapyon string | ree-string | str, backslash literal |

`f"..."`, `t"..."`, `u"..."` are errors with hints — their meaning depends on
an enclosing scope, and a data file has none.

## Diagnostics

`shiran:` (warning) → `akan:` (error) → `yakamashiwa:` (internal bug).
Verbose success prints `ええやん`.
