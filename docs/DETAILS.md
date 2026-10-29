# yapyon (やぴょん)

## Status

**Version `0.6.0`**, implementing specification and grammar **v0.6** for
merge/source composition and unfinished persistence, with host-value record
export. The lexer, parser, resolver, loader, emitter, four serializers,
contracts, and trees with slots share the format's merge rules; the suite and
**121 portable corpus cases** exercise those contracts. The validated source
suite executes **3540 tests**, with zero skips on Python 3.11, 3.13, and 3.14
using the supported POSIX test filesystem. Unsupported-ACL refusal and recovery
are tested separately as well. Python 3.11 is the minimum supported version.
Core runtime dependencies are the standard library.

**The normative specification is published, in two documents under
[`docs/`](./):**

| | |
|---|---|
| [`docs/GRAMMAR.md`](GRAMMAR.md) | *are these bytes well-formed yapyon?* — self-contained, normative for syntax |
| [`docs/SPEC.md`](SPEC.md) | *what do well-formed bytes mean?* — normative for meaning |
| [`docs/conformance/`](conformance/) | *does an implementation agree?* — portable cases; the directory's own README is the protocol |

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

## Collection comprehensions

*Added in 0.5.3; SPEC §16 and GRAMMAR §G9.* Construct lists, dictionaries, and
multimaps directly in the document. Every comprehension has one `for` and
at most one `if`. A list source binds one item; a dictionary or multimap source
binds key and value. Multimap input visits every entry, including repeats.

```python
>>> import yapyon
>>> d = yapyon.loads('persona: {name: "example", models: ["m1", "M/2"]}\nrows: {target: {provider: (persona.name), remote: (target)} for target in persona.models}\n')
>>> d["rows"]
{'m1': {'provider': 'example', 'remote': 'm1'}, 'M/2': {'provider': 'example', 'remote': 'M/2'}}
```

The outer `target` is a computed key; the inner `provider` and `remote` are
ordinary name keys. Keys retain exact string text and are not promoted to
names. Dictionary duplicates are akan; use a multimap to retain them. Ordinary
nonempty inline multimaps are `{+ key: value, key: value}`.

```python
>>> d = yapyon.loads('models: ["m1", "m2"]\nby_provider: {+ "example": model for model in models}\n')
>>> [(entry.key, entry.value) for entry in d["by_provider"]]
[('example', 'm1'), ('example', 'm2')]
```

Filters accept **True**, **False**, or **None** only; None counts as false.
Numbers, strings, and containers are not implicitly converted. Test availability
explicitly when empty-but-present values must count:

```python
>>> d = yapyon.loads('supported: ["responses", "chat"]\npersona: {dialects: {responses: None, chat: {}}}\nprotocol: [dialect for dialect in supported if persona.dialects.__get__(dialect) is not None][0]\n')
>>> d["protocol"]
'chat'
>>> yapyon.loads('choices: []\nprotocol: [x for x in choices].__get__(0)\n')["protocol"] is None
True
```

`[0]` requires a match and is akan on an empty result. `.__get__(0)` returns
None instead. Both evaluate the whole comprehension; neither hides errors in
later iterations. Comparisons, membership, None tests, and short-circuit
boolean operators are shared expression facilities, not special matching
functions. `and`/`or`/`not` return booleans, not selected arbitrary operands.

The equivalent block dictionary form is shown in the complete
[`comprehension example`](../examples/comprehensions.yap). A block list head
starts with `-`, and a block multimap head with `+`; the trailing `for` and
optional `if` align with that marker. Iteration bindings do not leak or become
mapping entries; ordinary nested mapping keys/explicit copies stay unchanged.

`Tree.to_source()` preserves unfinished comprehensions without evaluation,
including compositions with other nonempty dictionary layers. It writes explicit
pipes instead of flattening contributions or iterating a comprehension to save
it. Dictionary comprehensions merge by key across layers before retained value
bodies resolve, keeping each operand's lexical bindings separate. List and
multimap results use the same typed collection rules as literal values below.

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

## String keys

A bare key is a name. A plain quoted key is literal data, and `y`/`ry`
computes its text using the ordinary string rules. Quoted and computed keys
are **not names**, even when their text is an identifier: use a subscript
through a named parent to reach them, not a dotted step or scope search.

