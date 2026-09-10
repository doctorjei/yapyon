"""Resolver tests — one test per spec rule, named after the rule.

When a test and the implementation disagree, check SPEC.md before changing
either.
"""

import pytest

from yapyon.lexer import AkanError
from yapyon.parser import MultiMap, Scalar, YString, parse
from yapyon.resolver import Resolver, resolve


def load(text, **kw):
    """Parse and resolve; return the root node."""
    return resolve(parse(text), **kw)


def val(text, key, **kw):
    """The resolved value at a top-level key."""
    return load(text, **kw).by_key[key].value


def akan(text, needle="", **kw):
    with pytest.raises(AkanError) as e:
        load(text, **kw)
    assert needle in str(e.value), f"wrong message: {e.value}"


def warnings(text):
    r = Resolver(parse(text))
    r.resolve()
    return r.warnings


# --------------------------------------------------------------------------- #
# SPEC §5.2 — resolution scope: nearest wins
# --------------------------------------------------------------------------- #
def test_sibling_resolves():
    assert val('root: "/srv"\nlogs: y"{root}/logs"\n', "logs") == "/srv/logs"


def test_ancestor_resolves():
    node = load('name: "gw"\npaths:\n  banner: y"{name} here"\n')
    assert node.by_key["paths"].by_key["banner"].value == "gw here"


def test_nearest_wins_local_shadows_outer():
    node = load('x: "outer"\nb:\n  x: "inner"\n  v: y"{x}"\n')
    assert node.by_key["b"].by_key["v"].value == "inner"


def test_a_near_uncle_beats_a_far_ancestor():
    node = load('n: "far"\nmid:\n  n: "near"\n  deep:\n    v: y"{n}"\n')
    assert node.by_key["mid"].by_key["deep"].by_key["v"].value == "near"


def test_cousins_are_never_searched():
    akan('a:\n  x: "hidden"\nb:\n  v: y"{x}"\n', "no value named 'x'")


def test_root_is_reachable_by_plain_search():
    node = load('top: "T"\na:\n  b:\n    v: y"{top}"\n')
    assert node.by_key["a"].by_key["b"].by_key["v"].value == "T"


def test_root_escape_hatch_bypasses_the_search():
    node = load('x: "outer"\nb:\n  x: "inner"\n  v: y"{__ROOT__.x}"\n')
    assert node.by_key["b"].by_key["v"].value == "outer"


def test_shiran_on_shadow_names_both_and_the_fix():
    w = warnings('x: "outer"\nb:\n  x: "inner"\n  v: y"{x}"\n')
    assert len(w) == 1
    assert "shiran:" in w[0] and "shadows another" in w[0]
    assert "{__ROOT__.x}" in w[0]


def test_no_shiran_when_nothing_is_shadowed():
    assert warnings('root: "/srv"\nlogs: y"{root}/logs"\n') == []


def test_the_current_key_is_excluded_from_its_own_search():
    akan('a: y"{a}"\n', "no value named 'a'")


def test_dotted_segments_are_child_traversal():
    assert val('s:\n  host: "h"\nu: y"{s.host}/x"\n', "u") == "h/x"


def test_missing_child_key_is_akan():
    akan('s:\n  host: "h"\nu: y"{s.port}"\n', "there is no key 'port'")


def test_traversal_through_a_non_mapping_is_akan():
    akan('s: "str"\nu: y"{s.host}"\n', "is not a mapping")


# --------------------------------------------------------------------------- #
# SPEC §5.2 — multimaps take no part
# --------------------------------------------------------------------------- #
def test_multimap_entry_keys_are_not_searched():
    akan('m:\n  + a: "A"\n  + b: y"{a}"\n', "no value named 'a'")


def test_cannot_traverse_into_a_multimap():
    akan('m:\n  + a: "A"\nu: y"{m.a}"\n', "cannot traverse into a multimap")


def test_a_multimap_may_not_be_spliced_whole():
    akan('m:\n  + a: "A"\nu: y"{m}"\n', "cannot interpolate a list, dict, or "
                                        "multimap")


def test_scope_search_passes_through_a_multimap():
    # the enclosing mapping is still searched from inside an entry
    node = load('top: "T"\nm:\n  + a:\n      v: y"{top}"\n')
    entry = node.by_key["m"].entries[0]
    assert entry.value.by_key["v"].value == "T"


# --------------------------------------------------------------------------- #
# SPEC §5.3 — resolution order: fixpoint, chaining, cycles, caps
# --------------------------------------------------------------------------- #
def test_chains_resolve():
    node = load('a: "A"\nb: y"{a}B"\nc: y"{b}C"\n')
    assert node.by_key["c"].value == "ABC"


def test_forward_references_work():
    node = load('c: y"{b}C"\nb: y"{a}B"\na: "A"\n')
    assert node.by_key["c"].value == "ABC"


def test_a_cycle_is_akan_listing_the_stuck_references():
    with pytest.raises(AkanError) as e:
        load('a: y"{b}"\nb: y"{a}"\n')
    assert "cycle" in str(e.value)
    assert "{b}" in str(e.value) and "{a}" in str(e.value)


