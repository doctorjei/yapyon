# yapyon (やぴょん)

## Status

**Version `0.6.6`** implements specification and grammar **v0.6**, including
merge/source composition, unfinished persistence, host-value record export,
compact yapyon list layout, and conditional values. This version adds the reviewed
YamlPlus format/diagnostics and full-validity record predicate, resolved-AST
profile output, and reference-only `!` cancellation. A separate standalone binding uses
native safe PyYAML I/O and independent validation; it is not a core runtime
dependency. The lexer, parser, resolver, loader, emitter, five serializers,
contracts, and trees with slots share the format's merge rules. The current suite contains
**5209 tests**, including **141 corpus cases**, with migrated profile oracles
for values, diagnostics, and comment-preserving formatting. Release validation
checks source and extracted-sdist
suites on Python 3.11, 3.13, and 3.14, plus isolated wheel workflows. Safe-file
checks use the supported POSIX test filesystem and separately exercise
unsupported-ACL refusal/recovery. Python 3.11 remains the minimum supported
version. Core runtime dependencies are the standard library.

**The core language specification is published in two documents under
[`docs/`](./); the opt-in yamlplus profile has its own normative definition:**

| | |
|---|---|
| [`docs/GRAMMAR.md`](GRAMMAR.md) | *are these bytes well-formed yapyon?* — self-contained, normative for syntax |
| [`docs/SPEC.md`](SPEC.md) | *what do well-formed bytes mean?* — normative for meaning |
| [`docs/YAMLPLUS.md`](YAMLPLUS.md) | *which records are YAML-readable, and how are they read and written?* — normative for the optional profile |
| [`docs/conformance/`](conformance/) | *does an implementation agree?* — portable cases; the directory's own README is the protocol |

The corpus is not another normative document: it is **derived from** the
language specification and optional profile, and where they disagree the
normative text wins and the case is wrong. What
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

## Conditional values

`x if y else z` selects a typed value. It evaluates the condition first and only
the selected branch; an unused branch does not perform calls or lookups.

```python
>>> d = yapyon.loads('enabled: True\nprimary: {port: 443}\nfallback: {port: 80}\nchosen: primary if enabled else fallback\n')
>>> d["chosen"]
{'port': 443}
>>> d["chosen"] is d["primary"]
False
>>> yapyon.loads('out: 1 if True else missing\n')["out"]
1
```

Conditions use yapyon's existing rule: `True`, `False`, or `None` only, with None
counting as false. Numbers, strings, and containers do not gain implicit truthiness.
The branches may return different types; False, zero, None, and empty values stay
as themselves. A named branch is copied rather than aliased.

Chained conditionals associate to the right. Logical operators bind more tightly;
yapyon's merge pipe remains the lowest-precedence operator. Use `(a | b) if flag
else c` when the merged value belongs inside the selected branch. Comprehension
heads may use conditionals directly; parenthesize them in an iterable or filter.
Holes and reference-call arguments retain their existing grammar. This requires
at least a ledger, and `Tree.to_source()` preserves both branches unevaluated.
SPEC §16.3 has the rules.

## Optional contributions with `!`

Postfix `!` explicitly guards a reference. A missing reference cancels the
receiving field or collection item; it does not supply None or delete a lower
merge contribution. A present None, False, zero, or empty value stays data.

```python
>>> yapyon.loads('foo: {}\nitems: [1, (foo.missing!), 3]\n')
{'foo': {}, 'items': [1, 3]}
>>> yapyon.loads('foo: {}\nx: "alpha"\n|\nx:= (foo.missing!)\n')
{'foo': {}, 'x': 'alpha'}
>>> yapyon.loads('foo: {value: None}\nx: (foo.value!)\n')
{'foo': {'value': None}, 'x': None}
```

A canceled field inside a mapping list item removes only that field. Empty
containers are not pruned. In an expression or nested call, cancellation skips
that value's remaining computation and propagates to its receiving field/item;
it neither supplies a boolean nor silently removes a required argument.

`foo[selector]!` guards the selected entry, not evaluation of `selector`.
Use `foo[selector!]!` to guard both. Pending dependencies wait, and cycles,
wrong container/index types, failed functions, and disabled environment access
remain errors. None returned by `__get__` is still a present value, not absence.
Unlike `?.`, cancellation never passes None into an outer call.

Use `(reference!)` for a guarded copy; `(reference)!` is not a reference operand.
A canceled whole document is akan because an empty document is not accepted.
Source saving preserves the guards and necessary fallback layers without
resolution. This is full Yapyon, not a record or YamlPlus feature.

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

## Removing None values before serialization

`foo.__not_none__()` returns a recursive copy with None-valued dictionary keys,
multimap entries, and list elements removed. It is a data transformation, not a
serializer: chain it into the output format you want.

```python
>>> doc = 'foo: {name: "gw", token: None, options: [None, {limit: None, enabled: False}]}\nbody: foo.__not_none__().__as_json__()\n'
>>> d = yapyon.loads(doc)
>>> d["body"]
'{"name": "gw", "options": [{"enabled": false}]}'
>>> d["foo"]["token"] is None
True
>>> d["foo"]["options"]
[None, {'limit': None, 'enabled': False}]
```

The original stays unchanged. Only actual `None` values are removed: `False`,
`0`, `""`, the string `"None"`, and empty containers stay. Remaining list elements
keep their order, with their indices shifted. Values resolve before removal,
so computed None values are removed too. `__not_none__(foo)` is the equivalent
function spelling; it takes no keywords. SPEC §5.1.6 has the rules.

Use `foo.__not_none__().__as_toml__()`, `.__as_yaml__()`, or `.__as_yapyon__()`
for other formats. Without an explicit transformation, serializers keep their
usual behavior; host-value `dump`/`dumps`/`dump_safe` are unchanged.

## Compact list output

Yapyon output keeps a short list on one line when the entire line fits within
100 display columns. A longer eligible list can use a modified short form:

```python
>>> print(yapyon.dumps({"numbers": list(range(1, 31))}), end="")
numbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25,
          26, 27, 28, 29, 30]
