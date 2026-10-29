# A yapyon tutorial

> **This document teaches; it does not define.** The format is defined by
> [`SPEC.md`](SPEC.md) (what bytes mean) and [`GRAMMAR.md`](GRAMMAR.md)
> (which bytes are well-formed). Where this tutorial and either of those
> disagree, they are right and this is wrong. Section numbers like §5.2
> point into the spec.

Every example below is a complete document. The suite loads each one, and
checks every `# -> value` comment and every `>>>` session against the
library, so an example here cannot quietly stop being true.

## 1. What yapyon is for

yapyon is a format for configuration and data. It looks like YAML and spells
its values like Python:

```yapyon
name: "api-gateway"         # -> "api-gateway"
port: 8080                  # -> 8080
debug: False                # -> False
owner: None                 # -> None
```

Its whole design follows from one sentence: **the same bytes mean the same
data, to every parser, on every machine, always.** YAML reads `no` as
`False` in some parsers and as `"no"` in others, and a version written
`3.10` becomes the float `3.1`. yapyon makes those mistakes impossible to
write rather than easy to avoid: every value says its own type, in its own
spelling.

```pycon
>>> import yapyon
>>> yapyon.loads('debug: no\n')
Traceback (most recent call last):
yapyon.lexer.AkanError: akan: line 1, col 7: bare word 'no' in value position; write False for the value or "no" for the string
```

That message shows the format's three-step diagnostics register (§10):

| Register | Means |
|---|---|
| `shiran:` | legal, but probably a mistake or costly; loading continues |
| `akan:` | an error, with a line, a column, and the fix when there is one |
| `yakamashiwa:` | a bug in yapyon itself, not in your document |

## 2. Values

A document is a mapping of keys to values, laid out by indentation:

```yapyon
name: "gateway"             # -> "gateway"
version: "3.10"             # -> "3.10"
timeout: 2.5                # -> 2.5
retries: 3                  # -> 3
limits:
  memory_mb: 512            # -> 512
  disk_gb: 0x10             # -> 16
  cpu_shares: 1_024         # -> 1024
formats: ["json", "toml"]   # -> ["json", "toml"]
hosts:
  - "a.example.com"
  - "b.example.com"
inline: {burst: 100, sustained: 25}
```

- **Strings are always quoted**, with `'...'`, `"..."`, or `"""..."""`.
  There are no unquoted strings anywhere, which is what rules out YAML's
  guessing.
- **Numbers are Python's**: underscores, and the radixes `0b`, `0o`, `0x`,
  plus yapyon's `0q` (base 4) and `0z` (Crockford base 32). An integer has
  no size limit.
- **`True`, `False`, and `None`** are the only keywords, capitalized as in
  Python.
- **Lists** are `[a, b]` or a block of `- ` items; **mappings** are
  `{k: v}` or an indented block.
- **There is no infinity, NaN, set, tuple, or date.** Each was left out
  for a reason the spec records; a date, for one, is a string until a
  program says otherwise.

Keys are bare identifiers or strings. A plain quoted key is allowed in a
record; a `y`/`ry` key is computed and needs resolution:

```yapyon
provider: "moonshot-ai"
providers:
  y"{provider}": {port: 443}
selected: (providers[provider])  # -> {"port": 443}
```

Only bare keys are **names**. A quoted or computed key, even `"model":`,
is reached by a subscript through a named parent, not by `.model` or a
bare `{model}` reference. Keys are equal when their resulting strings are
equal, regardless of how those strings were spelled or computed. Empty
keys, dunders, and keys beginning with `@` are refused (§7).

A key may appear only once in a mapping:

```pycon
>>> yapyon.loads('a: 1\na: 2\n')
Traceback (most recent call last):
yapyon.lexer.AkanError: akan: line 2, col 0: duplicate key 'a' (first defined on line 1)
```

Python and YAML both quietly keep the second. yapyon refuses, because a
repeated key is far more often a typo than an intention — and when it *is*
an intention, there is a way to say so (section 4 below).

