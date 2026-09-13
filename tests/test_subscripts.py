"""Subscript tests — SPEC §5.1. One test per rule, named after the rule.

`a.b` is sugar for `a["b"]`: the bracket is the general form and its content
yields a key — a quoted literal, an integer index, or a reference whose
*value* is the key. When a test and the implementation disagree, check the
spec before changing either.
"""

import pytest

from yapyon import AkanError, OrderedMultimap, loads
from yapyon.lexer import RefError, parse_ref


def akan(text, needle=""):
    with pytest.raises(AkanError) as e:
        loads(text)
    assert needle in str(e.value), f"wrong message: {e.value}"


def warnings_of(text):
    seen = []
    loads(text, warn=seen.append)
    return seen


# --------------------------------------------------------------------------- #
# The dot is sugar for the bracket
# --------------------------------------------------------------------------- #
def test_a_dot_and_a_quoted_key_are_the_same_step():
    # not two constructs: the dot reduces to the bracket, so they parse alike
    assert parse_ref("a.b").steps == parse_ref("a['b']").steps


def test_a_dot_and_a_quoted_key_resolve_alike():
    doc = 'a:\n  bar: "X"\nu: y"{a.bar}"\nv: y"{a[\'bar\']}"\n'
    out = loads(doc)
    assert out["u"] == out["v"] == "X"


def test_a_bracket_reaches_keys_a_dot_cannot():
    # this is what the general form is *for* — it subsumes §9's reserved
    # "quoted hole segments" rather than adding a third spelling.
    # No v0.1 document can *write* the key `b.c` (§7 keys are bare
    # identifiers, and quoted keys are reserved), so the reference side is
    # ready ahead of the key side. That is the compatible order.
    assert parse_ref('a["b.c"]').steps == [("key", "a"), ("key", "b.c")]


# --------------------------------------------------------------------------- #
# Integer indices are bracket-only
# --------------------------------------------------------------------------- #
def test_a_list_is_indexed_with_brackets():
    assert loads('xs: ["p", "q"]\nu: y"{xs[0]}{xs[1]}"\n')["u"] == "pq"


def test_a_dotted_integer_is_akan_because_zero_is_no_identifier():
    akan('xs: ["p"]\nu: y"{xs.0}"\n', "'0' is not an identifier")


def test_indexing_past_the_end_is_akan():
    akan('xs: ["p"]\nu: y"{xs[3]}"\n', "index 3 is past the end of a list of 1")


def test_indexing_a_non_list_is_akan():
    akan('m:\n  a: 1\nu: y"{m[0]}"\n', "is not a list")


def test_a_key_on_a_list_says_to_index_it():
    akan('xs: ["p"]\nu: y"{xs.nope}"\n', "index it with brackets instead")


def test_a_negative_index_is_reserved():
    akan('xs: ["p"]\nu: y"{xs[-1]}"\n', "negative index '-1' is reserved")


# --------------------------------------------------------------------------- #
# A bracket may hold a reference: the key is that reference's value
# --------------------------------------------------------------------------- #
def test_a_reference_in_a_bracket_names_the_key():
    doc = ('p: "claude"\nd:\n  claude: "anthropic"\n  codex: "responses"\n'
           'u: y"{d[p]}"\n')
    assert loads(doc)["u"] == "anthropic"


def test_the_inner_reference_resolves_in_the_y_strings_scope():
    # NOT in the scope of the node being indexed. {d[protocol]} means "the
    # entry named by *my* protocol", which is the whole point.
    doc = ('protocol: "outer"\nd:\n  protocol: "inner"\n  outer: "OUT"\n'
           '  inner: "IN"\nu: y"{d[protocol]}"\n')
    assert loads(doc)["u"] == "OUT"


def test_the_persona_grata_shape_resolves():
    # mind.dialects[protocol].api_uri — the case with no workaround, and the
    # api_uri's own hole still reaches its uncle
    doc = ('protocol: "claude"\nmind:\n  endpoint: "https://api"\n'
           '  dialects:\n    claude:\n      api_uri: y"{endpoint}/v1"\n'
           '    codex:\n      api_uri: y"{endpoint}/responses"\n'
           '  chosen: y"{dialects[protocol].api_uri}"\n')
    assert loads(doc)["mind"]["chosen"] == "https://api/v1"


def test_a_reference_may_nest_in_a_bracket():
    doc = 'i: "k"\nj:\n  k: "deep"\nd:\n  deep: "found"\nu: y"{d[j[i]]}"\n'
    assert loads(doc)["u"] == "found"


