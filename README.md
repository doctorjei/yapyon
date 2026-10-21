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
  scalar: ['bool', 'int', 'float', 'str (always quoted!}', 'None']
  containers: ['list', 'dict', 'multimap', 'bytes', 'template strings']
encodings:
  + bytes: b'Python-style' # Same as it ever was...
  + bytes: dna'GATTACA'    # Base-4... and more!
  + ints:  4               # Decimal
  + int32: 0z1A            # Crockford base32
```

**The pitch:** the same bytes with the same inputs yield the same the same data, to every parser, on every machine, always. There's no implicit typing: `no` is not `False`, and strings are always quoted; there are no anchors or tags, one null spelling, and one document per file. A repeated key in a map is an error, never an uncaught typo silently overwriting data.

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

The `loads` and `load` functions return plain Python. Types include builtin Python types as well as OrderedMultiMap ('+'-syntax) and `Template` ('y-string').

Some other quick commands:
```
$ python -m yapyon record examples/registry.yap  # A Yapon record
$ python -m yapyon lexer  examples/gateway.yap   # token dump
$ python -m yapyon parser examples/gateway.yap   # AST dump
$ python -m yapyon tier   examples/gateway.yap   # tier 3 — it carries a yt
$ python -m yapyon expand examples/bridge.yap    # a ledger in, a record out
```

## Document Variants

A document is one of four kinds (discoverable via `yapyon.tier_of()`:
- **record**: literals only (no resolver / resolution process)
- **ledger**: splices & calls built-ins; resolves internally
- **template**: incorporates external data (e.g., environment variables)
- **assembly**: calls functions that a **contract** declares; can be assembly from multiple files

Yapyon has no ambient scope nor includes and is built to be completely auditable / verifiable.

**template** (3) is finished by something outside it — the environment it
reads with `{$HOME}` or `__ENV__`, or the consumer joining a `yt`; an
**assembly** (4) calls functions that a **contract** declares, which the
program loading it supplies. There is no ambient scope and no includes: a
document reaches outside itself only through variables it names, which the
loader exposes (the standard ones by default, never secrets unless asked),
and through a contract its loader was handed — so its reach is something you
can *prove* rather than audit.

## Element References

A hole names a value. The shortcut style `a.b` is syntactic sugar for`(equivalent to) a["b"]`.

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