def test_a_self_cycle_through_a_sibling_is_akan():
    akan('a:\n  x: y"{y}"\n  y: y"{x}"\n', "cycle")


def test_missing_reference_is_akan_at_the_hole():
    with pytest.raises(AkanError) as e:
        load('a: "A"\nb: y"{nope}"\n')
    assert "no value named 'nope'" in str(e.value)
    assert (e.value.line, e.value.col) == (2, 3)


def test_depth_cap_is_enforced_and_overridable():
    doc = 'a0: "x"\n' + "".join(f'a{i}: y"{{a{i - 1}}}"\n' for i in range(1, 8))
    assert load(doc).by_key["a7"].value == "x"          # fits the default
    akan(doc, "depth cap", max_depth=3)


def test_size_cap_is_enforced_and_overridable():
    akan('a: "0123456789"\nb: y"{a}{a}{a}"\n', "rendered-size cap", max_size=8)


# --------------------------------------------------------------------------- #
# SPEC §5.4 — the lexeme rule
# --------------------------------------------------------------------------- #
def test_float_splices_its_lexeme_not_its_value():
    assert val('version: 3.10\nb: y"v{version}"\n', "b") == "v3.10"


def test_int_spellings_splice_as_written():
    node = load('m: 0xFF\nk: 1_000\na: y"{m}"\nb: y"{k}"\n')
    assert node.by_key["a"].value == "0xFF"
    assert node.by_key["b"].value == "1_000"


def test_keywords_splice_as_themselves():
    node = load('t: True\nn: None\na: y"{t}/{n}"\n')
    assert node.by_key["a"].value == "True/None"


def test_strings_splice_their_content_not_their_lexeme():
    assert val('s: "a\\tb"\nu: y"[{s}]"\n', "u") == "[a\tb]"


def test_a_resolved_result_is_inert():
    # the spliced-in text is never rescanned for holes
    node = load('brace: "{x}"\nu: y"{brace}"\nx: "NOPE"\n')
    assert node.by_key["u"].value == "{x}"


def test_brace_escapes_survive_resolution():
    assert val('u: y"{{literal}}"\n', "u") == "{literal}"


# --------------------------------------------------------------------------- #
# SPEC §5.5 — the splice matrix
# --------------------------------------------------------------------------- #
def test_y_takes_str_content():
    assert val('s: "S"\nu: y"{s}"\n', "u") == "S"


def test_y_rejects_b_spelled_bytes_and_names_the_fix():
    akan('p: b"\\x89"\nu: y"{p}"\n', "respell as b64")
    akan('p: rb"\\d"\nu: y"{p}"\n', "respell as b64")


def test_y_takes_b64_bytes_as_base64_text():
    assert val('p: b64"aGVsbG8="\nu: y"{p}"\n', "u") == "aGVsbG8="


def test_y_rejects_containers():
    akan('c: [1, 2]\nu: y"{c}"\n', "cannot interpolate")
    akan('c: {a: 1}\nu: y"{c}"\n', "cannot interpolate")


def test_y_rejects_templates():
    akan('t: yt"Hi {user}"\nu: y"{t}"\n', "cannot splice a template")


def test_yb_takes_bytes_from_either_spelling():
    node = load('p: b"AB"\nq: b64"Q0Q="\nu: yb"{p}{q}"\n')
    assert node.by_key["u"].value == b"ABCD"
    assert node.by_key["u"].type == "bytes"


def test_yb_rejects_text_with_no_implicit_encode():
    akan('s: "S"\nu: yb"{s}"\n', "no implicit encode")


def test_yb_takes_the_ascii_lexeme_of_a_number():
    assert val('port: 8080\nu: yb"*{port}\\r\\n"\n', "u") == b"*8080\r\n"


def test_ry_keeps_backslashes_and_live_holes():
    assert val('n: "gw"\np: ry"^{n}-\\d+$"\n', "p") == "^gw-\\d+$"


def test_yt_is_left_unresolved():
    node = load('user: "nobody"\nt: yt"Hi {user}"\n')
    t = node.by_key["t"]
    assert isinstance(t, YString) and t.prefix == "yt"
    assert t.parts == [("text", "Hi "), ("hole", "user")]


def test_a_resolved_y_string_is_a_plain_str_scalar():
    node = load('a: "A"\nb: y"{a}!"\n')
    b = node.by_key["b"]
    assert isinstance(b, Scalar) and b.type == "str" and b.prefix == ""


def test_a_resolved_yb_string_has_no_text_form():
    # its result is b-spelled bytes, so splicing it into text still akans
    akan('p: b"AB"\nq: yb"{p}"\nu: y"{q}"\n', "respell as b64")


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #
def test_the_example_document_resolves():
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "examples" / "gateway.ypy").read_text()
    node = resolve(parse(src))
    paths = node.by_key["paths"]
    assert paths.by_key["logs"].value == "/srv/gateway/logs"
    assert paths.by_key["banner"].value == "api-gateway v3.10"   # not 3.1
    assert paths.by_key["pattern"].value == "^api-gateway-\\d+$"
    assert node.by_key["magic"].by_key["frame"].value == b"*8080\r\n"
    assert isinstance(node.by_key["changes"], MultiMap)
