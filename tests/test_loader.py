"""Loader and Template tests — one test per spec rule, named after the rule.

When a test and the implementation disagree, check the spec before changing
either.
"""

import io
from pathlib import Path

import pytest

import yapyon
from yapyon import AkanError, OrderedMultimap, Template, load, loads

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "gateway.ypy"


def akan(text, needle=""):
    with pytest.raises(AkanError) as e:
        loads(text)
    assert needle in str(e.value), f"wrong message: {e.value}"


# --------------------------------------------------------------------------- #
# The everyday API
# --------------------------------------------------------------------------- #
def test_loads_gives_plain_python():
    assert loads('a: "x"\nb: 1\nc: 3.10\nd: True\ne: None\n') == {
        "a": "x", "b": 1, "c": 3.1, "d": True, "e": None}


def test_key_order_is_preserved():
    assert list(loads("b: 1\na: 2\nc: 3\n")) == ["b", "a", "c"]


def test_containers_load_as_dict_and_list():
    doc = loads('m:\n  k: "v"\nxs: [1, 2]\nys:\n  - "a"\n  - "b"\n')
    assert doc == {"m": {"k": "v"}, "xs": [1, 2], "ys": ["a", "b"]}


def test_bytes_load_as_bytes():
    doc = loads('a: b"\\x89PNG"\nb: b64"aGVsbG8="\n')
    assert doc == {"a": b"\x89PNG", "b": b"hello"}


def test_y_strings_are_already_resolved():
    assert loads('root: "/srv"\nlogs: y"{root}/logs"\n')["logs"] == "/srv/logs"


def test_load_reads_a_file_object():
    assert load(io.StringIO('a: "x"\n')) == {"a": "x"}


def test_load_reads_the_example_document():
    with EXAMPLE.open() as fp:
        doc = load(fp)
    assert doc["paths"]["banner"] == "api-gateway v3.10"
    assert doc["magic"]["frame"] == b"*8080\r\n"


def test_warn_receives_shiran():
    # the vehicle is the avoidable-bracket shiran; shadowing is silent
    seen = []
    loads('a:\n  bar: "X"\nu: y"{a[\'bar\']}"\n', warn=seen.append)
    assert len(seen) == 1 and seen[0].startswith("shiran:")


def test_caps_are_loader_overridable():
    doc = 'a: "0123456789"\nb: y"{a}{a}"\n'
    assert loads(doc)["b"] == "01234567890123456789"
    with pytest.raises(AkanError):
        loads(doc, max_size=8)


# --------------------------------------------------------------------------- #
# SPEC §7.1 — a multimap loads as OrderedMultimap
# --------------------------------------------------------------------------- #
def test_multimap_loads_as_an_ordered_multimap():
    doc = loads('changes:\n  + registry: "set"\n  + file: "delete"\n'
                '  + registry: "remove"\n')
    mm = doc["changes"]
    assert isinstance(mm, OrderedMultimap)
    assert [(k, v) for k, v in mm] == [
        ("registry", "set"), ("file", "delete"), ("registry", "remove")]
    assert mm.grouped() == {"registry": ("set", "remove"),
                            "file": ("delete",)}


def test_a_loaded_multimap_reprs_its_timeline():
    mm = loads('m:\n  + a: 1\n  + b: 2\n  + a: 3\n')["m"]
    assert repr(mm) == "OrderedMultimap([('a', 1), ('b', 2), ('a', 3)])"


def test_multimaps_are_equal_iff_their_entry_sequences_are():
    text = 'm:\n  + a: 1\n  + b: 2\n  + a: 3\n'
    assert loads(text)["m"] == loads(text)["m"]
    assert loads(text)["m"] != loads('m:\n  + a: 1\n  + a: 3\n  + b: 2\n')["m"]


def test_a_multimap_is_never_equal_to_a_mapping():
    # even when its keys happen to be unique (§7.1)
    mm = loads('m:\n  + a: 1\n')["m"]
    assert mm != {"a": 1} and {"a": 1} != mm


def test_multimap_entry_values_are_built_too():
    mm = loads('m:\n  + a:\n      k: [1, 2]\n')["m"]
    assert mm["a"].values() == ({"k": [1, 2]},)