```

Elements pack greedily, with continuation lines aligned beneath the first
element. Every complete line fits 100 columns, including indentation, keys,
brackets, and commas. Mappings or multimaps anywhere inside a list disqualify
it; each nested list must fit on one line as an indivisible element. A scalar
with a multi-line spelling stays in block layout rather than being respelled.

At least 75% of the counted lines must hold two or more top-level elements.
Bracket-only lines are ignored, and the final remainder line is exempt so a
single leftover element does not force block layout. Nested lists count as
one element each. If the requirements fail, normal block layout is used.

This is the shared yapyon policy for `emit`, `Tree.to_source`, `expand_record`,
`__as_yapyon__`, and `dump`/`dumps`/`dump_safe`. JSON, YAML, and TOML writer
layouts are unchanged. SPEC §14.1 defines the exact rules.

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
- **None** follows ordinary scalar precedence: higher wins, even against a
  dictionary, list, or multimap. Noncombining kinds take the higher whole value.
  Compatible empty collections do not clear data. None, zero, False, and empty
  text are values, not absence. `field:= None` or `field:= []` explicitly replaces
  instead of combining; neither deletes the field or blocks later overrides.

**Changed in 0.6.2:** a higher `None` no longer yields to an earlier container.
It also discards an earlier pending computation or unfilled slot without
executing or filling it. A later contribution can change the value again.

```python
>>> yapyon.loads('{old: 1} | None') is None
True
>>> yapyon.loads('None | {new: 2}')
{'new': 2}
>>> yapyon.loads('{part<base>: {bad: (missing)}} | {part: None}')
{'part': None}
```

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
lists/multimaps combine whole items, and `None` follows scalar precedence. Holes
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
>>> for slot in agent.slots("llamacpp"):
...     slot.fill(yapyon.parse('mind:\n  endpoint: "remote"\n  model: "q4"\ndesc: y"{name}"\n'))
>>> agent.resolve()
{'name': 'local', 'persona': {'mind': {'endpoint': 'http://localhost:9931', 'model': 'q4'}, 'desc': 'local'}}
```

Prefer ordinary field-key handles when the place is already known, or filter by
its **complete label** when choosing which filler to supply. `slots("base.persona")`
and `slots(("base", "persona"))` match the same label, using folded name identity;
they do not match a prefix. `Tree.slots()` returns all retained slots, and
`Handle.slots()` restricts discovery to that subtree. Repeated labels are legal,
so every match is returned in document order, never an implicit first choice:

```python
>>> group = yapyon.parse('agents: {one<base.persona>: {}, two<base.persona>: {}}')
>>> [slot.key for slot in group["agents"].slots("base.persona")]
['one', 'two']
>>> definition = yapyon.parse('persona: {model: "demo"}')
>>> for slot in group["agents"].slots(("base", "persona")):
...     slot.fill(definition)
>>> group.resolve()
{'agents': {'one': {'model': 'demo'}, 'two': {'model': 'demo'}}}
```

An empty string or tuple filters for abstract slots. Discovery stops at an unfilled
slot, even when its label does not match: nested overrides belong to that slot's
fill. Advanced source-contribution and positional handles remain supported when
you deliberately need them; they are not the ordinary way to identify a slot.

