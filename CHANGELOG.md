# Changelog

All notable changes to yapyon are recorded here. Section numbers refer to the
yapyon specification.

This project uses [PEP 440](https://peps.python.org/pep-0440/) versions.
`0.1.0` is the first release that is not a pre-release; every `0.1.0aN`
before it needed `pip install yapyon --pre` to be seen.

---

## 0.6.0.dev0 — Unreleased

Development prerelease targeting specification and grammar **v0.6** for
merge/source composition and unfinished persistence. This section records
unreleased work, not a publication claim.

### Changed — breaking

- **Ordinary collection merging (§15.2)** combines lists by whole typed
  elements and multimaps by complete key/value pairs, instead of replacing
  them wholesale. Equal items retain the greater per-input occurrence count,
  not the sum. Earlier positions stay; incoming occurrences match the first
  equal unmatched original earlier occurrence or append in incoming order.
  A match takes the complete higher representation, including lexemes and
  a dictionary item's key order/kind, without recursive member fusion.
  Standalone and explicitly replaced collections keep authored repetitions.
- **Typed merge equality** distinguishes bool, int, and float: True, 1, and
  1.0 are different items. Same-kind values ignore incidental literal spelling;
  dictionaries compare associations independent of entry order/key kind,
  multimaps compare ordered entry sequences, and Templates compare delivered
  parts and hole metadata without rendering. Ordinary expression equality
  retains its existing numeric behavior.
- **None yields to containers in either order**, including empty dictionaries,
  lists, and multimaps. Compatible empty inputs yield rather than clear
  populated collections. Other noncombining kinds take the higher whole value. Use explicit
  field replacement to force None or an empty collection over earlier data.
- **Copies and calls merge by eventual value kind**, not parser-node class.
  A deferred copy/call returning a dictionary now merges by key rather than
  replacing an earlier dictionary wholesale; returned lists/multimaps use the
  same collection operation as literals. Unknown kinds wait for resolution
  without executing during merge or source saving.

### Added

- **Field replacement:** `key:= value` discards that field's earlier value,
  including pending computation, and uses the complete incoming RHS. It is
  not deletion or protection from later overrides. Colon and equals are
  separate tokens, so `key : = value` is also valid; flow newlines may separate
  them. An annotation alone does not raise the tier of otherwise literal data,
  and direct record normalization preserves it. Same-contribution dictionary
  duplicates remain akan; matched dictionary keys retain earlier spelling,
  position, and name/non-name kind, without promotion.
- **Explicit value composition (§16.5):** `|` is the lowest-precedence value
  operator, below logical `or`, and associates left to right across mixed block
  and flow operands. Right grouping remains meaningful; merge is not generally
  associative. A pipe requires at least a ledger even with literal operands.
  The hole/call-argument reference grammar is unchanged.
- **Faithful unfinished-source layers (§15.8):** `Tree.to_source()` retains
  computed-key dictionaries, comprehensions with nonempty contributions,
  collection programs, replacement intent, lexical scopes, and meaningful
  grouping as one parseable document. It does no lookup, environment access,
  call, cast, serialization, comprehension iteration, template rendering,
  or runtime duplicate comparison, and leaves the source tree unchanged.
- **Slot composition preserves sequential operations.** A labeled field's
  complete dictionary RHS is one override contribution, not a sequence to
  apply separately to a future filler. Saving may lift sequential slot
  operations into surrounding dictionary layers. Literal empty overrides
  mean no operation on any filler kind; a new replacement slot still fills
  normally. Kind-dependent named-slot contributions retain a discoverable,
  fillable slot rather than guessing its eventual kind or final collection
  position.
- The former computed-key, pending replacement-boundary, and merged-dictionary-
  comprehension save refusals are lifted where explicit layers faithfully
  represent their state. **A completed fill's undecided historical abstract-slot
  obligation and an unattached slot remain save-time refusals.** A later edit
  is not retroactive fulfillment of a prior fill's own obligation. Source
  saving remains distinct from record emission and finished-data serializers.

### Documentation

- Correct README quote-reuse guidance: a hole may use the enclosing string's
  quote mark. Correct stale identifier-only-key and bare-call reservations
  while retaining the narrower hole-interior postfix grammar. Extend the guide
  and tutorial with typed merging, field replacement, meaningful grouping,
  and save/reload continuations.

## 0.5.3 — 2026-10-25

Built to specification **v0.5**, amended with collection construction and data
expressions. The operator-word compatibility change is noted below.

### Compatibility

- Lowercase operator words have their expression meaning in the new value
  grammar. In particular, `not(None)` is logical negation, not a call to a
  declared function named `not`, as it could be in 0.5.2. Use a non-operator
  declared name (the existing uppercase naming convention avoids collisions).
  Ordinary keys/path segments keep these words as names; hole references
  retain their separate §5.1 grammar.

### Added

- **Collection comprehensions (§16)** for lists, dictionaries, and multimaps,
  in inline and block forms. One `for` clause and one optional `if`; list
  inputs bind one item, dictionary/multimap inputs bind each key/value pair.
  Sources and result kinds are independent. Bindings are lexical and local;
  output is fresh typed data. Computed result keys retain exact text, dictionary
  duplicates are akan, and multimap repeats/order are retained.
- **Data expressions:** comparisons, membership, `is None`/`is not None`, and
  short-circuit boolean `and`/`or`/`not`. Conditions accept True, False, and
  None only; None counts as false. Boolean operators return booleans, not
  arbitrary operands. Explicit `__bool__` casting is unchanged.
- **Postfix operations on constructed values and call results**, including
  `[dialect for dialect in choices if condition][0]` and `.__get__(0)` for an
  optional first result. Evaluation remains eager; selecting the first item
  does not hide later comprehension errors. Safe receiver chains retain
  their boundary through postfix selection and explicit grouping.
- **Nonempty inline multimaps:** `{+ key: value, key: value}` uses one leading
  marker and ordinary comma-separated pairs. Empty remains `{+}`; block
  entries retain their individual markers. Literal inline multimaps are records.
- Unfinished source saving preserves comprehensions and predicates without
  evaluating inputs, environment references, or functions. A deferred dictionary
  comprehension merged with another nonempty dictionary contribution is refused
  at save time because source cannot retain both layers; empty literal layers
  remain safe. In-memory dictionaries merge normally, before retained generated
  value bodies resolve; lists/multimaps retain whole replacement.
- Portable conformance cases and a complete `examples/comprehensions.yap`.

### Fixed

- A safe call on None skips its remaining arguments before evaluating them,
  using the existing shared call path.

## 0.5.2 — 2026-10-24

Built to specification **v0.5**, amended. **No breaking changes.** Adds
non-evaluating source persistence for partially composed Trees; existing
in-memory merging, filling, and resolution keep their behavior.

### Added

- **`Tree.to_source()` (§15.8): save partially composed documents.** Write
  unresolved yapyon source, preserving expressions, computed keys, and
  remaining named/abstract slots without consulting the environment or
  invoking functions. Reload the text to continue filling and editing.
  Saving leaves the original Tree unchanged. Layout is normalized, comments
  are lost, and reloaded diagnostics refer to the saved document.
- Save-time akan for potentially matching computed keys across merged
  dictionaries, and for a completed fill's still-undecided abstract-slot
  obligation. Pending slot overrides that would lose a replacement boundary
  when flattened are also refused, rather than changing what a later filler
  inherits. Empty and provably disjoint dictionary contributions do not
  trigger the collision refusal, and harmless override chains remain valid.
  In-memory merge/fill/resolve behavior and record-only `emit()` remain
  unchanged.

### Fixed

- Record `emit()` reports record-rule akan for an unfilled slot instead of
  raising an internal-invariant exception.

## 0.5.1 — 2026-10-24

Built to specification and grammar **v0.5**, amended. **Breaking**: the
built-in functions are renamed. Released as a patch because nothing yet
depends on 0.5.0.

### Added

- **§5.1.5: casters.** `__str__`, `__int__`, `__float__`, and `__bool__`
  convert one value, with Python's names and yapyon's own parsing. Text
  must be the whole value — `"03"` is 3, but `"3.0"`, `"42abc"`, and
  `" 42"` are akan as ints, unlike C's `atoi`; a float truncates to an
  int; bools are 1 and 0 both ways (`__bool__` reads `true/false`,
  `yes/no`, `on/off`, `1/0` in any case); `__str__` writes numbers as
  splicing does and refuses bytes. `None` is akan unless `?.` skips the
  call.
- **`__get__(key, default=None)`**: `dict.get` for mappings and lists
  (negative indices from the end); a multimap gives the key's list view.
- **§13.1: `?.`.** A call written after `?.` is skipped when its receiver
  is `None`, and the rest of the chain with it, so
  `models.__get__(0)?.__str__()` is `None` for an empty list.
- **§5.6: bare call values.** A value ending in a call may be written
  without parentheses — `port: port_text.__int__()` — and means its copy:
  a call's result is owned by nobody, so it may land where it is written.
  A bare path is still akan, and its message now offers both readings.
- GRAMMAR §G4.3 states why `03` is akan as a literal: readers disagree
  whether `010` is 8 or 10.
- **§7: quoted and computed string keys.** Plain quoted keys work in records;
  `y"…"` and `ry"…"` keys resolve through the same machinery as values.
  Quoted keys are not names: subscript through a named parent to reach them.
  Key equality is resolved string equality; duplicates within a mapping are
  akan, while matching keys across merged layers merge with layer precedence.
  `__KEY__` returns the key text. Empty keys, dunders, and `@`-keys are refused.
- Tree walking exposes pending keys as opaque `Key` locations without
  evaluating them. Fills and merges remain before resolution. Record output
  quotes resolved computed keys; contract results may carry any legal string
  key. JSON/TOML metadata paths escape `~` and `/` to keep keys unambiguous.

### Changed (breaking)

- **Built-ins are lowercase dunders**: `__AS_JSON__`, `__AS_TOML__`,
  `__AS_YAML__`, `__AS_YAPYON__`, and `__ENV__` are now `__as_json__`,
  `__as_toml__`, `__as_yaml__`, `__as_yapyon__`, and `__env__`. The old
  names are unknown built-ins. The anchors stay `__ROOT__`, `__PARENT__`,
  and `__KEY__`; declared functions use upper snake case by convention.
- Loaded mappings are dict subclasses carrying name/non-name key metadata,
  preserving `lookup` semantics. Normal dict indexing and equality remain;
  exact `type(value) is dict` checks should use `isinstance(value, dict)`.
- The avoidable-subscript warning now occurs during resolution, when the
  target's key kind is known; lexer/parser-only operations cannot decide it.

---

## 0.5.0 — 2026-10-24

Built to specification and grammar **v0.5**: slots, and trees a consumer
assembles before resolving. **Breaking** for
code that used `yapyon.parse` or the stage-level names; every document
that loaded in 0.4.1 loads the same.

### Added

- **§15: slots.** `persona<llamacpp>: {overrides}` makes `persona`'s value
  a slot, which the consumer fills: the filler is merged under the
  overrides, which win. A label says what fills the slot and may reach
  into the filler (`agent<base.agent>`); `harness<>` is an abstract slot,
  which a document filling from this one must give a value — a label,
  `<>` again to pass it on, or a plain value that replaces it. The meaning
  of any assembly is that of filling to literal, merging, and repeating,
  whatever order the fills are made in. A slot makes a document a template
  (tier 3) and a record holds none; one left unfilled is akan. GRAMMAR
  §G4.9 (the `LABEL` token), §G6, §G7. Designed with persona-grata, whose
  templates are among the tests.
- **`yapyon.Tree`**: `parse` and `parse_file` read a document without
  resolving it. Live handles walk it — each value's kind, value, lexeme,
  and source, line, and column; `merge` layers trees (later wins, mappings
  recurse, `None` kept); `fill`, `replace`, and `remove` edit it; and
  `resolve()` resolves once, as `loads` would. Holes bind where their
  values land, and diagnostics name the document each value came from.
- Y-strings and copies keep their lexeme, as literals already did.

### Changed (breaking)

- **`yapyon.parse` returns a `Tree`**, not the parser's root node.
- **The parser's nodes and the stages leave the top-level namespace**:
  `Lexer`, `Token`, `tokenize`, `Parser`, `parse_tokens`, `dump`,
  `Resolver`, `resolve`, `build`, and the node classes (`Node`, `Scalar`,
  `YString`, `ResolvedTemplate`, `Pair`, `Mapping`, `Sequence`,
  `MultiMap`). They remain importable from their modules
  (`yapyon.parser`, …) as internals, with no promise of stability.
- `yapyon.emit` takes a `Tree` as well as a parsed node.

### Documentation

- The README links the tutorial, the long-form guide, the specification,
  the grammar, the conformance corpus, and this changelog, with absolute
  links so they work on PyPI too.
- `docs/DETAILS.md` describes copies (§5.6) and trees and slots (§15).

---

## 0.4.1 — 2026-10-23

Built to specification and grammar **v0.4**, amended: a value may be a
copy of another, `(ref)`. Nothing here is breaking — every document that
loaded in 0.4.0 loads the same, and records are unchanged.

### Added

- **§5.6: copies.** In value position, a reference in parentheses is a
  copy of the value it names, kept typed: `supported: (wanted)` gives a
  list where `y"{wanted}"` is akan. The lookup is a hole's; the value is
  resolved where it is written and then copied, and the copy is a
  separate object. Parentheses around a literal only group it (`(1)` is
  `1`); `()` and a comma inside parentheses are akan, as yapyon has no
  tuples. A call's result can be copied, typed as its declaration says:
  `(__ENV__("X"))` keeps `None` where a y-string would write `"None"`.
  A document using parentheses is a ledger, and a record admits none (§12). GRAMMAR §G4.8
  and §G6. Requested by persona-grata.

- **§12: two styles of document.** Records and ledgers are **basic** —
  finished by their own bytes, the base case every document reduces
  toward. Templates and assemblies are **extra** — finished by something
  outside them. Names only; nothing changes in what any document means.

### Changed

- **§1: ehmon 6 no longer says that everything yapyon-native is spelled in
  the `y` namespace.** It was not true — `0q`/`0z`, the stream literals,
  `+` and `{+}`, the dunders, and `{$NAME}` are yapyon-native too. The rule
  it stood for, that the string prefixes which splice are spelled with
  `y`, is unchanged. Ehmon 1 and 2 gain a line each for copies.
- **The README is a front page**, and the long form moved to
  `docs/DETAILS.md`, which the suite executes as it does the README.
  Typos, table examples, and the showcase fence were fixed on the way.

## 0.4.0 — 2026-10-21

Built to specification and grammar **v0.4**: declared
functions take keyword arguments, documents may read the environment, and
there are four tiers.

### Breaking

- **§12: four tiers, and `tier_of` renumbers.** A document is a **record**
  (1), a **ledger** (2), a **template** (3), or an **assembly** (4). A
  ledger is what 0.3.0 called a template: it splices and calls built-ins,
  and its own bytes finish it. A template is now finished by something
  outside the document — the environment it reads, or the consumer joining
  a `yt`'s parts. So `tier_of` and `python -m yapyon tier` report **3** for
  a document holding a `yt` (it was 2), and **4** for an assembly (it was
  3). The §12.5 conformance levels follow: a ledger implementation needs no
  §6.

### Added

- **§5.1.3: environment variables.** `{$HOME}` reads a variable of the
  process loading the document — strictly: unset is akan.
  `{__ENV__("XDG_CONFIG_HOME", fallback)}` is a built-in that returns the
  fallback when the variable is unset, and `None` with no fallback, as
  Python's `os.getenv` does. An empty value is a value. `$NAME` may be the
  whole hole, a receiver (`{$HOME.__AS_JSON__()}`), an argument, or a key
  in a bracket, and takes no step; a name it cannot spell is reached
  through `__ENV__`. Splicing the value cannot inject structure. `{$X}` was
  akan in 0.3.0, so nothing that loaded changes meaning.
- **§5.1.4: only standard variables are exposed by default** — those the
  pinned POSIX and XDG standards, or Microsoft's references, define for
  location, identity, hardware, locale, language, or presentation, and
  never a secret. Any other variable looks unset. `loads`, `load`,
  `expand_record`, and `lookup` take `env_allow=` (default
  `STANDARD_ENV`; a set of names, or `ENV_ALL`) and `env=` (default
  `os.environ`; `None` turns access off). `STANDARD_ENV`,
  `POSIX_STANDARD_ENV`, `WINDOWS_STANDARD_ENV`, and `ENV_ALL` are exported.
  `python -m yapyon expand` takes `--env-allow NAME`, `--env-all`, and
  `--no-env`. `expand_record` writes the values it read into the record.
- **§13.2: another language's `impl` entry is ignored entirely** — its
  keys and whatever it holds — and each language defines its own entry's
  keys. This version already behaved so; the spec now says it, so that a
  binding added later (`cpp`, `rust`, `mojo`, `csharp`) may give its entry
  keys an older reader does not know without breaking it.
- **§13.1: a borrow is valid only during the call it was passed to**, and
  a function must not keep it. An obligation, as determinism is (§13.6):
  this implementation does not enforce it, and a Python function that
  keeps a view still works here — but a C, C++, or Rust binding frees the
  document after the load, so the rule is stated now, before those
  languages arrive.
- **Conformance:** a case may declare its environment in a
  `<name>.env.json`; without one it loads in an empty environment. Eight
  environment cases (74 in all).

- **§13.1: keyword arguments for declared functions**, as Python takes
  them: positional arguments (the receiver first) fill the parameters in
  the contract's order, and keywords fill the rest by name, so
  `{f(a, y=b)}` and `{f(y=b, x=a)}` are one call. Every parameter is filled
  exactly once — one left empty, one filled twice, or a keyword naming no
  parameter is akan at the call, naming the parameters. The function
  receives its arguments in the contract's order however the call spelled
  them, so a binding's own parameter names never matter. GRAMMAR §G5 now
  generates keyword arguments in a call to any name. A call that akaned in
  0.3.0 now loads; nothing that loaded changes meaning. Default and
  variadic parameters stay reserved (§9).

- **`docs/TUTORIAL.md`**, a walk through the format from first values to
  contracts. It teaches and does not define — the spec and grammar stay
  normative — and every example in it is executed by the suite
  (`tests/test_tutorial.py`): its `>>>` sessions as doctests, its documents
  by loading them and checking each `# -> value` comment, and its command
  line session against `examples/bridge.yap`. Nothing here is breaking.

### Fixed

- **§13.4: a function returning a string with a lone surrogate is akan.**
  A yapyon `str` is Unicode scalar values, and a document cannot write a
  lone surrogate; 0.3.0 let a declared function deliver one anyway.

- **§5.3: a subscript's key may be written later in the document.** In
  every release since `0.1.0`, an indirect subscript whose key was a
  y-string not yet resolved — `u: y"{d[p].u}"` written above
  `p: y"{q}"` — was judged on the spot and refused as *"must name a string
  or a number to use as a key, not a container"*, while the same lines in
  the other order loaded. The reference now waits for its key like any
  other forward reference, and a key that waits on the reference itself is
  reported as the cycle it is. New corpus case
  `full/20-a-subscript-key-written-later`.

---

## 0.3.0 — 2026-10-19

The specification is **v0.3**, and this release builds it. Holes take
**calls**: the serializers become built-in functions, and a document may
call functions a **contract** declares, which the loader is given. Holes
splice **values**, as Python's interpolation does, while every literal keeps
its **lexeme** for anything that writes yapyon back. Bytes gain five
**stream** spellings and integers two radixes; serializer output is fixed
exactly by a new SPEC §14, and approximates what a format cannot carry
instead of refusing it. **Several changes are breaking** — see Changed.

### Changed — breaking

- **§5.4: a hole splices its value, not its lexeme**, as Python's `str()`
  writes it (operator, 2026-10-12: *"we are going to match language
  behavior … Python will be a primary guide"*). `3.10` splices as `3.1`,
  `0xFF` as `255`, `1_000` as `1000`; a version that must keep `3.10` is a
  string. Bytes in any spelling splice into text as their repr, `b'hi'` — so
  `b"..."` in a `y` is no longer akan, and `b64"aGk="` splices as `b'hi'`,
  not `aGk=`. `yb` takes the ASCII of the same text, and a `yt` renders the
  same way.
- **§5.1.2, §14: serializer output.** Layout is §14.1's — a container that
  fits in 100 columns is one line — so JSON is no longer `indent=2`
  throughout. Serializers **approximate rather than refuse**: a multimap,
  bytes, and TOML's `None` were akan and are now written (a JSON-LD node,
  base64url text with its spelling in `@_lexemes`, a left-out key that is
  recorded), and a non-decimal integer carries an `@_lexemes` entry. YAML
  quotes with double quotes, writes a flat list that fits as a flow
  sequence, and marks types with `%TAG` handles; TOML writes an integer
  outside 64 bits as a string. Single values are accepted (JSON, YAML,
  yapyon) and written plain; `__AS_TOML__()` refuses what is not a table
  by its signature. A `yt` in a serializer's argument draws §5.1.2's one
  message, which `expand_record` now shares.
- **§4.4: writers keep spellings.** `record`, `expand_record`, and
  `__AS_YAPYON__()` write each literal's lexeme — `'x'` keeps its quotes,
  `r"..."` stays raw, a key stays as spelled before folding — and use the
  canonical form only for values with none; canonical bytes are `b"..."`.
  A short flat list is written on one line. `Hole.lexeme` in a template
  now carries a string's or bytes' lexeme too, quotes and prefix included
  (§6.2), where it was empty for them.
- **The file extension is `.yap`** (was `.ypy`) for the examples and the
  conformance corpus.
- **Literals that were silently wrong are akan:** a float literal that
  overflows (`1e400` read as infinity, which yapyon has no spelling for);
  `b64` whitespace other than space, tab, or newline. A name that folds onto
  one of the new stream prefixes (`ｈｅｘ`) is akan as any reserved spelling
  is.
- **An argument that contains the call site is akan** for any reference
  (`blk: {me: y"{blk.__AS_JSON__()}"}`), where a named ancestor used to be
  reported as a cycle. An unknown built-in such as `__AS_XML__()` is now
  akan when its hole resolves, not when it is lexed, since the grammar
  admits any dunder call.

### Added

- **§13: functions and contracts.** `loads_contract` / `load_contract`
  read a contract — a record of function names, parameter and result types
  (§13.3's type strings), and where each language finds the code — and
  `loads`, `load`, `expand_record`, and `lookup` take `contract=` and
  `provide=`. A declared function receives container arguments as
  read-only **borrows** in document order, and its result is checked deep
  against the contract, its keys folded. Every failure is akan naming the
  function, never a traceback. `tier_of` returns **3** for a document that
  calls a declared function.
- **GRAMMAR §G5: calls in holes** — `{f(x)}`, `{a.f(x)}` (the same call),
  chains `{f(x).g()}`, nesting, Python-literal arguments, keyword arguments
  to built-ins (`{cfg.__AS_JSON__(lexemes=False)}`), whitespace between
  tokens, a trailing comma, escapes in hole strings, and PEP 701 quote reuse
  (`y"{a["b"]}"`).
- **Stream literals** `bin dna oct hex c32` beside `b64` (§4.3): bytes as
  symbols in a radix, padded at the end, with the symbol count and the spare
  bits checked; and integer prefixes **`0q`** (base 4) and **`0z`**
  (Crockford base 32), with the prefix letter in either case in every radix.
- **Long decimals (§3.1):** a decimal integer past 4,300 digits is shiran,
  past `max_digits` (default 17,200) akan; conversion never depends on the
  host's own digit limit.
- **`{+}`, the empty multimap** (GRAMMAR §G6, SPEC §7.1). A block multimap
  needs an entry, so an empty one had no spelling at all, and a writer
  given one wrote nothing. `{}` stays a mapping; a flow multimap with
  entries stays reserved.
- **Indented documents (GRAMMAR §G3):** the first line holding a token sets
  the base column; blank and comment lines are not measured.
- **The pinned display-width table** (`tools/gen_wcwidth_table.py`,
  Unicode 14.0.0) that §14.1's layout measures with.
- Conformance corpus: 65 cases (was 48).

### Fixed

- **`__AS_YAML__()` wrote exponent floats as `1e+16`**, which YAML 1.1
  readers (PyYAML) read as a string; it writes `1.0e+16` (§14.4).
- **A malformed key is reported as a key** (persona-grata, 2026-10-12):
  `my-model:` said "unexpected character '-'", and `1a:` was read as the
  number 1 and a stray word. The message now names the key and a legal
  spelling. Messages no longer say "v0.1".
- **A document that is just `{}` or `[]` was written back as nothing** by
  `record`, `expand_record`, and `__AS_YAPYON__()` — output that reloads as an
  empty document, which is akan. An empty container is written flow at the
  root as anywhere else (§4.4). *Any value is a valid document* (GRAMMAR §G6)
  is now pinned by tests and corpus cases; nothing executed it before.
- **A key holding a character newer than Unicode 14 got a different message
  on different Pythons** — and the suite failed on Python 3.11, the oldest
  supported, in every release since 0.1.0. The hint asked the host's own
  Unicode and printed the host's character name. It now reads a pinned
  table of what Unicode 14.0.0 left unassigned (`tools/gen_xid_table.py`),
  so every host gives the same text. Tested on 3.11, 3.13, and 3.14.
- YAML strings holding a newline were single-quoted, where YAML folds a
  line break into a space; quoted strings are now double-quoted with
  escapes.

---

## 0.2.1 — 2026-10-12

One addition, for consumers that assemble trees: `lookup`. Nothing is
breaking.

### Added

- **`yapyon.lookup(tree, current, ref)` — §5.2's scope search over a
  loaded tree.** For a consumer that assembles several loaded documents into
  one tree and must resolve references against it by yapyon's rules rather
  than a copy of them. `current` is a node the consumer holds from inside
  `tree`, found by identity, and the answer is exactly what a hole written
  inside it would get: its own keys first, then outward, nearest winning,
  with lists and multimap entries adding no scope. `ref` takes the full hole
  grammar — anchors, subscripts, negative indices, the multimap list view
  and serializers; `__PARENT__` is `current`, so `__PARENT__.__KEY__` is its
  own key, and a bare `__KEY__` is refused. It runs the resolver's own
  search rather than a second implementation. Refusals are `AkanError`,
  located by where `current` sits, since a loaded tree has no lines; a
  `current` that is not in the tree, or is in it twice, is refused.

---

## 0.2.0 — 2026-10-12

Readiness for persona-grata: a level a loader can check (`tier_of`), a
bridge from a full document down to a record (`expand_record`), TOML arrays
of tables, a fourth serializer that writes yapyon itself, and a portable
conformance corpus. It adds no consumer functions and no environment access.
**One change is breaking**: a non-canonical `b64"..."` literal is now akan —
see Changed.

### Added

- **§5.1.2 `__AS_YAPYON__()` — a fourth serializer.** It writes the block as
  a yapyon **record** in canonical spelling (§4.4), and it is the one
  serializer that can carry everything the data model holds: multimaps,
  bytes, and `None` all encode, where JSON, TOML, and YAML each refuse at
  least one. It writes from the resolved document rather than from loaded
  values, so numbers keep their source spelling (`3.10` stays `3.10`) and
  bytes keep the prefix the document chose (`b"..."` stays `b"..."`). A
  y-string in the block encodes as the value it resolved to. **A `yt` in the
  block is akan:** a template is delivered in parts (§6) and a record has
  no form for one, the same reason `expand_record` refuses it. Not breaking
  — the name was akan before.

- **`yapyon.tier_of(text)` and `python -m yapyon tier FILE` — the level a
  document needs.** **1** is a record (§12), loadable with no resolver;
  **2** is self-contained, needing the resolver but nothing outside the
  document; **3** needs something outside it. The level is computed from
  the bytes, never read off a declaration, so a loader can check a claimed
  level rather than trust it. The CLI prints the bare number so it composes
  in a shell test. **3 is unreachable today**: no shipped construct reaches
  outside the document. The levels are numbers because they have no names
  yet.

- **`yapyon.expand_record(text)` and `python -m yapyon expand FILE` — a
  full document reduced to a record.** Every y-string is replaced by the
  value it resolves to, and what comes out is canonical record text (§4.4,
  §12) that a resolver-free implementation can load:
  `loads_record(expand_record(s)) == loads(s)`. It works from the resolved
  document rather than loaded values, so a `version: 3.10` the document
  never splices still comes back as `3.10`. **A `yt` is refused** rather
  than joined: §6 leaves rendering a template to the consumer, and a record
  has no form for one. `examples/bridge.ypy` shows the crossing.

- **§5.1.2 `__AS_TOML__()` writes TOML arrays of tables.** A list whose
  elements are all mappings now becomes `[[name]]`, under its own path
  (`[[a.b]]`), with each element written out in full before the next
  header opens — a table nested inside an element attaches to *that*
  element, not to whichever `[[parent]]` was written last. A super-table
  above an array of tables gets no header of its own, since `[[a.b]]`
  already says `a` exists; it keeps its header when it has pairs of its
  own. A **mixed** list — mappings alongside scalars — goes out with
  inline tables (`a = [{ x = 1 }, 2]`), because TOML gives a key either
  an array of tables or an array value and never both. An **empty** list
  is written inline (`a = []`): a header with no element would drop the
  key rather than write it empty.

  This shape used to be **refused**. `__AS_TOML__()` raised on any mapping
  nested in a sequence, because the only alternative then was emitting
  `str(dict)` and having it read back as a string — and refusing was the
  right minimum against that. The refusal was over-broad, though: SPEC
  §5.1.2's akan list names multimaps, bytes, and `None` in TOML, and never
  mentioned a mapping in a sequence at all. The spec already said nested
  mappings become tables; the writer had simply stopped short of the
  repeated-key case.

  **Not breaking.** Every document that loaded before still loads, to the
  same data. What was an error is now a serialization. Verified against
  real TOML, not just fixtures: the repo's own `kinemata.toml` and
  kinemata's upstream config — ten array-of-tables sites between them,
  including nested `registry[i].entry` and a 21-element `gate` — now
  round-trip `tomllib → to_toml → tomllib` unchanged, where the same
  check reported an obstruction on 2026-09-18.

- **`docs/conformance/` — a portable conformance corpus.** 48 cases written
  in the format's own terms: an input file and the **record** it must
  denote, or an input plus a sidecar naming the rule it is refused under.
  Nothing in it is Python, so a second implementation runs the same files
  against its own loader and gets a yes or no. The record tier is covered
  completely, which is what unblocks a record-only port; the full tier
  covers the lexeme rule, nearest-wins resolution and `__ROOT__`, relative
  references, the dot as bracket sugar, indirect keys, negative indices,
  the multimap list view, chained splices, and all four serializers
  including TOML arrays of tables. Expectations are hand-authored from the
  spec and deliberately spelled *differently* from their input — `b"hi"`
  against `b64"aGk="`, `name` against `ｎａｍｅ`, block against flow — because
  a pair that must be identical is not an oracle. Error cases pin *that* a
  refusal happens and under which rule, never the message text, which is UX.
  `docs/conformance/README.md` is the protocol; the suite runs the whole
  corpus, so it cannot rot.

### Changed

- **§4.3 `b64"..."` must be canonical; a non-canonical literal is now akan.**
  Base64 packs 3 bytes into 4 six-bit characters, so a final group the
  input does not fill leaves bits that the padding discards and nothing
  decodes. `b"hi"` is `aGk=` canonically, but `aGl=`, `aGm=` and `aGn=`
  decode to it as well, differing only in those two bits — and with two
  pads a single byte has sixteen such spellings. yapyon accepted all of
  them, because Python's `base64.b64decode(validate=True)` checks the
  alphabet and the padding but **not** the discarded bits.

  **Breaking.** A document carrying a non-canonical `b64` literal now
  refuses to load. That is deliberate: these are different bytes in the
  document standing for one value, which is precisely the ambiguity a
  format whose thesis is *the same bytes mean the same data* cannot keep,
  and no encoder ever writes the discarded bits nonzero — so a document
  with them is a hand-edit or a corruption rather than something to
  accommodate. The akan names the canonical spelling. **To fix:** re-encode
  the value, or write the spelling the message gives you.

---

## 0.1.0 — 2026-09-29

The first release that is not an alpha, and the first `pip install yapyon`
finds without `--pre`.

This is the **self-contained tier**: typed literals, holes and splicing,
serializers, multimaps, and layering within a document — all resolvable from
the document's own bytes, with no ambient scope, no includes, and no
environment at the format level. Consumer functions and file embedding are a
deliberate later tier, not a gap in this one.

**Breaking.** The two-tier limits change what a document between the tiers
does, and the identifier rule changes which keys are legal and which are the
same key. Both are carried here rather than left spread down the alpha line,
so if you installed `0.1.0a1`–`a4` with `--pre`, read the two entries below
before upgrading.

### Changed

- **§5.3's expansion limits now have two tiers, and passing the spec's
  threshold is a `shiran` rather than an `akan`.** Resolution depth 32 and
  rendered size 1 MiB were hard errors, which forced one implementation's
  resource bound onto every consumer of the format. They are now the
  specification's **warn tier**: passing one emits a warning and resolution
  continues. Refusal moved to an implementation-chosen **ceiling**, which this
  implementation sets at `4x` the warn tier — **depth 128, rendered size
  4 MiB** — and which `loads`/`load` still move via `max_depth` / `max_size`.
  Those two arguments keep their names and their meaning of *the point at
  which loading fails*; what changed is that they now default above the
  warning rather than sitting on it.

  **This is a behavior change.** A document between the two tiers — deeper
  than 32, or rendering more than 1 MiB — previously raised `AkanError` and
  now loads successfully while emitting a shiran to `warn=`. Code relying on
  the old failure should pass `max_depth=32, max_size=1048576` to restore it
  exactly.

  The ceiling is deliberately finite: chained doubling is exponential, so a
  resolver with no ceiling is a denial-of-service in anything parsing
  untrusted configuration. The spec now declines to fix one ceiling for every
  implementation while requiring that one exist and be documented.

  **Unrelated and unchanged: a cycle or a missing target is still an `akan`**
  at any depth. Those share §5.3 with the limits but are a different thing —
  the document can never resolve, so the error belongs at the point of the
  mistake.

---

- **Identifiers are pinned to Unicode 14.0.0 and may not contain invisible
  characters.** The identifier tables were the interpreter's, so a key with a
  character from Unicode 15 or later loaded on Python 3.13 and was akan on
  3.11. yapyon now ships a generated Unicode 14 table (`tools/gen_xid_table.py`)
  and `UNICODE_VERSION` is `"14.0.0"` on every install. **Breaking:** keys and
  hole names may no longer contain `Default_Ignorable_Code_Point` characters.
  Those include the Hangul fillers, which made a key with no visible glyph
  legal, variation selectors, the combining grapheme joiner, and, on Python
  3.13+, ZWJ and ZWNJ.
- **Width variants and canonically equivalent spellings are one name.** A name
  is folded, width variants to their standard form and then NFC, and two
  names that fold alike are the same: `ｎａｍｅ: 1` loads as `{"name": 1}`,
  `{name}` finds it, and `name` beside it is a duplicate key. Previously
  `café` precomposed and decomposed were two keys that rendered identically.
  No other NFKC merge applies (`ﬁ` stays distinct from `fi`). **Breaking**
  wherever a document relied on two such spellings being different keys.
- A keyword, string prefix, or dunder name in another spelling (`Ｔｒｕｅ`,
  `ｂ"s"`, `_＿ROOT＿_`) is akan: reserved words have exactly one spelling.

- **SPEC §1's laws restated after review; no behavior changes.** Law 2 now
  says what the format does: a record computes nothing, and the full form's
  only computation is named application of its declared encodings — the
  serializers, which the old "never … transform" wording contradicted. "No
  environment" moved from law 2 to law 3, its one home. Law 7 says "during
  loading" rather than "at parse time", "never *merely* warned about" rather
  than "never a warning", and names both kinds of `shiran`.

### Added

- **Negative list indices, with Python's meaning.** `{xs[-1]}` is the last
  element and `{xs[-3]}` the third from the end; `{xs[-0]}` is `{xs[0]}`,
  because `-0` is the integer 0. They were reserved in SPEC §9 on the
  reasoning "refuse now, allow later", which was never a ruling. Allowing them
  is a widening: no document that loaded before changes meaning. Useful on a
  multimap's list view, where `{mm.k[-1]}` is the last value filed under `k`
  without knowing how many there are. `+` is still not an index sign.

### Fixed

- **A negative index reached through a reference was neither refused nor
  range-checked.** With `i: -1`, `{xs[i]}` quietly took Python's meaning while
  the written `{xs[-1]}` was refused as reserved; with `i: -5` on a short list
  it raised a bare `IndexError` instead of an akan. A position outside the
  list is now akan at either end, whichever way the index is spelled.

## 0.1.0a4 — 2026-09-19

A fix release. Two of the three entries below are bugs in `0.1.0a3` that could
corrupt or misreport data, and both were found by checking the library against
something it had not been written for rather than by a new test case. Nothing
here is breaking; code written against `0.1.0a3` keeps working.

### Fixed

- **`__AS_TOML__()` refuses a mapping nested in a sequence instead of
  corrupting it.** A list of mappings — TOML's `[[table-array]]`, or an inline
  table inside an array — reached `str()` and was written as a quoted string,
  so `{"count": [{"name": "x"}]}` emitted `count = ["{'name': 'x'}"]` and read
  back as text rather than a table. That is a silent reinterpretation, which
  §5.1.2 forbids: where a format cannot carry a value faithfully the encoding
  is akan, never approximate. The value now raises at the point of the
  mistake. Emitting real `[[name]]` headers is a separate feature and is not
  part of this change. Affects `0.1.0a3`.
- **A stalled serializer is reported as the cycle it is.** Two serializers
  whose targets hold each other — `b1.m` encoding `b2` while `b2.m` encodes
  `b1` — failed with *"a YString cannot be serialized"*, naming the wrong
  problem at the wrong line and mentioning neither the cycle nor the other
  reference. The encoder conflated *has no faithful encoding* (a multimap,
  bytes — permanent) with *is not resolved yet* (still holds a y-string), so a
  hard error pre-empted the resolver before it could detect the cycle. Affects
  `0.1.0a3`.
- **The refusal to serialize a bare anchor says why.**
  `{__PARENT__.__AS_JSON__()}` reported *"needs a value to encode"*, which is
  false — an anchor names a value — and suggested the spelling the author had
  already written. The refusal is correct (an anchor always contains the hole
  naming it, so the reference is circular in every document); only the message
  was wrong. Behavior is unchanged.

### Documentation

- **The specification is published**, as two documents under `docs/`:
  `GRAMMAR.md` (*are these bytes well-formed yapyon?* — self-contained,
  normative for syntax) and `SPEC.md` (*what do well-formed bytes mean?*).
  References run one way, so a parser can be written from the grammar alone.
  Both ship in the sdist.

---

## 0.1.0a3 — 2026-09-14

The first release to carry breaking changes. It also fixes a parse bug present
in **every** previously published version, described under *Fixed* below.

### Removed — breaking

- **`Template.fill(mapping)` is gone.** A `yt` no longer defers its holes to a
  mapping supplied later by the consumer; it resolves them against the
  document at parse time, by the ordinary scope rules, exactly as `y` does.
  The difference between the two is now delivery alone — `y` joins the parts
  into a `str`, `yt` hands over the literal text and the resolved values
  separately, so that a consumer which knows the destination (shell, SQL,
  HTML) can escape each value for it. `y` : `yt` :: f-string : t-string.
  `Template.render()` produces the joined string where that is what is wanted;
  there is deliberately no `__str__` that joins implicitly. (§6)

  Consequences, all of them simplifying: `__ROOT__` has one meaning rather
  than two, an unbound hole is an error at parse time where the author can see
  it rather than at fill time, and a `yt` value is determined by the
  document's own bytes.

  *Migrating:* code that built a `Template` and called `.fill(data)` was using
  late binding, which this release does not replace. Resolve the values in the
  document, or join with `.render()`.

- **Dunder keys are akan.** `__foo__: "x"` loaded in `0.1.0a1` and `0.1.0a2`;
  it is now an error. The `__dunder__` namespace belongs to yapyon rather than
  to the document, which is what makes "every key of a mapping is addressable
  from a hole" true — previously `__foo__: "x"` loaded while `y"{__foo__}"`
  could never name it, and `__ROOT__` itself was a legal key. `__` and `___`
  count as dunders too. (§7)

- **The shadowing warning no longer fires.** A local definition shadowing an
  outer one used to emit a `shiran:`. Nothing about it was ambiguous — the
  scope search is total and deterministic — and it fired on correct code,
  since layered configuration is deliberate shadowing. The fix it suggested
  (`{__ROOT__.x}`) resolved to a *different value*, which makes it a trap
  rather than a warning. Anything reading warnings will see fewer.

### Fixed

- **`\"` inside a string now parses.** `x: "a\"b"` failed as *"dangling
  backslash in string"* in `0.1.0a1` and `0.1.0a2`, so **no document could put
  a double quote inside a double-quoted string** — though `\"` and `\'` have
  been in the escape table since the first release. The fix is a scanning rule
  (a backslash consumes the character it protects), so it applies to raw and
  bytes literals equally, and it is strictly widening: nothing that parsed
  before stops parsing.

- **`python -m yapyon.<stage>` no longer leaks a traceback** on a document
  error. Running an already-imported module under `-m` executes it a second
  time, giving the stage a different `AkanError` class from the one being
  caught. The per-module entry points delegate through the package path now.
  **`python -m yapyon <stage>` is the documented spelling.**

### Added

- **Subscripts — `a.b` is sugar for `a["b"]`.** The bracket is the general
  form, and its contents yield a key: a quoted literal, or a reference whose
  *value* is the key. So `{d[p]}` means "the value of `d` at the key stored in
  `p`", and the inner reference resolves in the scope of the y-string's own
  position. This also gives list indices (`{xs[0]}`) and quoted segments
  (`{a["b.c"]}`), which were previously reserved. (§5.1)

- **Multimap traversal yields a list view.** `{mm.registry}` names *every*
  value filed under `registry`, in order, as a list — 0 entries give an empty
  list, N give N — and `{mm.registry[0]}` indexes it. Splicing the view into
  text stays akan exactly as for any list. (§5.2)

- **Relative references `__PARENT__` and `__KEY__`.** A block can name its own
  position, so the same text can appear in every block and resolve to that
  block, and a block can be renamed or moved without editing its contents.
  (§5.1.1)

      store: "/cfg"
      personas:
        kimi:
          id:     y"{__PARENT__.__KEY__}"
          prompt: y"{__ROOT__.store}/{__PARENT__.__KEY__}.md"

- **Named serializers — `__AS_JSON__()`, `__AS_TOML__()`, `__AS_YAML__()`.**
  Splicing a container into text is barred because there is no one text form
  for it; a named serializer is the author saying which they mean, in the
  document, where a reader can see it. It stands to a container as `b64"..."`
  does to bytes. A serializer is an *encoding*, not a function: no arguments,
  no composition, and the set belongs to the format. (§5.1.2)

      body: y"payload={cfg.__AS_JSON__()}"

  All three writers are ours and the core remains dependency-free. **yapyon
  does not prune** — dropping a key because its value is `None` or `""` would
  be a silent reinterpretation — and because nothing is pruned, `None` reaches
  the TOML writer, where it is akan rather than approximated, TOML having no
  null.

- **An emitter — `yapyon.emit()` and `python -m yapyon record`** — rendering a
  record back to canonical yapyon, with canonical spelling now normative
  (§4.4). It reads the AST and never the loaded values, which is what keeps
  `3.10` from coming back as `3.1` and a `b"..."` literal from being respelled
  as base64. It is a **normalizer, not a round-tripper**: comments do not
  survive.

- **Shirans are shown at the command line**, on stderr, and never change the
  exit status — so a warning cannot corrupt `record`'s output when it is
  redirected into a file, nor break a pipeline on a legal document.

- **`yapyon.UNICODE_VERSION`**, reporting the Unicode data version this
  install's identifier tables come from (it follows the host interpreter).
  This is the one place a document's meaning leans on something outside its
  own bytes, so it is a machine-readable fact rather than a sentence in a
  README that can go stale.

- **Diagnostics can name their source file.** Every stage accepts `source=`;
  with one, an error reads `name:line:col`.

- **A `shiran:` for an avoidable bracket.** `{a["bar"]}` and `{a.bar}` mean
  identically the same thing, so the warning is about spelling and taking the
  fix changes nothing. It stays silent wherever the bracket was needed.

- A worked record in `examples/`.

---

## 0.1.0a2 — 2026-09-13

### Added

- **The yapyon record (§12)** — a second, restricted form in which every leaf
  has a literal value: no y-strings, nothing deferred. `loads_record` /
  `load_record` run the pipeline without the resolver and refuse the y-family;
  `is_record` tests a document by lexing. It gives a minimal implementation
  something genuinely conforming to ship, and it is a safe mode by design
  rather than an after-the-fact carve-out.

### Changed

- **Names are UAX #31 identifiers** — `XID_Start | "_"` then `XID_Continue`,
  exact codepoints, no normalization. The previous test admitted `a²`, which
  was a legal key no hole could name, and rejected a decomposed `é`. Keys and
  hole segments now answer to one rule. (§7)
- **Multimaps compare by entry sequence**, and a multimap is never equal to a
  mapping. Previously `OrderedMultimap` had no `__eq__` at all, so two loads
  of the same bytes compared unequal. (§7.1)
- **Holes are recognized before escapes decode**, so `\x7b` is content rather
  than a live hole — matching Python's f-string layering.
- Akan messages say what was expected, not only what was found.

---

## 0.1.0a1 — 2026-09-11

First public release. A config/data format: Python-style typed literals with
YAML-like block structure, and parse-time splicing (y-strings) in place of
YAML's anchors.

- Lexer, parser, resolver, and loader; `y` / `yb` / `yt` / `ry` splicing;
  ordered multimaps; a conformance suite over the splice matrix and the
  documented divergences from Python and YAML.
