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

from yapyon import AkanError, OrderedMultimap, Template, loads


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
    assert "cannot splice a template" in splice_akan(prefix, 's: yt"{x}"')


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
    assert "cannot splice a template" in splice_akan("yb", 's: yt"{x}"')


# -- row 3: yt, at fill time (§6) ------------------------------------------- #
# NOTE: values reach a template from the consumer, not from the document, so
# the b/b64 spelling distinction does not exist here — which is what the
# matrix's "— (no spelling at fill)" cell records. These cases follow §6's
# prose ("bytes fill as standard base64 … the one canonical bytes→text
# bridge"); see the workbook note on §5.5's conflicting `akan¹` cell.
def filled(hole, **values):
    return loads(f't: yt"{hole}"\n')["t"].fill(**values)


def test_row_yt_str_fills_verbatim():
    assert filled("{s}", s="A B\tC") == "A B\tC"


def test_row_yt_bytes_fill_as_base64():
    assert filled("{s}", s=b"AB") == "QUI="


@pytest.mark.parametrize("value,expected", [
    (8080, "8080"), (True, "True"), (False, "False"), (None, "None"),
    (3.10, "3.1"),                  # canonical, not the document's lexeme
    (0.1 + 0.2, "0.30000000000000004"),
])
def test_row_yt_scalars_fill_as_canonical_spellings(value, expected):
    assert filled("{s}", s=value) == expected


@pytest.mark.parametrize("value", [[1, 2], {"a": 1}, (1, 2), OrderedMultimap()])
def test_row_yt_containers_are_akan(value):
    with pytest.raises(AkanError) as e:
        filled("{s}", s=value)
    assert "cannot fill" in str(e.value)


def test_row_yt_templates_are_akan():
    with pytest.raises(AkanError) as e:
        filled("{s}", s=Template([("text", "x")]))
    assert "cannot fill" in str(e.value)


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
