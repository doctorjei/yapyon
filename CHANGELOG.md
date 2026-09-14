# Changelog

All notable changes to yapyon are recorded here. Section numbers refer to the
yapyon specification.

This project uses [PEP 440](https://peps.python.org/pep-0440/) versions.
Every `0.1.0aN` is a pre-release: `pip install yapyon` will not see it without
`--pre`.

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