```python
>>> d = yapyon.loads('provider: "moonshot-ai"\nproviders: {y"{provider}": {port: 443}}\nselected: (providers[provider])\n')
>>> d["providers"]
{'moonshot-ai': {'port': 443}}
>>> d["selected"]
{'port': 443}
>>> yapyon.loads_record('"model-name": "small"\n')
{'model-name': 'small'}
```

Key equality is the resulting string: different expressions can yield the
same key. Repetition in one mapping is akan; matching keys across explicitly
merged layers follow the ordinary merge rule. Merging never resolves an
input early. Pending contributions keep their precedence until the keys are
known. Empty keys, dunders, and keys beginning with `@` are refused.

Loaded mappings are **dict subclasses** retaining which keys were names, so
`yapyon.lookup` agrees with document holes. Normal indexing and equality are
dict's; replacing a value preserves its key's kind. New Python-added keys
and ordinary dicts use writable identifiers as names and other legal strings
as non-name keys. `copy`, deepcopy, pickle, and unions preserve provenance;
explicitly converting to `dict` discards it.

## Merging values

*The `0.6.0.dev0` development line; SPEC §15.2 and §16.5.* `|` composes
complete values, and the same rules govern `Tree`/`Handle` merging and fills.
A later contribution is higher precedence. A pair's ordinary `:` combines
values; `:=` replaces the field with its **complete** incoming value:

```python
>>> doc = 'settings:\n  paths: ["base", "shared"]\n  reset: ["old"]\n  |\n  paths: ["shared", "new", "shared"]\n  reset:= []\n'
>>> yapyon.loads(doc)
{'settings': {'paths': ['base', 'shared', 'new', 'shared'], 'reset': []}}
```

- **Dictionaries** match resulting string keys recursively. Earlier keys keep
  their position, spelling, and name/non-name kind; new incoming keys append
  in incoming order. Separate layers may match, but duplicates within one
  contribution are still akan. A quoted/computed key is never promoted to a name.
- **Lists** combine whole typed elements; **multimaps** combine complete key/value
  pairs, not values guessed to match by repeated key or position. Equal items
  retain the **greater occurrence count in either input**, not the sum or
  necessarily one. Standalone and explicitly replaced collections keep repeats.
- **Occurrence order and spelling:** visit incoming items in order, matching each
  to the first equal unmatched item from the original earlier input. A match
  keeps that earlier position and takes the **whole incoming representation**,
  including lexemes and a dictionary item's key order/kind. Unmatched incoming
  occurrences append; appended items are not new match targets in that merge.
  Unmatched earlier occurrences keep their own representation.
- **Typed duplicate equality** distinguishes `True`, `1`, and `1.0`. Same-kind
  numbers ignore spelling; text/bytes compare decoded contents. Lists and
  multimaps compare in order; dictionary associations ignore entry order and
  key spelling/kind. Templates compare delivered parts and hole metadata without
  rendering. Ordinary expression `==` keeps its existing numeric behavior.
- **None** yields to a dictionary, list, or multimap in either order, including
  empty containers. Otherwise noncombining kinds take the higher whole value.
  Compatible empty collections do not clear data. Zero, False, and empty text
  are values, not absence. `field:= None` or `field:= []` explicitly replaces
  instead of combining; neither deletes the field or blocks later overrides.

```python
>>> yapyon.loads('[0x1, True] | [1.0, 1]')
[1, True, 1.0]
>>> entries = yapyon.loads('{+ a: 1, a: 2} | {+ a: 1, a: 1, a: 3}')
>>> [(entry.key, entry.value) for entry in entries]
[('a', 1), ('a', 2), ('a', 1), ('a', 3)]
```

`:` and `=` are separate tokens: `field:= value` and `field : = value`
are equivalent. Within flow delimiters, newlines may separate them too;
ordinary indentation still matters outside those delimiters. Replacement
annotates the field, not the enclosing dictionary or collection, and a pipe
on its right belongs to the complete incoming value.

**Grouping is meaningful.** A pipe has the lowest value-operator precedence,
below `or`, and unparenthesized chains associate left to right. Block and flow
operands can mix without changing that order. Compare these complete documents:

```python
>>> yapyon.loads('{config: {old: 1}} | {config: "reset"} | {config: {new: 2}}')
{'config': {'new': 2}}
>>> yapyon.loads('{config: {old: 1}} | ({config: "reset"} | {config: {new: 2}})')
{'config': {'old': 1, 'new': 2}}
```