A key with nothing after it is akan too: there is no implicit null. Write
`None` if you mean it.

### Block strings

`"""` strings are dedented to their first content line, and the newline
right after the opening `"""` is dropped, so a long string can sit where it
belongs in the layout:

```yapyon
motd:
  """
  Welcome.
    Indented lines keep their extra.
  Goodbye."""
```

```pycon
>>> print(yapyon.loads('motd:\n  """\n  Welcome.\n    Indented lines keep their extra.\n  Goodbye."""\n')["motd"])
Welcome.
  Indented lines keep their extra.
Goodbye.
```

## 3. Prefixes

A prefix changes how the characters of a string are read. `b` and `r` mean
exactly what they mean in Python:

```yapyon
path: r"C:\temp"                  # -> "C:\\temp"
magic: b"\x89PNG\r\n\x1a\n"       # -> b"\x89PNG\r\n\x1a\n"
raw_bytes: rb"\d"                 # -> b"\\d"
```

Six more spell **bytes as a stream of symbols in a radix**, one prefix per
radix (§4.3) — handy when a value arrives in one of these encodings and you
would rather not convert it by hand:

```yapyon
two: bin"0110100001101001"        # -> b"hi"
four: dna"CAATCAAC"               # -> b"hi"
eight: oct"320644"                # -> b"hi"
sixteen: hex"6869"                # -> b"hi"
thirty_two: c32"D1MG"             # -> b"hi"
sixty_four: b64"aGk="             # -> b"hi"
```

A stream fills bytes from the left and is padded at the end, so `hex"abc"`
is the two bytes `ab c0`. That is the difference between a stream and a
number: `0x6869` is the integer 26729, and `hex"6869"` is two bytes.

`f"..."`, `t"..."`, and `u"..."` are akan. In Python they evaluate against
the surrounding program, and a data file has no surrounding program — so
borrowing them would make the same text mean different things in Python and
in yapyon. The splicing string prefixes use the `y` namespace instead.

## 4. Multimaps: when keys repeat on purpose

Some data really is a list of keyed steps, where a key may come back and
the order matters — a sequence of edits, a chain of handlers. Mark each
entry with `+ `:

```yapyon
changes:
  + registry: {set: ["BypassTPMCheck"]}
  + file: {delete: ["Program Files/Edge"]}
  + registry: {remove: ["Edge Update"]}
```

```pycon
>>> changes = yapyon.loads('changes:\n  + registry: 1\n  + file: 2\n  + registry: 3\n')["changes"]
>>> changes
OrderedMultimap([('registry', 1), ('file', 2), ('registry', 3)])
>>> changes == {"registry": 1, "file": 2}
False
```

A multimap is its own type, never equal to a dict, because its order and
its repeats are data. `{+}` is the empty one; `{}` is always an empty
mapping.

## 5. Splicing with y-strings

A `y` string may contain **holes** in braces. Each hole names another value
in the document, and its text is spliced in when the document loads:

```yapyon
name: "gateway"
root: "/srv/gateway"
logs: y"{root}/logs"              # -> "/srv/gateway/logs"
banner: y"{name} starting"        # -> "gateway starting"
```

This is how yapyon replaces YAML's anchors and aliases: a value is named
where it is used, by the name it already has. Order does not matter —
a hole may name a value further down — and a chain of y-strings resolves
however long it is. Write `{{` and `}}` for literal braces.

A hole splices the **value**, the way Python's `str()` writes it (§5.4):

```yapyon
port: 0x1F90
ratio: 3.10
on: True
label: y"{port} {ratio} {on}"     # -> "8080 3.1 True"
```

So if you need `3.10` to stay `3.10`, it was a string all along: write
`version: "3.10"`.

### Which value a name finds: nearest wins

A hole looks for its first name starting where the y-string sits and
moving outward (§5.2): first the y-string's siblings, then each enclosing
level in turn, up to the top. The first match wins.

