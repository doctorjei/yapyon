"""Conformance suite — SPEC §5.5 and §11 as executable tables.

Both spec tables are already test matrices; this file turns each row into a
case. It is the artifact that makes the format checkable by another
implementation: a port passes yapyon's conformance suite or it does not.

The §11 cases assert **both** sides where Python's behaviour is stable across
3.11+, because a divergence table that only tests one side is just a list of
opinions.
"""

import ast
import warnings

import pytest

import yapyon
from yapyon import (AkanError, OrderedMultimap, Template, is_record, loads,
                    loads_record)


def akan_of(text):
    """The akan a document raises, for matrix cells that must fail."""
    with pytest.raises(AkanError) as e:
        loads(text)
    return str(e.value)


# =========================================================================== #
# SPEC §5.5 — the splice matrix
#
# | Hole in… | str | b-bytes | b64-bytes | int/float/bool/None | container |
# |   yt value |
# =========================================================================== #
def splice(prefix, target, hole="{s}"):
    """Splice `target` (a top-level `s: ...` line) through a `prefix` hole."""
    return loads(f'{target}\nu: {prefix}"{hole}"\n')["u"]


def splice_akan(prefix, target, hole="{s}"):
    return akan_of(f'{target}\nu: {prefix}"{hole}"\n')


# -- row 1: y / ry ---------------------------------------------------------- #
@pytest.mark.parametrize("prefix", ["y", "ry"])
def test_row_y_str_splices_content(prefix):
    assert splice(prefix, 's: "AB"') == "AB"


@pytest.mark.parametrize("prefix", ["y", "ry"])
@pytest.mark.parametrize("target", ['s: b"AB"', r's: rb"\d"'])
def test_row_y_b_bytes_is_akan(prefix, target):
    assert "respell as b64" in splice_akan(prefix, target)


@pytest.mark.parametrize("prefix", ["y", "ry"])
def test_row_y_b64_bytes_splices_as_base64_text(prefix):
    assert splice(prefix, 's: b64"QUI="') == "QUI="


@pytest.mark.parametrize("prefix", ["y", "ry"])
@pytest.mark.parametrize("target,expected", [
    ("s: 3.10", "3.10"),            # the lexeme, not repr(3.1)
    ("s: 0xFF", "0xFF"),
    ("s: 1_000", "1_000"),
    ("s: -5", "-5"),
    ("s: True", "True"),
    ("s: None", "None"),
])
def test_row_y_scalars_splice_their_lexeme(prefix, target, expected):
    assert splice(prefix, target) == expected


@pytest.mark.parametrize("prefix", ["y", "ry"])
@pytest.mark.parametrize("target", ["s: [1, 2]", "s: {a: 1}",
                                    's:\n  + a: 1'])
def test_row_y_containers_are_akan(prefix, target):
    assert "cannot interpolate" in splice_akan(prefix, target)


@pytest.mark.parametrize("prefix", ["y", "ry"])
def test_row_y_templates_are_akan(prefix):
    assert "cannot splice a template" in splice_akan(
        prefix, 'x: "v"\ns: yt"{x}"')


# -- row 2: yb -------------------------------------------------------------- #
def test_row_yb_str_is_akan():
    assert "no implicit encode" in splice_akan("yb", 's: "AB"')


@pytest.mark.parametrize("target", ['s: b"AB"', 's: b64"QUI="'])
def test_row_yb_bytes_splice_decoded(target):
    assert splice("yb", target) == b"AB"


@pytest.mark.parametrize("target,expected", [
    ("s: 3.10", b"3.10"),
    ("s: 0xFF", b"0xFF"),
    ("s: True", b"True"),
    ("s: None", b"None"),
])
def test_row_yb_scalars_splice_their_ascii_lexeme(target, expected):
    assert splice("yb", target) == expected


@pytest.mark.parametrize("target", ["s: [1, 2]", "s: {a: 1}"])
def test_row_yb_containers_are_akan(target):
    assert "cannot interpolate" in splice_akan("yb", target)


def test_row_yb_templates_are_akan():
    assert "cannot splice a template" in splice_akan(
        "yb", 'x: "v"\ns: yt"{x}"')


# -- row 3: yt (§6) --------------------------------------------------------- #
# yt has no matrix of its own. Since 2026-09-14 a template resolves against the
# document exactly as `y` does and differs only in not being joined, so §5.5
# governs `render()` and the conformance claim is an *equality*: rendering a yt
# reproduces the equivalent y, cell for cell. That is what "an unjoined
# y-string" means, and it is the property that keeps the two from drifting.
MATRIX_ROWS = [
    's: "AB"', 's: b64"QUI="', "s: 3.10", "s: 0xFF", "s: 1_000", "s: -5",
    "s: True", "s: None",
]