The label says *what* fills the slot; finding it is the consumer's job, so
yapyon never reads a file on a slot's behalf. A label may reach into its
filler — `agent<base.agent>` fills with `base`'s `agent` branch — and an
empty label, `harness<>`, is abstract: whoever fills from that document must
give `harness` a value. A retained slot still unfilled when the tree resolves
is akan. A later dominating value or explicit replacement can discard a slot;
a list or multimap remains a pending contribution until filling. A higher
`None` discards the slot just as any other scalar does.
Empty dictionary overrides use ordinary merging: they preserve a dictionary
filler but replace any non-dictionary filler with `{}`. Literal `{}` and
composed empty dictionaries agree; neither forbids adding later overrides.
`part<new>:= {}` selects a fresh slot whose dictionary overrides still apply
after it is filled. SPEC §15 has the rules.

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
  name: "local"
  desc: y"{name}"
  harness<chosen>: {}
>>> resumed = yapyon.parse(saved, source="saved-agent.yap")
>>> resumed["agent"]["harness"].fill(yapyon.parse('mode: "cli"'))
>>> resumed.resolve()
{'agent': {'name': 'local', 'desc': 'local', 'harness': {'mode': 'cli'}}}
```

The superseded `name` disappears, but `desc` remains an expression and the
harness remains a slot. Saving uses the merge operation's structural facts to
combine known-key dictionaries, select proven winners, and remove compatible
empty-collection identities. It does not need to know what `name` resolves to
in a later composition. Earlier key spelling, name/non-name kind, entry order,
and explicit replacement intent survive.

No marker is needed just to remember that a dictionary was composed. Empty
dictionary contents follow the same ordinary merge rule whether literal,
composed, or emptied by edits. Since 0.6.2, literal empty slot overrides no
longer bypass that rule: filling `part<base>: {}` with `7`, `None`, a list,
or a multimap gives `part: {}`. A dictionary filler keeps its contents.
Necessary layers still survive; output is not unconditionally pipe-free.

Normalization is recursive and pointwise: dictionaries union their known keys,
while each matching field keeps its own ordered merge program. Safe empty named-
slot overrides can absorb the following dictionary, without knowing the filler.
Here is the complete three-slot document and its saved form:

```python
>>> original = '''persona:
...   mind:
...     endpoint: "https://api.minimax.io"
...     dialects:
...       chat<chat.dialect>: {}
...       responses<responses.dialect>: {}
...       anthropic<anthropic.dialect>: {}
...       |
...       anthropic:
...         api_uri: y"{endpoint}/anthropic"
... '''
>>> pending = yapyon.parse(original)
>>> compact = pending.to_source()
>>> print(compact, end="")
persona:
  mind:
    endpoint: "https://api.minimax.io"
    dialects:
      chat<chat.dialect>: {}
      responses<responses.dialect>: {}
      anthropic<anthropic.dialect>:
        api_uri: y"{endpoint}/anthropic"