```yapyon
path: "/etc/app"
claude:
  path: y"{path}/claude"          # -> "/etc/app/claude"
  config: y"{path}/config.yap"    # -> "/etc/app/claude/config.yap"
top: y"{path}"                    # -> "/etc/app"
```

Inside `claude`, `config` finds its sibling `path`, which itself refined the
outer one. That is deliberate shadowing, the shape layered configuration
takes, and yapyon never warns about it. When you do want the top-level
value, say so with `__ROOT__`:

```yapyon
name: "outer"
inner:
  name: "inner"
  near: y"{name}"                 # -> "inner"
  far: y"{__ROOT__.name}"         # -> "outer"
```

### Reaching into containers

After the first name, a reference walks down. For a name key, `a.b` is
shorthand for `a["b"]`; a quoted or computed key needs the subscript.
Integer subscripts index lists (negative ones from the end, as in Python),
and a subscript holding a *reference* uses that reference's value as the key:

```yapyon
protocol: "codex"
servers: ["alpha", "beta", "gamma"]
dialects:
  claude: {uri: "/v1"}
  codex: {uri: "/responses"}
first: y"{servers[0]}"            # -> "alpha"
last: y"{servers[-1]}"            # -> "gamma"
chosen: y"{dialects[protocol].uri}"   # -> "/responses"
```

`{dialects[protocol]}` is "the dialect named by `protocol`". The inner
reference resolves from the y-string's own position, so it means *my*
protocol, wherever the y-string sits.

Indexing a multimap by key gives **every** value filed under that key, in
order, as a list — so a reference is never left to pick one:

```yapyon
handlers:
  + on_start: "warm_cache"
  + on_stop: "flush"
  + on_start: "open_socket"
first_start: y"{handlers.on_start[0]}"   # -> "warm_cache"
last_start: y"{handlers.on_start[-1]}"   # -> "open_socket"
```

### Where a block refers to itself

`__PARENT__` steps one level outward from where the y-string sits, and
`__KEY__` names a key rather than a value (§5.1.1). Together they let a
block refer to its own name, so it can be copied or renamed without
editing its contents:

```yapyon
store: "/cfg"
personas:
  kimi:
    id: y"{__PARENT__.__KEY__}"                     # -> "kimi"
    prompt: y"{store}/{__PARENT__.__KEY__}.md"      # -> "/cfg/kimi.md"
  goose:
    id: y"{__PARENT__.__KEY__}"                     # -> "goose"
    prompt: y"{store}/{__PARENT__.__KEY__}.md"      # -> "/cfg/goose.md"
```

### What may not be spliced

Splicing only crosses into text where there is exactly one right way to do
it (§5.5). A list or a mapping has many text forms — JSON? YAML? Python's
repr? — so splicing one is akan:

```pycon
>>> yapyon.loads('tags: ["a", "b"]\nline: y"{tags}"\n')
Traceback (most recent call last):
yapyon.lexer.AkanError: akan: line 2, col 6: cannot interpolate a list, dict, or multimap into a string
```

The fix is to name the encoding, with a serializer (section 7 below). A name that
does not exist, or y-strings that wait on each other in a cycle, are akan
too, and the message lists every reference that is stuck:

```pycon
>>> yapyon.loads('a: y"{b}"\nb: y"{a}"\n')
Traceback (most recent call last):
yapyon.lexer.AkanError: akan: line 1, col 3: references never resolve (they form a cycle): {b} at line 1, col 3; {a} at line 2, col 3
```

### Copying a whole value

A list or a mapping cannot go into text, but it can go somewhere else
whole. A reference in parentheses is a **copy**: the value it names, kept
as what it is.

```yapyon
wanted: ["responses", "chat"]
supported: (wanted)               # -> ["responses", "chat"]
servers:
  main: {host: "a.example", port: 8080}
backup: (servers.main)            # -> {"host": "a.example", "port": 8080}
port: (servers.main.port)         # -> 8080
```