Parentheses keep the right-hand program as one operand; merging is not generally
associative. `(True or False) | False` is the grouping of
`True or False | False`. For traversal of a merge result, group the whole result
before its postfix. Pipes are value expressions, not additions to hole/call
argument syntax.

**Compatibility:** copies and calls combine according to their eventual value
kind, just like literal containers. Previously a deferred copy/call could replace
an earlier mapping wholesale because its parser node was not a mapping. Now a
returned dictionary merges by key, and returned lists/multimaps use the typed
collection rules. Use explicit field replacement when whole replacement is meant:

```python
>>> lower = yapyon.parse('settings: {host: "local", port: 80}\n')
>>> higher = yapyon.parse('choices: {active: {port: 443}}\nsettings: choices.__get__("active")\n')
>>> yapyon.merge(lower, higher).resolve()["settings"]
{'host': 'local', 'port': 443}
```

Unknown results stay deferred; constructing a merge or saving it never runs a
call to discover its kind. A pipe makes a document at least a ledger even with
literal operands. A replacement separator alone does not: otherwise literal
annotated data remains a record.

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

A merge uses the value-kind rules above: dictionary unique keys recurse,
lists/multimaps combine whole items, and `None` yields to containers. Holes
resolve where their values end up, so a layer can refer to keys another layer
brings. Neither merging nor source saving resolves an input early.

Before resolution, `keys()`/`items()` return a `yapyon.Key` location token
for each computed key. Pass that token back to the same mapping to walk or
edit its value; `.lexeme` shows the key expression without evaluating it.
These tokens are locations, not expressions compared for data-key equality.
An unresolved collection has no guessed final indices or length; effective-index
operations need a structurally known view. Retained slots remain discoverable
through `slots()` and fillable even when those final positions are unknown.

```python
>>> pending = yapyon.parse('name: "x"\ny"{name}": 42\n')
>>> key = pending.keys()[1]
>>> key.lexeme, pending[key].value
('y"{name}"', 42)
>>> pending.resolve()
{'name': 'x', 'x': 42}
```

A **slot** marks a place the consumer fills. `persona<llamacpp>:` makes
`persona`'s value a slot labeled `llamacpp`; the dictionary under it holds
**overrides** applied over whatever fills it (`{}` for none):

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
give `harness` a value. A retained slot still unfilled when the tree resolves
is akan. A later dominating value or explicit replacement can discard a slot;
`None`, a list, or a multimap may instead need to wait for the filler's kind.
Literal empty overrides mean no operation even on a non-dictionary filler.
`part<new>:= {}` replaces the inherited field with a fresh slot, not an empty
dictionary that ignores its new filler. SPEC §15 has the rules.

A labeled field's **complete RHS is one dictionary override contribution**.
Several sequential additions to an unfilled slot are not interchangeable with
one premerged RHS. For example, applying `config: "reset"` and then
`config: {new: 2}` discards a filler's old `config` keys. Premerging those two
dictionaries first gives just one dictionary override, which can retain the
filler's old keys. `to_source()` preserves the distinction with surrounding
dictionary layers where needed. A copied `overrides` view is inspection, not
a replay of every sequential operation. Equivalent fills of the same retained
assembly and fixed slot selections give the same result; merging independently
prefilled inputs is not the same operation as selecting between unfilled slots.

### Save now, finish later

`Tree.to_source()` writes the current unfinished tree as yapyon text. Fill
only the slots you choose, save the text using ordinary file I/O, and parse
it again to continue. No expression is evaluated while saving: environment
variables, contract calls, copies, serializers, and computed keys stay as
written. The original tree is unchanged.

```python
>>> draft = yapyon.parse('agent<base.agent>: {name: "local"}\n')
>>> definition = yapyon.parse('agent:\n  name: "base"\n  desc: y"{name}"\n  harness<chosen>: {}\n')
>>> draft["agent"].fill(definition)
>>> saved = draft.to_source()
>>> print(saved, end="")
agent:
  name: "base"
  desc: y"{name}"
  harness<chosen>: {}
  |
  name: "local"
>>> resumed = yapyon.parse(saved, source="saved-agent.yap")
>>> resumed["agent"]["harness"].fill(yapyon.parse('mode: "cli"'))
>>> resumed.resolve()
{'agent': {'name': 'local', 'desc': 'local', 'harness': {'mode': 'cli'}}}
```

