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

Pre-alpha. Lexer and parser done and tested; resolver next. See `SPEC.md` for
the normative draft and `CLAUDE.md` for design rationale and roadmap.

```console
$ pip install -e ".[dev]"
$ pytest -q
$ python -m yapyon.lexer examples/gateway.ypy    # token dump
$ python -m yapyon.parser examples/gateway.ypy   # AST dump
```

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