@pytest.mark.parametrize("target", MATRIX_ROWS)
def test_row_yt_render_equals_the_equivalent_y(target):
    assert splice("yt", target).render() == splice("y", target)


@pytest.mark.parametrize("target", ['s: b"AB"', r's: rb"\d"'])
def test_row_yt_refuses_to_render_what_y_refuses_to_splice(target):
    # carried, but not renderable: §5.5 governs the join, not the delivery
    with pytest.raises(AkanError) as e:
        splice("yt", target).render()
    assert "respell as b64" in str(e.value)
    assert "respell as b64" in splice_akan("y", target)


@pytest.mark.parametrize("target", ["s: [1, 2]", "s: {a: 1}", 's:\n  + a: 1'])
def test_row_yt_carries_a_container_that_y_cannot_splice(target):
    # the one place the two rows genuinely differ, and only in *when*: a y is
    # always joined so it akans at parse; a yt is joined only if asked
    t = splice("yt", target)
    assert len(t.values) == 1
    with pytest.raises(AkanError) as e:
        t.render()
    assert "cannot interpolate" in str(e.value)
    assert "cannot interpolate" in splice_akan("y", target)


def test_row_yt_templates_are_akan():
    assert "cannot splice a template" in splice_akan("yt", 'x: "v"\ns: yt"{x}"')


# =========================================================================== #
# SPEC §11 — the divergence table (vs Python)
# =========================================================================== #
def test_unquoted_words_are_names_in_python_and_akan_here():
    assert eval("1 + 1") == 2                        # bare words evaluate
    assert "no plain scalars" in akan_of("a: hello\n")


def test_triple_quote_leading_whitespace_kept_in_python_dedented_here():
    assert ast.literal_eval('"""a\n    b"""') == "a\n    b"
    assert loads('k: """a\n    b"""\n')["k"] == "a\nb"


def test_newline_after_the_opening_delimiter_kept_in_python_dropped_here():
    assert ast.literal_eval('"""\na"""') == "\na"
    assert loads('k: """\n  a"""\n')["k"] == "a"


def test_unknown_escapes_kept_in_python_akan_here():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert ast.literal_eval(r'"\q"') == "\\q"    # backslash survives
    assert "unknown escape" in akan_of(r'x: "\q"')


def test_named_character_escapes_exist_in_python_akan_here():
    assert ast.literal_eval(r'"\N{BULLET}"') == "\u2022"
    assert "unknown escape" in akan_of(r'x: "\N{BULLET}"')


def test_lone_surrogates_allowed_in_python_akan_here():
    assert ast.literal_eval(r'"\ud800"') == "\ud800"
    assert "surrogate" in akan_of(r'x: "\ud800"')


def test_high_octal_escapes_truncate_in_python_and_are_akan_here():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert ast.literal_eval(r'b"\777"') == b"\xff"     # 511 & 0xFF
    assert "outside the byte range" in akan_of(r'x: b"\777"')


def test_brace_producing_escapes_are_content_in_both():
    # not a divergence — yapyon matches Python's layering on purpose
    assert eval(r'f"\x7bname\x7d"') == "{name}"
    assert loads(r'x: y"\x7bname\x7d"') == {"x": "{name}"}


@pytest.mark.parametrize("src,hint", [
    ('x: f"h"', "no f-strings"),
    ('x: t"h"', "yeeted"),
    ('x: u"h"', "just remove it"),
])
def test_f_t_and_u_prefixes_are_akan_with_a_hint(src, hint):
    # their meaning depends on an enclosing program; a data file has none
    assert hint in akan_of(src)


def test_y_prefixes_are_a_syntax_error_in_python_and_native_here():
    with pytest.raises(SyntaxError):
        ast.literal_eval('y"{a}"')
    assert loads('a: "A"\nu: y"{a}!"\n')["u"] == "A!"


def test_prefix_spelling_is_multiple_in_python_and_canonical_here():
    assert ast.literal_eval(r'BR"\d"') == ast.literal_eval(r'rb"\d"')
    assert "canonical order is rb" in akan_of(r'x: br"\d"')
    assert "unknown string prefix" in akan_of(r'x: RB"\d"')


def test_inf_and_nan_reachable_in_python_and_unspellable_here():
    assert float("inf") == float("inf")
    assert "no inf/nan spelling" in akan_of("a: inf\n")
    assert "no inf/nan spelling" in akan_of("a: nan\n")