The pipe in the saved text retains the definition and override as distinct
contributions. Saving likewise retains computed-key collisions across layers,
comprehensions combined with other nonempty dictionaries, collection programs,
and sequential slot operations. It preserves replacement intent and meaningful
right grouping rather than collapsing them to a value that happens to work for
one current filler. No lookup, environment access, function/cast/serializer,
comprehension iteration, template rendering, or runtime duplicate comparison
runs to produce source.

Two states still have no faithful source spelling (SPEC §15.8):

- **A completed fill's undecided historical abstract-slot obligation.** If it
  still needs a computed-key comparison about that fill's own overrides,
  saving is akan at the fill. An ordinary new abstract slot cannot encode
  that historical requirement, and a later convenient edit is not retroactive
  fulfillment. Keep composing in memory or provide explicit overrides before
  making the responsible fill; saving never evaluates a key to settle it.
- **An unattached slot.** A slot must be attached to a dictionary key and label;
  a slot extracted as a standalone root value has no source form.

Remaining attached named and abstract slots can otherwise be saved and filled
later. These refusals do not change in-memory merging or resolution.
`resolve()` requires every still-needed slot to be filled; slots discarded by
later replacement no longer need fillers. `emit()` and the `record` command
remain record-only and never evaluate authored pipes to make them records.
Data expansion/serializers consume composition into finished data instead;
source writing preserves the unfinished program.

Generated source uses two-space indentation, `key: value`, `key:= value`,
and standalone pipes aligned with their contribution heads. It normalizes
layout and loses comments. Reloaded diagnostics use the saved file's positions,
not the original template files', and handles/key-location tokens belong to
their original tree, not to its reloaded copy.

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
lexing, without loading. A replacement annotation is field intent, not
computation; an explicit pipe is computation even with literal operands:

```python
>>> yapyon.is_record('items:= []\n')
True
>>> yapyon.is_record('[] | []\n')
False
```

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
An authored replacement annotation on direct record source also survives
normalization. **Comments do not survive**, so this is a normalizer rather
than a round-tripper. `yapyon.emit` is the same thing as a function. A
non-record is refused at the offending computation, with the record rule
as the reason; authored pipes are not silently evaluated.

## Exporting Python values

Use `dumps` for text, conventional `dump` for an already-open text stream, and
`dump_safe` for checked file replacement:

```python
>>> value = {"name": "gw", "ports": [8080, 8443], "enabled": True}
>>> text = yapyon.dumps(value)
>>> print(text, end="")
name: "gw"
ports: [8080, 8443]
enabled: True
>>> yapyon.loads_record(text) == value
True
>>> import io
>>> fp = io.StringIO()
>>> yapyon.dump(value, fp)
>>> fp.getvalue() == text
True
>>> fp.closed
False
```

All three functions share the same adaptation and canonical emitter. They write
records without environment access, function calls, merging, or expression
resolution. `Tree.to_source()` saves unfinished source; `emit()` normalizes a
record tree and preserves its authored lexemes; host export has no authored
literal spellings to preserve.

### Data and keys

Accepted recursively: `str`, `int`, finite `float`, `bool`, `None`, `bytes`,
`list`, `dict`, and `OrderedMultimap`. Any supported value may be the root.
Order, repetitions, empty containers, `None`, zero, and `False` survive. There
is no pruning, sorting, implicit string conversion, or custom-adapter protocol.
`Template`, unresolved `Tree`, tuples, sets, bytearrays, memoryviews, and arbitrary
objects are not implicitly converted. Explicitly adapt other host objects first.

Keys remain exact strings. A plain Python dictionary uses a bare name only
when that spelling preserves the exact key; otherwise it quotes the key.
Known loaded name/non-name provenance survives. Quoted keys do not become names,
and invalid or inconsistent provenance is refused rather than silently folded.
Non-string, empty, dunder, and `@`-prefixed keys remain invalid.

Shared acyclic Python containers are accepted as independently serialized
occurrences. Reloading does not preserve their mutable identity. Actual container
cycles raise `AkanError` with the current and ancestor data paths, without
invented source coordinates. Unsupported kinds/non-string keys/options are
`TypeError`; invalid text, nonfinite numbers, invalid provenance, and exceeded
export limits are `ValueError`. Text cannot contain lone surrogates.