>>> resumed = yapyon.parse(compact)
>>> files = {"chat": yapyon.parse('dialect: {}'), "responses": yapyon.parse('dialect: {}'), "anthropic": yapyon.parse('dialect: [1]')}
>>> for name, filler in files.items():
...     for slot in resumed.slots((name, "dialect")):
...         slot.fill(filler)
>>> resumed.resolve()["persona"]["mind"]["dialects"]["anthropic"]
{'api_uri': 'https://api.minimax.io/anthropic'}
```

A dictionary filler retains its unoverridden fields; the local dictionary replaces
a non-dictionary filler. `{}` is not an identity on arbitrary data: it is redundant
*before this following dictionary*. The same check applies at nested known-key
paths. A pending comprehension is not an empty dictionary just because no entries
are exposed; its validation and lexical scope remain intact.

Where slot layers must remain, independent known-key contributions are placed
beside their first field, rather than collected after unrelated fields. The first
key's spelling, visibility, and order still win. Computed-key domains and historical
fill checks can prevent this redistribution. A retained pipe alone is not a reason
to warn. Source and API construction can produce identical state, so the writer
does not guess how a program originated.

After reloading, rediscover corresponding fields or labels: proven normalization
may remove or split raw source operands, so an old operand index is not a persistent
identity. Deliberately editing a retained source operand remains supported, but is
not necessarily the same operation as editing its normalized logical value.

Simplification is conservative, not unconditional flattening. Computed-key
validation domains, comprehensions combined with other nonempty dictionaries,
nonempty collection comparisons, and sequential slot operations retain their
necessary layers. An uncertain child can stay layered inside an otherwise
simplified dictionary. A reset inside a sequential slot program must not become
one premerged override; an ordinary kind reset must not invent `:=`. No lookup,
environment access, function/cast/serializer, comprehension iteration, template
rendering, or runtime duplicate comparison runs to produce source.

Redundant authored pipes may disappear too. The output can therefore have a
lower syntactic tier and less resource cost; a former resource-limit refusal
need not recur. Semantic errors and later fill/edit/merge behavior still matter.
The original tree's tier and the record-only emitter's rules are unchanged:

```python
>>> layered = yapyon.parse('1 | 2')
>>> print(layered.to_source(), end="")
2
>>> yapyon.is_record(layered.to_source())
True
>>> yapyon.tier_of('1 | 2')
2
```

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

Sequential slot operations retain their needed surrounding dictionary layers
while those operations exist. Removing the parent's last field leaves an empty
dictionary, with no hidden history or marker. Reusing that empty dictionary as
slot overrides follows ordinary merging, in memory and after saving:

```python
>>> program = yapyon.parse('part<base>: {config: "reset"}')
>>> program["part"].merge(yapyon.parse('config: {new: 2}'))
>>> restored = yapyon.parse(program.to_source())
>>> for candidate in (program, restored):
...     candidate["part"].remove()
...     target = yapyon.parse('target<base>: {}')
...     target["target"].merge(candidate)
...     target["target"].fill(yapyon.parse('7'))
...     print(target.resolve())
{'target': {}}
{'target': {}}
```

Generated source uses two-space indentation, `key: value`, `key:= value`,
and pipes aligned with their contribution heads (`| {}` for a compact empty
dictionary operand). It normalizes
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
be one typo away from the unsafe one. The working standard requires `is_record`
to check syntax and the record rule without resolution or building values.
It must return false for malformed, empty, or non-record input.

**Unreleased correction:** the current source implements this full-validity
predicate. Published 0.6.5 used a lexical-only test that could return true for
broken or empty input and raised on lexical errors. `is_record` now returns
false for those inputs; API misuse still raises. `tier_of` remains a lexical
tier classification, not a syntax validator, and has not changed.

A replacement annotation is field intent, not computation; an explicit pipe
is computation even with literal operands:

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

## Yamlplus: readable as YAML and yapyon

The reviewed [YamlPlus standard](YAMLPLUS.md) starts from valid Yapyon records
that are also valid YAML 1.1 and YAML 1.2. Different interpretation is not by
itself invalid syntax. Explicit exclusions need a reason; multimaps are excluded
for now because their structure and repeated entries are not ordinary mappings.
YamlPlus is not a general YAML converter. The standalone binding uses native
safe PyYAML values; Yapyon's binding retains typed literal values. Their explicit
boundary is described below, not mandated by the format standard's import paths.

### Required behavior

- Keys remain strings. YAML-sensitive unquoted keys warn about conversion and
  possible collisions; writing warns and quotes them. Quoted keys retain exact
  non-name semantics and are never promoted to names. Quoting a former name
  preserves text but changes its later name visibility.
- Numeric variants such as `0b101`, `0o17`, `1_000`, `1e5`, `00`, and `01.5`
  remain admitted when valid in both. Non-shared interpretations with a shared
  typed alternative draw shiran; already-shared forms do not warn merely for
  their style. Fixes must preserve int versus float and negative zero.
- Ambiguous colons and selected string/escape differences are shiran, not
  blanket refusals. Double quotes provide a shared newline spelling. Active
  numeric-zero escapes followed by a digit warn, including `\08`/`\09`.
- Valid-in-both byte/stream literals are admitted. Their unavoidable YAML
  text-versus-bytes difference is hora. Bare `None` stays unquoted null and
  also draws hora; quoted `"None"` is text. Bare `null` remains invalid Yapyon.
- Source formatting must preserve comments, typed data, order, and field intent.
  Ordinary Yapyon emitter comment loss is not the profile formatter contract.
  Host-value writing has no original comments or lexemes to preserve and must
  not stringify non-string keys or silently change collection kind.

**Hora** uses a separate `info=` callback, default `None`; shiran uses `warn=`.
The CLI shows shiran by default and hora only with `--info`, on stderr. Hora
summarizes bytes and bare None separately, once per kind per operation, with
count/first location when available. Neither diagnostic changes successful
status or membership. The normative document contains measured PyYAML results
separately from the YAML reference interpretations.

### Current implementation and package boundary

**The two bindings have different, explicit reading roles.** This Yapyon release
includes `yapyon.is_yamlplus` and `yapyon.yamlplus` with typed literal
values, key provenance, and its stdlib-only runtime. The separate `yamlplus`
project has independent check/validation and native safe YAML reading/writing
through PyYAML, without Yapyon language machinery. Both must validate input and
emit profile-conformant documents. Native YAML strings `None` and byte-literal
text are not guessed into typed null/bytes.

Local verification covers both complete source suites on Python 3.11, 3.13, and
3.14, an exact standalone source distribution and fresh standalone wheel installs,
independent admission/formatting/output comparisons, and the held gates. Edge
review corrected legal-tab handling in the standalone private loader and located
stack-exhaustion refusal in Yapyon's profile validator. This bounded verification
is not a proof of every possible input, a standalone publication, or a release
announcement.

Checking uses the shared Yapyon lexer/parser plus a standard-library-only YAML
surface recognizer. It does not load YAML objects or infer Yapyon types from
them. YAML flow/block syntax recognition has a nesting refusal ceiling of128;
the shared recursive Yapyon parser may refuse stack exhaustion earlier. Host
writing keeps the ordinary export bounds/options; source formatting bounds its
complete UTF-8 output, including retained comments, with `max_size`.

The APIs retain exact types and string keys. Bytes in host output use safe b64
literals as an implementation choice. Other writers and ordinary Yapyon's
comment-dropping emitter are unchanged.

For example:

```python
>>> from yapyon import yamlplus
>>> yapyon.is_yamlplus('name: "example"\nmissing: None\n')
True
>>> yamlplus.loads('missing: None\nword: "None"\n')
{'missing': None, 'word': 'None'}
>>> warnings = []
>>> text = yamlplus.dumps({"yes": "hello", "missing": None}, warn=warnings.append)
>>> print(text, end="")
"yes": "hello"
missing: None
>>> len(warnings)
1
```

Operations are `yamlplus.check`, `is_yamlplus`, `load`/`loads`, `normalize`, and
`dump`/`dumps`. Each accepts separate optional `warn=` and `info=` callbacks;
callback exceptions propagate. Current in-tree CLI entry points are:

```sh
python -m yapyon yamlplus settings.yaml
python -m yapyon yamlplus --write settings.yaml
python -m yapyon yamlplus --info settings.yaml
```

The first validates without payload output; the second writes formatted source
to stdout. Formatting applies only the selected key, colon/comment-boundary,
and active-zero-escape fixes, preserving comments and their association, field
intent, other layout, and other admitted scalar spellings. It is idempotent and
never evaluates. CRLF source is normalized to LF, and output ends in a newline.
Shiran goes to stderr by default; `--info` additionally shows summarized hora.
Neither affects successful status. No version or release vehicle is selected.

### Output from full Yapyon constructs

The new `__as_yamlplus__()` serializer writes resolved data as conforming profile
source. References, calls, copies, comprehensions, conditionals, and composition
use the ordinary resolver; no second evaluator is added. Text/numbers/bytes are
written with profile-safe spellings, and susceptible name keys are quoted with
a warning about their changed visibility. Multimaps and unjoined templates
refuse instead of being wrapped, pruned, or implicitly rendered.

```python
>>> import yapyon
>>> from yapyon import yamlplus
>>> doc = 'name: "gw"\nmessage: y"hi {name}"\n'
>>> profile = yapyon.expand_yamlplus(doc, env={})
>>> yapyon.is_yamlplus(profile)
True
>>> yamlplus.loads(profile)
{'name': 'gw', 'message': 'hi gw'}
>>> draft = yapyon.parse(doc)
>>> draft.to_yamlplus(env={}) == profile
True
>>> 'y"hi {name}"' in draft.to_source()
True
```

`expand_yamlplus` accepts the full expansion environment/contract/resource
options plus separate `warn=` and `info=` callbacks. `Tree.to_yamlplus` uses the
same resolution options on a private working copy; it does not change the tree.
`Tree.to_source` stays non-evaluating. Existing `expand_record`, JSON/YAML/TOML,
and ordinary Yapyon output remain distinct and unchanged.

```sh
python -m yapyon expand --yamlplus --info settings.yap
```

Generated data is checked for profile validity before it is returned or written.
Comments belong to source formatting, not this resolved-data export. None and
bytes retain their documented unavoidable interpretation gaps for native YAML
readers. The standalone writer uses PyYAML with profile-safe representers, not
an unconstrained dump; its conventional diagnostic labels do not change validity.

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

Both tiers are about cost alone. A **cycle or an unguarded missing target is
akan** at any depth. Explicit `!` guards cancel their receiving contribution;
they do not suppress cycles or other errors. Composition also charges
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