def test_a_reference_naming_an_integer_indexes():
    assert loads('i: 1\nxs: ["p", "q"]\nu: y"{xs[i]}"\n')["u"] == "q"


def test_a_subscript_naming_a_container_is_akan():
    akan('c:\n  x: 1\nd:\n  a: 1\nu: y"{d[c]}"\n', "not a container")


# --------------------------------------------------------------------------- #
# The bracket spelling of an identifier key is a shiran
# --------------------------------------------------------------------------- #
def test_the_long_spelling_of_an_identifier_key_warns():
    w = warnings_of('a:\n  bar: "X"\nu: y"{a[\'bar\']}"\n')
    assert len(w) == 1 and w[0].startswith("shiran:")
    assert 'the long way to write .bar' in w[0]


def test_the_warning_does_not_fire_where_the_bracket_is_needed():
    # a shiran must mark a probable mistake, not merely unusual code
    assert parse_ref('a["b.c"]').shirans == []      # a dot cannot reach it
    assert parse_ref('a["b-c"]').shirans == []
    assert warnings_of('i: 0\nxs: ["p"]\nu: y"{xs[i]}"\n') == []
    assert warnings_of('xs: ["p"]\nu: y"{xs[0]}"\n') == []


def test_the_long_spelling_still_works():
    # legal, not akan — the middle rung of the register
    assert loads('a:\n  bar: "X"\nu: y"{a[\'bar\']}"\n')["u"] == "X"


# --------------------------------------------------------------------------- #
# Multimap by-key traversal is a list view (§7.1)
# --------------------------------------------------------------------------- #
def test_a_multimap_key_names_every_value_under_it():
    doc = ('m:\n  + a: "1"\n  + b: "x"\n  + a: "2"\n'
           'u: y"{m.a[0]}{m.a[1]}"\n')
    assert loads(doc)["u"] == "12"


def test_the_view_is_a_list_so_splicing_it_whole_is_akan():
    akan('m:\n  + a: "1"\nu: y"{m.a}"\n',
         "cannot interpolate a list, dict, or multimap")


def test_zero_one_and_many_are_the_same_shape():
    # totality is what beats "unique-only": validity never depends on data
    for entries, expect in [('  + a: "1"\n', 1), ('  + a: "1"\n  + a: "2"\n', 2)]:
        doc = f'm:\n{entries}u: y"{{m.a[0]}}"\n'
        assert loads(doc)["u"] == "1"
    akan('m:\n  + a: "1"\nu: y"{m.zz[0]}"\n', "past the end of a list of 0")


# --------------------------------------------------------------------------- #
# Templates traverse identically — one grammar, three users
# --------------------------------------------------------------------------- #
def test_a_template_takes_the_same_subscripts():
    t = loads('t: yt"{d[p]}/{xs[1]}"\n')["t"]
    assert t.fill(d={"claude": "anthropic"}, p="claude", xs=["a", "b"]) == \
        "anthropic/b"


def test_a_template_traverses_a_multimap_as_a_list_view():
    mm = OrderedMultimap()
    mm.insert("k", "first")
    mm.insert("k", "second")
    assert loads('t: yt"{m.k[1]}"\n')["t"].fill(m=mm) == "second"


def test_template_holes_report_the_source_spelling():
    assert loads('t: yt"{a[\'b\']}{xs[0]}"\n')["t"].holes == ("a['b']", "xs[0]")


# --------------------------------------------------------------------------- #
# Grammar errors
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ref,needle", [
    ("a[", "unclosed '['"),
    ("a[]", "empty subscript"),
    ("a['x]", "unclosed '['"),
    ("a..b", "empty segment"),
    ("a.", "may not end with '.'"),
    (".a", "empty segment"),
    ("a['x\\\\y']", "escapes in a quoted key are reserved"),
    ("8080", "not an identifier"),
])
def test_malformed_references_are_akan(ref, needle):
    with pytest.raises(RefError) as e:
        parse_ref(ref)
    assert needle in str(e.value), f"wrong message: {e.value}"


def test_a_quoted_key_may_hold_a_brace():
    # the hole scanner tracks quotes, so } inside a key does not close it
    assert parse_ref('a["}"]').steps == [("key", "a"), ("key", "}")]


def test_the_string_delimiter_still_ends_the_string():
    # y"{a["b"]}" closes at the inner quote; use the other one, as in
    # Python before PEP 701
    akan('a:\n  b: 1\nu: y"{a["b"]}"\n', "unclosed hole")