Inside the parentheses goes anything a hole could name, found the same way.
The value is resolved where it is written and then copied, and the copy is
a separate object, so changing one list after loading leaves the other
alone:

```pycon
>>> d = yapyon.loads('wanted: ["chat"]\nsupported: (wanted)\n')
>>> d["supported"].append("responses")
>>> d["wanted"]
['chat']
```

Parentheses around a literal only group it, as in Python — `(8080)` is
`8080` — and there are no tuples, so `(1, 2)` is akan.

A `$` or `~` in the text of a string is an ordinary character:
`y"${HOME}"` is a dollar sign and then the hole `{HOME}`. Reading the
environment is written inside the braces, `{$HOME}` — see "Reading the
environment" in §8.

### The other y prefixes

```yapyon
name: "gateway"
port: 8080
pattern: ry"^{name}-\d+$"         # -> "^gateway-\\d+$"
frame: yb"PORT {port}\r\n"        # -> b"PORT 8080\r\n"
```

- **`ry`** is a raw y-string: backslashes are literal, holes are live —
  good for regular expressions.
- **`yb`** splices into bytes. Text never turns into bytes silently, so a
  `str` hole in a `yb` is akan; numbers splice as their ASCII.

## 6. Templates: `yt`, the string that stays in pieces

A joined string has forgotten which characters the author wrote and which
came from the data:

```pycon
>>> d = yapyon.loads('user: "; rm -rf /"\ncmd: y"echo {user}"\nsafe: yt"echo {user}"\n')
>>> d["cmd"]
'echo ; rm -rf /'
```

A `yt` string resolves its holes exactly as a `y` string does, but hands
over the pieces instead of joining them (§6):

```pycon
>>> list(d["safe"])
['echo ', Hole('user', '; rm -rf /'), '']
>>> hole = list(d["safe"])[1]
>>> hole.ref, hole.value, hole.lexeme
('user', '; rm -rf /', '"; rm -rf /"')
>>> d["safe"].render()
'echo ; rm -rf /'
```

`y` is to `yt` as an f-string is to a t-string. The code that knows where
the string is going — a shell, SQL, HTML — escapes each value itself, and
`render()` is there for when plain joining really is what you want. It is
never implicit, because an easy implicit join is the very mistake a
template exists to prevent.

## 7. Serializers: putting a container into text

A serializer is the document author naming the encoding. There are four,
built in, called inside a hole:

```yapyon
cfg:
  name: "gw"
  port: 0x1F90
  tags: ["a", "b"]
as_json: y"{cfg.__as_json__()}"
as_toml: y"{cfg.__as_toml__()}"
as_yaml: y"{cfg.__as_yaml__()}"
as_yapyon: y"{cfg.__as_yapyon__()}"
```

```pycon
>>> doc = 'cfg:\n  name: "gw"\n  port: 0x1F90\n  tags: ["a", "b"]\nj: y"{cfg.__as_json__()}"\nt: y"{cfg.__as_toml__()}"\n'
>>> print(yapyon.loads(doc)["j"])
{"name": "gw", "port": 8080, "tags": ["a", "b"], "@_lexemes": {"port": "0x1F90"}}
>>> print(yapyon.loads(doc)["t"])
name = "gw"
port = 8080
tags = ["a", "b"]
"@_lexemes" = {port = "0x1F90"}
<BLANKLINE>
```

Their output is fixed exactly by §14, layout included, so every
implementation writes the same text. Where a format cannot carry a value
directly, the serializer **approximates rather than refuses**: here the
port is written as its value, `8080`, and the spelling `0x1F90` is recorded
beside it in `@_lexemes`, where a yapyon-aware reader can restore it and
any other reader still sees correct plain data. Bytes and multimaps are
handled the same way. `{cfg.__as_json__(lexemes=False)}` writes the plain
values alone.