# --------------------------------------------------------------------------- #
# SPEC §6 — yt is a y-string that is not joined
# --------------------------------------------------------------------------- #
def test_yt_resolves_against_the_document_like_y_does():
    # the difference between y and yt is the join, not the scope
    d = loads('user: "nobody"\ny: y"Hi {user}"\nt: yt"Hi {user}"\n')
    assert d["y"] == "Hi nobody"
    assert d["t"].values == ("nobody",)
    assert d["t"].render() == "Hi nobody"


def test_a_template_keeps_the_parts_apart():
    t = loads('who: "bob"\nn: 3\ng: yt"Hello {who}, {n} new"\n')["g"]
    assert isinstance(t, Template)
    assert t.strings == ("Hello ", ", ", " new")
    assert t.values == ("bob", 3)
    assert tuple(h.ref for h in t.holes) == ("who", "n")


def test_the_alternation_is_total():
    # str first and last, an empty one between adjacent holes -- so a consumer
    # never special-cases a leading, trailing or doubled hole
    t = loads('a: "A"\nb: "B"\nt: yt"{a}{b}"\n')["t"]
    assert t.strings == ("", "", "")
    assert len(t.strings) == len(t.holes) + 1
    assert [type(p).__name__ for p in t] == ["str", "Hole", "str", "Hole",
                                             "str"]


def test_iterating_alternates_text_and_holes():
    # the isinstance check is how a processor tells author bytes from data
    t = loads('x: "v"\nt: yt"a{x}b"\n')["t"]
    assert [p if isinstance(p, str) else p.value for p in t] == ["a", "v", "b"]


def test_a_hole_carries_the_lexeme_so_rendering_stays_faithful():
    # §5.4: 3.10 is the float 3.1, and only the lexeme can render it back
    t = loads('v: 3.10\nt: yt"v{v}"\n')["t"]
    hole = t.holes[0]
    assert hole.value == 3.1 and hole.lexeme == "3.10"
    assert t.render() == "v3.10"


def test_a_hole_keeps_the_reference_as_written():
    t = loads('d:\n  k: "v"\nt: yt"{d[\'k\']}"\n')["t"]
    assert t.holes[0].ref == "d['k']"


def test_carrying_is_unconstrained_where_rendering_is_not():
    # yapyon does not render, so a hole may carry anything a document holds;
    # §5.5 governs render() alone
    t = loads('raw: b"\\x89PNG"\nxs: [1, 2]\nt: yt"{raw}{xs}"\n')["t"]
    assert t.values == (b"\x89PNG", [1, 2])
    with pytest.raises(AkanError) as e:
        t.render()
    assert "b-spelled bytes have no text form" in str(e.value)


def test_b64_bytes_render_as_base64_exactly_as_in_a_y_string():
    d = loads('q: b64"aGk="\ny: y"x{q}y"\nt: yt"x{q}y"\n')
    assert d["t"].render() == d["y"] == "xaGk=y"


def test_an_unbound_hole_is_akan_at_parse_not_at_render():
    # law 7: the mistake is in the document, so it lands on the author
    with pytest.raises(AkanError) as e:
        loads('t: yt"Hi {nobody}"\n')
    assert "no value named 'nobody' is in scope here" in str(e.value)


def test_a_template_cannot_be_spliced_into_a_string():
    # joining one would throw away the parts it exists to preserve
    with pytest.raises(AkanError) as e:
        loads('x: "v"\nt: yt"{x}"\ny: y"{t}"\n')
    assert "cannot splice a template into a string" in str(e.value)


def test_there_is_no_implicit_rendering():
    # an implicit join is the footgun the parts exist to remove
    t = loads('x: "v"\nt: yt"a{x}"\n')["t"]
    assert "av" not in str(t)
    assert not hasattr(t, "fill")


def test_templates_compare_by_parts():
    assert loads('b: "B"\nt: yt"a{b}"\n')["t"] == loads(
        'b: "B"\nt: yt"a{b}"\n')["t"]
    assert loads('b: "B"\nt: yt"a{b}"\n')["t"] != loads(
        'b: "C"\nt: yt"a{b}"\n')["t"]



# --------------------------------------------------------------------------- #
# Errors still carry positions through the whole pipeline
# --------------------------------------------------------------------------- #
def test_a_parse_error_survives_the_loader():
    akan("a: no\n", 'write False for the value or "no" for the string')


def test_a_resolution_error_survives_the_loader():
    akan('a: y"{nope}"\n', "no value named 'nope'")


def test_the_package_exposes_the_everyday_api():
    for name in ("load", "loads", "build", "Template", "OrderedMultimap"):
        assert name in yapyon.__all__ and hasattr(yapyon, name)