### Export limits and input consistency

Each function accepts the same keyword options:

| Option | Default | Meaning |
|---|---|---|
| `max_digits` | 17,200 | Maximum decimal integer digits; at least 4,300 |
| `max_depth` | 128 | Nested container levels; root container is 1, scalar root is 0 |
| `max_size` | 4 MiB | Actual serialized UTF-8 bytes, including layout, escapes, and final newline |
| `warn` | `None` | Optional warning callback; integers above 4,300 decimal digits warn |

Limits require integers, not booleans; depth and size must be positive. `warn`
is `None` or callable. These are export-specific metrics, not resolver dependency
or expansion metrics. They are independent of CPython's decimal conversion setting
and of an eventual stream's encoding. Adaptation and shared emission are bounded
before unbounded graph expansion or output allocation. Callback failures propagate.

**The exporter does not mutate or lock its input.** Keep the entire input stable
until serialization completes. If another thread can mutate it and you need a
consistent view, use your own shared lock around saving and every mutation.
Copying data during an unsynchronized traversal is not an atomic snapshot.
Safe file replacement does not synchronize the Python input.

### Streams and safe files

`dump(value, fp, ...)` validates/prepares complete text before one `fp.write`.
It does not close, flush, or retry the caller's stream. A reported integer short
or inconsistent count is `OSError`; a writer returning `None` follows that
protocol. Native write/encoding failures propagate. Opening a file with `"w"`
may already truncate it before `dump` runs; conventional stream output is not
atomic file replacement.

`dump_safe(value, path, ...)` accepts a string or `os.PathLike` returning a string
and writes UTF-8. Its verified protection implementation is currently **Linux-only**;
other platforms raise `OSError` with `ENOTSUP` before changing the destination.
Unrecognized filesystem access metadata, including NFSv4 ACLs, also causes a
safe refusal; verified support covers ordinary Linux mode bits and POSIX ACLs,
not every filesystem mounted on Linux. The following complete example runs
where those protections are supported:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import yapyon

value = {"port": 8080}
with TemporaryDirectory() as directory:
    path = Path(directory) / "settings.yap"
    yapyon.dump_safe(value, path)
    with path.open(encoding="utf-8") as fp:
        restored = yapyon.load_record(fp)
    print(restored)
```

Output:

```text
{'port': 8080}
```

The destination is not truncated while output is prepared. A complete candidate
is written and closed inside a private `0700` staging directory; replacement
publishes it only afterward. New destinations are owner-only (`0600`). Existing
Linux ownership, permission bits, POSIX access ACLs, and security labels must be
preserved or verified equal; unsupported protections and special-mode targets
are refused rather than silently weakened. The directory keeps the candidate
private even while its final access permissions are being prepared.

Existing destination symlinks are followed and left intact; replacement affects
the selected target. Other hard links to an old inode continue naming that old
file. Detected destination/path changes cause failure rather than a blind
replacement, but these checks are not a filesystem lock or protection against
hostile last-instant pathname races. No sudden-power-loss durability is promised.

On filesystem failure the native exception is preserved and gains `recovery_path`
(a retained file path, or `None`) and explanatory exception notes. Notes identify
the actual target, failed operation, retained data, completeness, and observed or
uncertain replacement outcome. Recoverable files remain private; if local staging
fails or is incomplete, a complete private fallback is attempted when possible.
An interruption closes owned descriptors without heavy fallback retries. A rename
error is not falsely described as proof that no replacement occurred, and cleanup
errors after publication explicitly report that replacement completed. The library
does not print errors; callers decide how to show or handle them.

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

Both tiers are about cost alone. A **cycle or a missing target is always
akan** at any depth, because it can never resolve. Composition also charges
materialization and duplicate-comparison work before unbounded allocation;
a small deduplicated result does not make arbitrarily large inputs free.
`max_size` also bounds merge work units: visits to projection/key-readiness
steps, dictionary field contributions, and recursively compared values. The
default is 4,194,304 work units, independent of the rendered-size counter;
fixpoint retries count too. `max_depth` additionally guards retained composition
nesting before projecting it. A refusal names the work or depth ceiling rather
than relying on a host allocation or recursion failure.

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