`{cfg.__as_json__()}` and `{__as_json__(cfg)}` mean the same thing. A
serializer cannot encode the block it sits in — that would need its own
result to compute its own result — so `{__PARENT__.__as_json__()}` is akan;
name a sibling block instead.

## 8. Four kinds of document

Everything so far sorts every document into one of four tiers (§12), and
each tier contains the one before it:

| Level | Name | Holds | Finished by | Style |
|---|---|---|---|---|
| 1 | **record** | literals only | nothing: it is already data | basic |
| 2 | **ledger** | y-strings, copies, built-in calls, collection construction, and value composition | its own bytes | basic |
| 3 | **template** | `yt` strings, slots, or reads of the environment | the environment, or the consumer joining parts or filling slots | extra |
| 4 | **assembly** | calls to declared functions | a contract | extra |

Records and ledgers are **basic**: their bytes are the whole story, so they
mean the same thing on every machine. Templates and assemblies are
**extra**: they need something from outside before they are done.

The tier is visible in the bytes, so a program can ask before it loads:

```pycon
>>> yapyon.tier_of('port: 8080\n')
1
>>> yapyon.tier_of('port: 8080\naddr: y"localhost:{port}"\n')
2
>>> yapyon.tier_of('user: "ana"\ncmd: yt"echo {user}"\n')
3
>>> yapyon.tier_of('title: "Hi"\npath: y"/{slug(title)}"\n')
4
```

A **record** is the safe form by design: nothing in it depends on
anything else, so an implementation with no resolver at all can read it
and still be conforming. `loads_record` refuses anything more, at the
prefix that makes it more:

```pycon
>>> yapyon.loads_record('name: "gw"\nport: 8080\n')
{'name': 'gw', 'port': 8080}
>>> yapyon.loads_record('name: "gw"\naddr: y"{name}:80"\n')
Traceback (most recent call last):
yapyon.lexer.AkanError: akan: line 2, col 6: a record's leaves must all be literals; a y-string defers its value (load with yapyon.loads for the full form)
```

Braces in a plain string are inert: `"{name}"` is six characters, in every
implementation, forever. Only the `y` makes a hole.

**A ledger reduces to a record.** `expand_record` resolves every hole and
writes the result back out as yapyon, so a tool on the far side needs only
the simple reader. Here it is on `examples/bridge.yap` (shown without
its comments):

```yapyon
name: "gateway"
version: "3.10"

paths:
  root: "/srv/gateway"
  logs: y"{root}/logs"
  banner: y"{name} v{version}"
```

```console
$ python -m yapyon tier examples/bridge.yap
2
$ python -m yapyon expand examples/bridge.yap
name: "gateway"
version: "3.10"
paths:
  root: "/srv/gateway"
  logs: "/srv/gateway/logs"
  banner: "gateway v3.10"
```

Every literal comes back spelled as the author spelled it; only layout and
comments are normalized.

### Reading the environment

A hole can read the environment of the program loading the document. `$NAME`
is strict, and `__env__` takes a fallback (§5.1.3):

```yapyon
home: y"{$HOME}"
config: y"{__env__('XDG_CONFIG_HOME', default_config)}/app"
default_config: y"{$HOME}/.config"
```

```pycon
>>> doc = 'home: y"{$HOME}"\nconfig: y"{__env__(\'XDG_CONFIG_HOME\', default_config)}/app"\ndefault_config: y"{$HOME}/.config"\n'
>>> yapyon.loads(doc, env={"HOME": "/home/ana"})
{'home': '/home/ana', 'config': '/home/ana/.config/app', 'default_config': '/home/ana/.config'}
>>> yapyon.loads(doc, env={"HOME": "/home/ana", "XDG_CONFIG_HOME": "/cfg"})["config"]
'/cfg/app'
```

`env` defaults to the process's own environment; it is given here so the
example means the same thing everywhere. Not every variable is visible: a
load exposes only the standard ones — locations, identity, locale, and the
like — because environments often hold secrets (§5.1.4). Anything else
looks unset until the program allows it:

