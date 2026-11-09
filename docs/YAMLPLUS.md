# YamlPlus

**The YAML-readable profile of Yapyon records. This document is normative for
profile membership, meaning, diagnostics, and source formatting.**

This is the unreleased working standard. It states required behavior, not a
claim that a particular binding implements every requirement. See the
[implementation guide](DETAILS.md#yamlplus-readable-as-yaml-and-yapyon) for
current availability. Package layout and the shared-library boundary are not
specified here; YamlPlus must be usable independently of Yapyon.

YamlPlus is an official part of the Yapyon family, presented from YAML's side
for configuration and settings. It is not an extension of YAML or a general
YAML-to-Yapyon converter. Yapyon adds references, composition, templates, and
contracts when more is needed; see [SPEC.md](SPEC.md) and [GRAMMAR.md](GRAMMAR.md).

## 1. Membership and meaning

**A valid Yapyon record that is also valid YAML 1.1 and YAML 1.2 is YamlPlus,
except for the explicit exclusions and source constraints below.**

Syntactic validity is not the same as matching interpretation. A YAML schema
resolving a spelling as text rather than a number does not make it invalid
YAML. Such differences are not, by themselves, prohibitions.

- The source has Yapyon's literal meanings, exact types, string-key model,
  duplicate checks, name/non-name provenance, and record rules. There is no
  second evaluator or inference from a previously loaded YAML object.
- Multimaps are explicitly **akan in YamlPlus for now**, including `{+}` and
  nonempty flow/block forms. Their collection kind and repeated-entry semantics
  are not ordinary YAML mapping semantics. Ordinary Yapyon multimaps are unchanged.
- Computation, y-family strings/keys, copies, parentheses, slots, references,
  calls, merge pipes, and comprehensions are outside the record scope.
- A YAML-only spelling that is not a valid Yapyon record remains outside the
  profile: for example, bare text values, bare `null`, YAML tags/anchors/aliases,
  document markers, literal/folded block scalars, and complex keys.
- Do not add blanket exclusions merely because a spelling is unusual or a
  particular reader interprets it differently. An additional exclusion needs
  an explicit reason; implementation refusal ceilings remain separately documented.

The reference interpretations are YAML 1.1's
[bool](https://yaml.org/type/bool.html), [null](https://yaml.org/type/null.html),
[int](https://yaml.org/type/int.html), and [float](https://yaml.org/type/float.html)
type definitions dated 2005-02-11, and
[YAML 1.2.2](https://yaml.org/spec/1.2.2/), including its core schema in section
10.3.2. YAML 1.1's [timestamp](https://yaml.org/type/timestamp.html),
[merge](https://yaml.org/type/merge.html), and [value](https://yaml.org/type/value.html)
definitions dated 2005-01-18 also identify special key interpretations.

A library's extensions or omissions are not the standard. PyYAML results in
this document are separately identified measurements of **PyYAML 6.0.3
`safe_load`**. They are not substitutes for either YAML reference interpretation.

## 2. Structure, source, and comments

One nonempty document is required; a scalar or sequence may be the whole
document. Empty containers are `{}` and `[]`. An empty or comment-only file
is not a null value. Indentation and literal validity follow Yapyon's grammar;
YAML's indentless sequences are not valid Yapyon records.

Flow collections use brackets/braces and commas. Trailing commas are allowed.
Whitespace remains allowed between tokens unless source validity requires
otherwise; formatting style is not a reason to reject valid input.

### 2.1 Colon interpretation

The following is valid in both, but changes the field boundary:

```yaml
{port:8080}
```

| Reader/rules | Result |
|---|---|
| Yapyon | Key `port`, integer value `8080` |
| YAML 1.1 and 1.2 | Key `port:8080`, null value |
| Actual PyYAML 6.0.3 | `{'port:8080': None}` |

This is **shiran, not a profile refusal**. Explain the differing YAML field
boundary and recommend separating the colon. A formatter writes:

```yaml
{port: 8080}
```

Do not warn merely because there is adjacency. Shared flow forms such as
`{"port":8080}` and `{ports:[8080,8443]}` are allowed without this ambiguity
warning. If a particular source is invalid YAML outright, a warning does not
make it valid.

### 2.2 Comments and source constraints

Comments follow Yapyon's source grammar. **Source formatting must preserve
comments and the information they convey**, including their association with
the relevant setting. Dropping comments is not an acceptable simplification.
Host-value writing has no original source comments to preserve.

Separating an inline comment from preceding content is the shared spelling.
If an otherwise valid-in-both spelling makes YAML consume a Yapyon comment as
scalar content, that is an avoidable boundary difference: issue shiran and
insert separation when formatting, without discarding the comment. A reader's
permissive handling does not legalize source forbidden by the reference syntax.

- Source is UTF-8, with LF or CRLF line endings and spaces for indentation.
- Raw controls other than tabs and line endings, raw NEL, U+2028, U+2029,
  U+FEFF, U+FFFE, and U+FFFF are excluded by the profile's source constraints.
  Use escapes inside strings rather than relying on differing source-character
  or line-break handling.
- A YAML implicit key and its colon must share a physical line within the
  1,024-source-character implicit-key limit. This profile does not add YAML's
  explicit complex-key syntax to Yapyon.

## 3. String keys

Keys remain strings, not booleans, numbers, dates, or null. They obey Yapyon's
ordinary validity checks: nonempty, not beginning with `@`, and not a reserved
dunder. Numeric/bytes/container keys are not admitted, and a writer must not
stringify non-string host keys implicitly.

A bare key is a name; a quoted key retains exact text and is not a name.
Quoting does not promote it into scope lookup or dotted access. Ordinary name
folding still applies to bare names; YAML does not acquire that rule. For
identical name text across readers, use the folded spelling. Quoting an
original width/NFD spelling instead preserves its exact text and changes its
name status; these choices must not be presented as interchangeable repairs.
There is no additional ban solely for a name being written in a folding form.

**An otherwise valid unquoted key that YAML would automatically convert is
legal but discouraged and must yield shiran.** Use the reference rules, not a
four-word list. This includes boolean/null words and their specified case
variants; when writing string keys, numbers, timestamps, `<<`, and `=` can
also need quotation. PyYAML's omission of YAML 1.1's `y`/`n` booleans does not
remove the compatibility warning. Yapyon's keyword-key restrictions still apply.

When reading, explain conversion and potential collisions without changing
the Yapyon key. Warn even without an actual collision. When writing, warn and
quote affected keys. Quoted input suppresses this implicit-typing warning.

```yaml
yes: "first"
on: "second"
```

Yapyon has two distinct string keys. YAML 1.1 and actual PyYAML 6.0.3 turn
both into boolean true, so PyYAML loses the first entry; YAML 1.2 core keeps
both string keys. Quotation prevents this conversion.

A profile writer's selected quotation preserves key text but makes a former
name an exact non-name key. That visibility change must be explicit; profile
output is not a promise of interchangeable later name lookup. It does not
relax Yapyon's key checks or silently coalesce keys.

## 4. Scalar values

### 4.1 Numbers

Admit every numeric spelling that satisfies the membership rule. This includes
`0b101`, `0o17`, `1_000`, `1e5`, `00`, and `01.5`; do not retain the prototype's
extra radix, grouping, or leading-zero bans.

**Issue shiran when a numeric spelling has differing reference interpretations
and a shared, type-preserving spelling exists.** Name that alternative. Do not
warn merely because an already-shared spelling has a decimal alternative.

| Complete document | Yapyon | YAML 1.1 | YAML 1.2 core | Actual PyYAML 6.0.3 |
|---|---|---|---|---|
| `value: 0b101` | Integer 5 | Integer 5 | String `0b101` | Integer 5 |
| `value: 0o17` | Integer 15 | String `0o17` | Integer 15 | String `0o17` |
| `value: 1_000` | Integer 1000 | Integer 1000 | String `1_000` | Integer 1000 |
| `value: 1e5` | Float 100000.0 | String `1e5` | Float 100000.0 | String `1e5` |
| `value: 00` | Integer 0 | Integer 0 | Integer 0 | Integer 0 |
| `value: 01.5` | Float 1.5 | Float 1.5 | Float 1.5 | Float 1.5 |

The first four draw shiran; shared alternatives include `5`, `15`, `1000`, and
`1.0e+5`. The last two do not draw this warning. Unsigned lowercase-prefix
hexadecimal such as `0xff` is also already shared. All admitted integers and
finite floats have shared decimal/dotted spellings within existing range and
resource limits. Preserve int versus float and negative zero: replacing `1e5`
with integer `100000` is not a type-preserving repair.

These diagnostics follow the fixed reference behavior, not the currently
installed PyYAML version. Native reader ranges and resource ceilings are not
a guarantee of unlimited implementation capacity. Invalid Yapyon numeric
spellings and unsupported infinities/NaNs do not become valid through this rule.

### 4.2 Strings, quotation, and escapes

String values must be literal strings in Yapyon. An ordinary YAML bare word
is not thereby a Yapyon string. Valid-in-both raw-string and single-quoted
backslash forms are not automatically prohibited, but interpretation differences
yield shiran and should name a shared double-quoted spelling.

| Complete document | Yapyon string | YAML 1.1 / 1.2 string | Actual PyYAML 6.0.3 string |
|---|---|---|---|
| `text: "line\nbreak"` | Contains a newline | Contains a newline | Contains a newline |
| `text: 'line\nbreak'` | Contains a newline | Contains backslash+n | Contains backslash+n |
| `text: r"hello"` | `hello` | Literal `r"hello"` | Literal `r"hello"` |

The second and third are shiran. Shared double-quoted escapes include `\\`,
`\"`, `\a`, `\b`, `\f`, `\n`, `\r`, `\t`, `\v`, `\xHH`, `\uHHHH`, and
`\UHHHHHHHH`, subject to the ordinary Unicode-scalar checks. A string value
may contain newlines even when its source spelling uses escaped newlines.
YAML literal blocks such as `|-` are not Yapyon syntax and are not added here.

**An active `\0` escape followed immediately by any ASCII decimal digit is
shiran**, including `\08` and `\09`; standalone `\0` does not draw this warning.
Do not limit it to three-character escapes or to cases that actually decode
differently. Raw strings do not process these as escapes; their compatibility
issue is the raw-literal spelling instead.

| Double-quoted string | Yapyon content | YAML 1.1 / 1.2 content | Actual PyYAML 6.0.3 content |
|---|---|---|---|
| `"\0"` | NUL | NUL | NUL |
| `"\01"` | U+0001 | NUL then `1` | NUL then `1` |
| `"\012"` | Newline | NUL then `12` | NUL then `12` |
| `"\08"` | NUL then `8` | NUL then `8` | NUL then `8` |
| `"\101"` | `A` | Syntax error | ScannerError |

A formatter uses unambiguous shared escapes while preserving the Yapyon value,
for example `\01` to `\x01`, `\012` to `\x0a`, and `\08` to `\x008`.
NUL is the string character U+0000, not the null value `None`.

Unrecognized YAML double-quote escapes such as `\1` through `\7` are errors
there, not merely warnings. Non-raw `\8`/`\9` already fail Yapyon. In YAML
single quotes, backslashes are literal rather than escape introducers; apply
actual document validity and the single-quoted compatibility warning instead
of incorrectly declaring every backslash an invalid YAML escape. This standard
does not remove octal escapes from ordinary Yapyon.

### 4.3 Bytes and stream literals

Valid-in-both `b`, `rb`, `bin`, `dna`, `oct`, `hex`, `c32`, and `b64` literals
are admitted. Yapyon decodes bytes; YAML treats the literal spelling as text.
This unavoidable scalar-type gap is **hora, not shiran**.

| Complete document | Yapyon value | YAML 1.1 / 1.2 value | Actual PyYAML 6.0.3 value |
|---|---|---|---|---|
| `payload: b"hi"` | Bytes `68 69` | String containing `b"hi"` | String containing `b"hi"` |
| `payload: hex"6869"` | Bytes `68 69` | String containing `hex"6869"` | String containing `hex"6869"` |
| `payload: b64"aGk="` | Bytes `68 69` | String containing `b64"aGk="` | String containing `b64"aGk="` |

YAML does not discard the prefix/quotes or decode the payload. Its explicit
`!!binary` form works in PyYAML but is not Yapyon syntax. Do not quote an entire
byte literal as an ordinary string, stringify bytes, or add YAML-only tags as
an automatic repair. A particular literal whose contents make invalid YAML
still fails membership. Hora does not excuse a separate avoidable ambiguity.

Host output may choose a safe admitted encoding; `b64` is a useful implementation
choice, not a required canonical encoding selected by this standard.

### 4.4 Booleans and None

Boolean literals are `True` and `False`, exactly. Bare `yes`/`no`/`on`/`off`
values are not additional Yapyon booleans; explicit casting is outside records.

**Bare `None` is null and must be written unquoted. Quoted `"None"` or `'None'`
is text. Both are admitted. Bare `null` is not valid Yapyon.**

```yaml
missing: None
word: "None"
```

Yapyon reads null and text respectively. YAML 1.1, YAML 1.2 core, and actual
PyYAML 6.0.3 read the string `None` for both. Emit hora for the bare null value,
not for the ordinary quoted string. Read source quotation; do not convert every
already-loaded YAML string `None` to null. There is no shared typed null spelling
in the current intersection, just as there is no shared typed bytes spelling.

## 5. Formatting and diagnostics

A source formatter must preserve typed Yapyon data, order, key text, authored
field intent, and comments. It must not evaluate, prune, stringify unsupported
keys, promote quoted keys, or erase user information to simplify implementation.
The selected compatibility rewrites are explicit: quote affected keys, separate
ambiguous colons/comments, and write unambiguous active numeric-zero escapes.
Retain other admissible authored literal spellings unless a further rewrite
is explicitly selected; a reading warning alone is not a mandate to convert
every radix or raw literal. Respect the stated name-visibility effect of key
quotation. Host values have no original comments or literal lexemes to preserve.

| Register | Profile use | Validity effect |
|---|---|---|
| `hora:` (ほら, roughly "look/see") | Accepted unavoidable bytes/None compatibility differences | None |
| `shiran:` | Selected avoidable interpretation differences with a shared, data-preserving alternative | None |
| `akan:` | Invalid input, an explicit exclusion, or an implementation refusal | Refusal |
| `yakamashiwa:` | An internal implementation invariant failed | Implementation bug |

Warnings and notices are not permission to reinterpret data silently. Reports
identify their source location, or host-value path, where available. A proposed
repair must retain the Yapyon value and its type; selected provenance changes
such as key quotation must be disclosed rather than called universally equivalent.

- Python delivery uses separate optional callbacks: `warn=` for shiran and
  `info=` for hora, each defaulting to `None`. Messages are formatted strings.
  Do not send hora through the warning channel. Callback failures propagate.
- CLI shiran is shown by default on stderr. Hora is opt-in with `--info`, also
  on stderr. Payload output remains on stdout. Neither changes a successful
  exit status or document validity.
- Emit one hora summary per kind per operation: bytes and bare None separately,
  with a count and first location/path when available, not one notice per value.
- Checking must establish syntax validity and membership without resolution.
  A predicate returns false for malformed/empty/out-of-profile source; an
  explanatory check raises located akan. API misuse is not document invalidity.

These interface behaviors do not select final package/import paths or move any
shared components. Current binding support and its pending standalone package
boundary are described in the guide.

## 6. Illustrative Python binding

This common-path example uses the existing in-tree binding, not a normative
choice of the final standalone library namespace or a claim of full conformance:

```python
import yapyon
from yapyon import yamlplus

assert yapyon.is_yamlplus('missing: None\nword: "None"\n')
assert yamlplus.loads('missing: None\nword: "None"\n') == {
    "missing": None, "word": "None"}
warnings = []
text = yamlplus.dumps({"yes": "hello", "missing": None}, warn=warnings.append)
assert text == '"yes": "hello"\nmissing: None\n'
assert len(warnings) == 1
```

A binding is not a substitute for this standard. Its tests must establish the
admission rules, comment retention, and diagnostic delivery separately from
independent-library availability. The latter remains pending for this in-tree
binding; package restructuring does not follow from this example.
