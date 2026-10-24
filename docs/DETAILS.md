# yapyon (やぴょん)

## Status

**`0.5.1`**, built to specification **v0.5**. Lexer, parser, resolver,
loader, emitter, the four serializers, contracts, and trees with slots are
done and tested,
including a conformance suite that turns the splice matrix and the Python
divergence table into executable cases, and a portable corpus in
`docs/conformance/` that another implementation can run against itself. The
suite is **2016 tests** on the current tree; the number here tracks the tree,
not a release.

**The normative specification is published, in two documents under
[`docs/`](./):**

| | |
|---|---|
| [`docs/GRAMMAR.md`](GRAMMAR.md) | *are these bytes well-formed yapyon?* — self-contained, normative for syntax |
| [`docs/SPEC.md`](SPEC.md) | *what do well-formed bytes mean?* — normative for meaning |
| [`docs/conformance/`](conformance/) | *does an implementation agree?* — 95 portable cases; the directory's own README is the protocol |

The corpus is not a third normative document: it is **derived from** the
other two, and where they disagree the spec wins and the case is wrong. What
it adds is a check rather than a definition — every case is data, not code
in a language, so a second implementation runs the same files against its
own loader and gets a yes or no.

New to the format? [`docs/TUTORIAL.md`](TUTORIAL.md) walks through it
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

## Copies

A reference in parentheses is a **copy** of the value it names, kept as what
it is — where a y-string can only take text. *(New in `0.4.1`.)*

```python
>>> d = yapyon.loads('wanted: ["responses", "chat"]\nsupported: (wanted)\n')
>>> d["supported"]
['responses', 'chat']
>>> d["supported"] is d["wanted"]
False
```

The lookup is a hole's, the value is resolved where it is written and then
copied, and the copy is a separate object. Parentheses around a literal only
group it, as in Python. SPEC §5.6 has the rules.

## Casts and the getter

Four built-ins convert one value to another type, with Python's names and
yapyon's own rules for what they accept — so a cast means the same in every
implementation. A value ending in a call may stand bare, without the
parentheses a copy needs. *(New in `0.5.1`.)*

```python
>>> yapyon.loads('port_text: "0080"\nport: port_text.__int__()\nflag: __bool__("Yes")\n')
{'port_text': '0080', 'port': 80, 'flag': True}
```

Text must be the whole value: `"3.0"`, `"42abc"`, and `" 42"` are akan as
ints, and nothing is quietly dropped. A float truncates to an int, bools are
1 and 0, and `__str__` writes a number as splicing does. `None` is akan
too — unless the call follows `?.`, which skips the rest of the chain:

```python
>>> yapyon.loads('models: []\nmind: {a: 1}\nfable: models.__get__(0)?.__str__()\nctx: mind.__get__("b", 8)\n')
{'models': [], 'mind': {'a': 1}, 'fable': None, 'ctx': 8}
```

`__get__(key, default=None)` is `dict.get`, for lists too, and gives a
multimap's list view of the key. SPEC §5.1.5 has every rule.

## Trees and slots

`yapyon.parse` reads a document **without resolving it** and returns a
`Tree`: holes still unresolved, every value keeping its spelling and its
place. A consumer walks it, combines trees with `merge`, and resolves once.
*(New in `0.5.0`; `parse` returned the parser's nodes before.)*

```python
>>> base = yapyon.parse('mind:\n  model: "m1"\n  endpoint: "e"\nv: 3.10\n')
>>> base["v"].value, base["v"].lexeme
(3.1, '3.10')
>>> user = yapyon.parse('mind:\n  model: "m2"\nsay: y"{mind.model} at {mind.endpoint}"\n')
>>> yapyon.merge(base, user).resolve()
{'mind': {'model': 'm2', 'endpoint': 'e'}, 'v': 3.1, 'say': 'm2 at e'}
```

A merge recurses only where both sides are mappings; anywhere else the later
value wins whole, and `None` is a value like any other. Holes resolve where
their values end up, so a layer can refer to keys another layer brings.

A **slot** marks a place the consumer fills. `persona<llamacpp>:` makes
`persona`'s value a slot labeled `llamacpp`; the mapping under it holds
**overrides** that win over whatever fills it (`{}` for none):

```python
>>> agent = yapyon.parse('name: "local"\npersona<llamacpp>:\n  mind:\n    endpoint: "http://localhost:9931"\n')
>>> [(slot.key, slot.label) for slot in agent.slots()]
[('persona', ('llamacpp',))]
>>> agent["persona"].fill(yapyon.parse('mind:\n  endpoint: "remote"\n  model: "q4"\ndesc: y"{name}"\n'))
>>> agent.resolve()
{'name': 'local', 'persona': {'mind': {'endpoint': 'http://localhost:9931', 'model': 'q4'}, 'desc': 'local'}}
```

The label says *what* fills the slot; finding it is the consumer's job, so
yapyon never reads a file on a slot's behalf. A label may reach into its
filler — `agent<base.agent>` fills with `base`'s `agent` branch — and an
empty label, `harness<>`, is abstract: whoever fills from that document must
give `harness` a value. A slot still unfilled when the tree resolves is akan.
SPEC §15 has the rules.

## Records

A **yapyon record** is the restricted form in which *every leaf element has a
literal value* — no splicing, no copies, no templates, nothing deferred. It is a strict
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
why the spec asks every implementation to say which tier it provides.
**yapyon implements every tier**, and so also loads records.
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
$ python -m yapyon tier   examples/gateway.yap   # 3 — it carries a yt
$ python -m yapyon expand examples/bridge.yap    # a ledger in, a record out
```

Every stage writes its output to stdout and its diagnostics to stderr, and
**shows shirans by default** — the library hides them behind `warn=`, but a
person at a terminal asked. A shiran does not change the exit status; an akan
exits 1.