```pycon
>>> yapyon.loads('key: y"{$API_KEY}"\n', env={"API_KEY": "s3cret"})
Traceback (most recent call last):
yapyon.lexer.AkanError: akan: line 1, col 5: {$API_KEY}: $API_KEY is not set, or not exposed by this application
>>> yapyon.loads('key: y"{$API_KEY}"\n', env={"API_KEY": "s3cret"},
...              env_allow=yapyon.STANDARD_ENV | {"API_KEY"})
{'key': 's3cret'}
```

A document that reads the environment is a **template**: the same bytes give
the same data in the same environment.

## 9. Functions and contracts

An assembly calls functions that the program loading it supplies. The
document names each call at its site; a **contract** declares each
function's types (§13). A contract is itself a record:

```yapyon
slug:
  params:
    text: "str"
  returns: "str"
  impl:
    python: {symbol: "slug"}
```

```pycon
>>> contract = yapyon.loads_contract('slug:\n  params:\n    text: "str"\n  returns: "str"\n  impl:\n    python: {symbol: "slug"}\n')
>>> def slug(text):
...     return text.lower().replace(" ", "-")
>>> doc = 'title: "Hello World"\npath: y"/posts/{slug(title)}"\nsame: y"/posts/{title.slug()}"\n'
>>> yapyon.loads(doc, contract=contract, provide={"slug": slug})
{'title': 'Hello World', 'path': '/posts/hello-world', 'same': '/posts/hello-world'}
```

`{title.slug()}` is the receiver form of `{slug(title)}`. An argument may
also be passed by name — the names are the contract's parameter names, and
the function still receives its arguments in the contract's order:

```pycon
>>> yapyon.loads('title: "Hello World"\npath: y"/posts/{slug(text=title)}"\n', contract=contract, provide={"slug": slug})
{'title': 'Hello World', 'path': '/posts/hello-world'}
```

The contract's
`impl` says where the code lives: with `from` (a module path), the loader
imports it; without it, as here, the program passes it in `provide=`.

The contract is what makes an assembly's reach provable rather than
something to audit. A document can call nothing its loader was not given:

```pycon
>>> yapyon.loads(doc)
Traceback (most recent call last):
yapyon.lexer.AkanError: akan: line 2, col 6: {slug(title)}: slug() is not a built-in, and no contract was given to the loader (SPEC §13.2)
```

Arguments are checked against the declared types before the call, all the
way down, and a mismatch is reported where the bad value is written:

```pycon
>>> yapyon.loads('title: 3\npath: y"/posts/{slug(title)}"\n', contract=contract, provide={"slug": slug})
Traceback (most recent call last):
yapyon.lexer.AkanError: akan: line 1, col 7: {slug(title)}: slug()'s parameter text takes str, not int
```

A function that raises is reported as akan naming it, never as a
traceback from inside your program. A list or mapping argument arrives as
a read-only view of the document's node, in document order. And a function
must be deterministic: the same contract, name, and arguments must give the
same result, or the same bytes would stop meaning the same data.

## 10. Composing values and saving unfinished source

*The `0.6.0.dev0` development line adds explicit value composition and
faithful source layers (§15.2, §15.8, §16.5).*

A pipe, `|`, combines complete values. A pair's ordinary `:` combines
contributions at that field; `:=` takes its complete incoming value instead:

```yapyon
settings:
  paths: ["base", "shared"]
  reset: ["old"]
  |
  paths: ["shared", "new", "shared"]
  reset:= []
```

```pycon
>>> doc = 'settings:\n  paths: ["base", "shared"]\n  reset: ["old"]\n  |\n  paths: ["shared", "new", "shared"]\n  reset:= []\n'
>>> yapyon.loads(doc)
{'settings': {'paths': ['base', 'shared', 'new', 'shared'], 'reset': []}}
```