def test_dict_keys_are_any_hashable_in_python_and_identifiers_here():
    assert ast.literal_eval('{1: "a", (2, 3): "b"}') == {1: "a", (2, 3): "b"}
    assert "numeric keys are akan" in akan_of('1: "a"\n')
    assert "quoted keys are reserved" in akan_of('"k": "a"\n')


def test_duplicate_keys_collapse_in_python_and_are_akan_here():
    assert ast.literal_eval('{"a": 1, "a": 2}') == {"a": 2}       # silently
    assert "duplicate key" in akan_of("a: 1\na: 2\n")
    kept = loads("+ a: 1\n+ a: 2\n")                              # unless `+ `
    assert [(k, v) for k, v in kept] == [("a", 1), ("a", 2)]


def test_identifiers_fold_under_nfkc_in_python_and_are_exact_here():
    namespace = {}
    exec("\ufb01 = 1", namespace)                   # U+FB01 LATIN SMALL FI
    assert namespace["fi"] == 1                     # Python folded it to "fi"
    doc = loads("\ufb01: 1\nfi: 2\n")               # yapyon keeps them apart
    assert doc == {"\ufb01": 1, "fi": 2}


@pytest.mark.parametrize("src", ["a: {1, 2}\n", "a: (1, 2)\n", "a: 1j\n"])
def test_set_tuple_and_complex_are_types_in_python_and_akan_here(src):
    literal = src.split(": ", 1)[1].strip()
    assert ast.literal_eval(literal) is not None    # Python has all three
    with pytest.raises(AkanError):
        loads(src)


# =========================================================================== #
# SPEC §12 — the yapyon record
#
# The eight scalar kinds of GRAMMAR §G6 split five/three, and that split *is* the
# record rule (§12.2). A port claiming the record level must agree on every
# row of this table and on the subset property below.
# =========================================================================== #
LITERAL_SCALARS = ['"x"', "'x'", 'b"\\x89"', 'b64"aGk="', 'r"x\\n"',
                   'rb"x\\n"', "1", "0xFF", "3.10", "1_000", "True", "False",
                   "None"]
DEFERRED_SCALARS = ['y"{a}"', 'ry"{a}"', 'yb"{a}"', 'yt"{a}"']


@pytest.mark.parametrize("literal", LITERAL_SCALARS)
def test_row_every_literal_scalar_is_a_record(literal):
    text = f'a: "seed"\nu: {literal}\n'
    assert is_record(text)
    assert loads_record(text)["u"] == loads(text)["u"]      # §12.3 subset


@pytest.mark.parametrize("literal", DEFERRED_SCALARS)
def test_row_every_y_family_scalar_is_not_a_record(literal):
    text = f'a: "seed"\nu: {literal}\n'
    assert not is_record(text)
    with pytest.raises(AkanError) as e:
        loads_record(text)
    assert "must all be literals" in str(e.value)
    assert (e.value.line, e.value.col) == (2, 3)   # §12.5: at the prefix


def test_the_two_forms_agree_on_a_record():
    # §12.3: a full implementation loading a record returns exactly what a
    # record implementation returns
    text = ('name: "gw"\nport: 8080\nratio: 3.10\nraw: "{not_a_hole}"\n'
            'blob: b64"aGVsbG8="\nxs:\n  - True\n  - None\n'
            'm:\n  + k: 1\n  + k: 2\n')
    assert loads_record(text) == loads(text)


def test_a_record_never_produces_a_template():
    # §12.4: Template is the one value type the two forms do not share
    assert isinstance(loads('a: "v"\nt: yt"{a}"\n')["t"], Template)
    with pytest.raises(AkanError):
        loads_record('a: "v"\nt: yt"{a}"\n')


def test_a_multimap_is_plain_data_and_survives_into_a_record():
    # §12.4: the criterion is "nothing deferred", not "builtin types only"
    mm = loads_record("m:\n  + a: 1\n  + a: 2\n")["m"]
    assert isinstance(mm, OrderedMultimap)
    assert [(k, v) for k, v in mm] == [("a", 1), ("a", 2)]


def test_unicode_version_reports_this_installs_tables():
    # GRAMMAR §G4.1: an implementation must document where its identifier tables come
    # from. yapyon's are the host interpreter's, so it reports rather than
    # claims -- and reports the *same* tables isidentifier() actually uses.
    import unicodedata
    assert yapyon.UNICODE_VERSION == unicodedata.unidata_version
    # The guaranteed floor is Python 3.11's, and no supported host is older.
    major, minor, _ = yapyon.UNICODE_VERSION.split(".")
    assert (int(major), int(minor)) >= (14, 0)
