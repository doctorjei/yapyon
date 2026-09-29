# Changelog

All notable changes to yapyon are recorded here. Section numbers refer to the
yapyon specification.

This project uses [PEP 440](https://peps.python.org/pep-0440/) versions.
`0.1.0` is the first release that is not a pre-release; every `0.1.0aN`
before it needed `pip install yapyon --pre` to be seen.

---

## 0.1.0 — 2026-09-29

The first release that is not an alpha, and the first `pip install yapyon`
finds without `--pre`.

This is the **self-contained tier**: typed literals, holes and splicing,
serializers, multimaps, and layering within a document — all resolvable from
the document's own bytes, with no ambient scope, no includes and no
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

  **This is a behaviour change.** A document between the two tiers — deeper
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
- A keyword, string prefix or dunder name in another spelling (`Ｔｒｕｅ`,
  `ｂ"s"`, `_＿ROOT＿_`) is akan: reserved words have exactly one spelling.

- **SPEC §1's laws restated after review; no behaviour changes.** Law 2 now
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
  was wrong. Behaviour is unchanged.

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
- **Holes are recognised before escapes decode**, so `\x7b` is content rather
  than a live hole — matching Python's f-string layering.
- Akan messages say what was expected, not only what was found.

---

## 0.1.0a1 — 2026-09-11

First public release. A config/data format: Python-style typed literals with
YAML-like block structure, and parse-time splicing (y-strings) in place of
YAML's anchors.

- Lexer, parser, resolver and loader; `y` / `yb` / `yt` / `ry` splicing;
  ordered multimaps; a conformance suite over the splice matrix and the
  documented divergences from Python and YAML.