Dictionaries match unique string keys recursively. Existing keys keep their
positions and name/non-name kind; new keys append. Quoted/computed keys do
not become names through merging. Lists compare **whole typed elements**,
and multimaps compare **whole key/value pairs**, not values guessed to match
by index, repeated key, or an `id` field.

For each equal item, keep the **greater count from either input**, not their
sum. Visit incoming occurrences in order: match each to the first equal,
unmatched occurrence from the original earlier collection. A match keeps its
earlier position and takes the **whole higher representation**; otherwise
append. Appended occurrences are not new match targets. Unmatched earlier
occurrences keep their own spellings. A matched dictionary-valued list item
is replaced whole, not recursively fused with the earlier item.

Merge equality distinguishes bool, int, and float, even when ordinary numeric
comparison would call them equal:

```pycon
>>> yapyon.loads('[0x1, True] | [1.0, 1]')
[1, True, 1.0]
```

`None` yields to dictionaries, lists, and multimaps in either order, including
empty ones. Compatible empty containers do not clear existing data. Other
noncombining kinds take the higher value. `field:= None` or `field:= []`
forces replacement, keeping the field present; a later contribution can
still change it. Spaces may separate `:` and `=`: `field : = []` is the
same annotation, not assignment or a new type.

### Precedence and grouping

The pipe has the **lowest value-operator precedence**, below `or`.
Unparenthesized chains associate left to right, including mixed block/flow
forms. Parentheses group an entire contribution, and that changes meaning:

```pycon
>>> yapyon.loads('{config: {old: 1}} | {config: "reset"} | {config: {new: 2}}')
{'config': {'new': 2}}
>>> yapyon.loads('{config: {old: 1}} | ({config: "reset"} | {config: {new: 2}})')
{'config': {'old': 1, 'new': 2}}
```

In the first document, the middle string discards the inherited dictionary.
In the second, the right group finishes as one dictionary before it meets
the left operand. A pipe after a pair's separator belongs to that pair's
whole value, not implicitly to the containing dictionary. To traverse a
merge result, group the whole result before its postfix. Pipes do not become
legal inside holes or call arguments; those retain their reference grammar.

Copies and calls use the **eventual value kind**, not a special whole-replacement
rule based on their syntax. A returned dictionary merges by key; returned
lists/multimaps follow the collection rule above. Earlier versions could
replace a dictionary wholesale when the incoming contribution was a deferred
copy or call. Use `:=` if whole replacement is intended.

A pipe requires at least a ledger, even with literal operands. A replacement
annotation alone does not:

```pycon
>>> yapyon.tier_of('items:= []\n')
1
>>> yapyon.tier_of('[] | []\n')
2
```

### Save the program, not one current result

`parse` returns an unresolved `Tree`; the consumer can merge it, fill selected
slots, save it, and continue later. A slot label names what fills it, never
how to find a file. Here the generated dictionary remains unfinished while
another dictionary is merged over it:

```pycon
>>> draft = yapyon.parse('persona<chosen>: {}\nmodels: {model: (model) for model in persona.models}\n')
>>> draft["models"].merge(yapyon.parse('"extra": "manual"\n'))
>>> saved = draft.to_source()
>>> resumed = yapyon.parse(saved, source="saved.yap")
>>> resumed["persona"].fill(yapyon.parse('models: ["m1"]\n'))
>>> resumed.resolve()["models"]
{'m1': 'm1', 'extra': 'manual'}
```

Saving runs no lookup, environment read, function, cast, serializer,
comprehension iteration, template rendering, or runtime duplicate comparison.
The source retains its layers, replacement intent, lexical bindings, and
meaningful grouping. Later fillers still control generated values; saving
neither chooses a filler nor freezes one current result. Record emission and
data serializers are different: they write finished data, not this program.

A labeled field's complete right-hand side is **one dictionary override
contribution**. Sequential overrides of a slot are not interchangeable with
one premerged RHS. Literal `{}` means no overrides even for a non-dictionary
filler; `part<new>:= {}` supplies a fresh slot that still needs its own filler.
The source writer may lift sequential slot operations into surrounding
dictionary layers to preserve their order.

Attached unfinished slots can be saved, but must be filled before their
values are required. Two source refusals remain: an undecided historical
abstract-slot obligation belonging to a completed fill, and a slot detached
from its dictionary field. The writer does not evaluate or invent source
syntax to evade either. Layout is normalized, comments are lost, and reloaded
diagnostics name the saved file. See the
[full persistence example](DETAILS.md#save-now-finish-later) for slot filling,
source text, and the remaining refusal rules.

## 11. Resolving a reference from code

A program that builds one tree out of several loaded documents can resolve
a reference against it by the same rules a hole uses, with `lookup` (the
reference is spelled as it would be inside a hole, without the braces):

```pycon
>>> tree = yapyon.loads('protocol: "codex"\nmind:\n  endpoint: "https://api"\n  dialects:\n    claude: {uri: "/v1"}\n    codex: {uri: "/responses"}\n')
>>> yapyon.lookup(tree, tree["mind"], "dialects[protocol].uri")
'/responses'
>>> yapyon.lookup(tree, tree["mind"]["dialects"]["codex"], "endpoint")
'https://api'
```

The second argument is the node you are holding; the answer is the one a
y-string written inside that node would get. It is the resolver's own
search, so the two cannot disagree.

## 12. Exporting Python data

When the starting point is Python values rather than unfinished document source,
`dumps` writes a record using the same canonical emitter:

```pycon
>>> settings = {"name": "gw", "ports": [8080, 8443], "enabled": True}
>>> text = yapyon.dumps(settings)
>>> print(text, end="")
name: "gw"
ports: [8080, 8443]
enabled: True
>>> yapyon.loads_record(text) == settings
True
```

All nine record data kinds are supported, including bytes and ordered multimaps.
Keys keep their exact string values and known loaded name/non-name kind. Nothing
is pruned, merged, implicitly stringified, or evaluated. A `Template`, unresolved
`Tree`, or unsupported host object is refused instead of guessed at.

Python code can supply the same mutable container in two places. Export writes
its contents independently, not an alias:

```pycon
>>> shared = [1, 2]
>>> restored = yapyon.loads_record(yapyon.dumps({"first": shared, "second": shared}))
>>> restored["first"].append(3)
>>> restored["second"]
[1, 2]
>>> shared
[1, 2]
```

A container containing itself is a cycle and raises `AkanError` with a data path.
Export limits bound container depth, decimal digits, and actual output UTF-8
bytes, including the final newline. These are not the resolver's dependency
metrics. Input is not mutated or locked: callers who need a consistent view during
concurrent mutation must use their own shared lock.

`dump(value, fp)` writes to a caller-owned text stream, without closing or flushing
it. `dump_safe(value, path)` adds checked UTF-8 file replacement: preserve the
original until complete output is ready, follow destination symlinks, and retain
private recovery data with useful native errors if replacement fails. Verified
file-protection support is currently Linux-only; unsupported platforms fail
without replacing the destination. See the [complete safe-file example and
limits](DETAILS.md#exporting-python-values).

Keep the three jobs separate: `Tree.to_source()` saves unfinished source,
`emit()` preserves record-tree lexemes, and the export functions write host data
whose authored literal spellings are no longer available.

## 13. Where next

- [`SPEC.md`](SPEC.md) — what everything means, including the parts this
  tutorial skipped: expansion limits (§5.3), identifier folding (§7), and
  the exact serializer output (§14).
- [`GRAMMAR.md`](GRAMMAR.md) — enough to write a parser from, on its own.
- [`conformance/`](conformance/) — cases another implementation can run
  against itself.
- `python -m yapyon lexer|parser|record|expand|tier FILE` — each stage, from
  the command line, writing diagnostics to stderr.
