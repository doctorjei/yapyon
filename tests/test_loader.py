"""Loader and Template tests — one test per spec rule, named after the rule.

When a test and the implementation disagree, check SPEC.md before changing
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
    seen = []
    loads('x: "outer"\nb:\n  x: "inner"\n  v: y"{x}"\n', warn=seen.append)
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


def test_multimap_entry_values_are_built_too():
    mm = loads('m:\n  + a:\n      k: [1, 2]\n')["m"]
    assert mm["a"].values() == ({"k": [1, 2]},)


# --------------------------------------------------------------------------- #
# SPEC §6 — yt produces a Template, unfilled
# --------------------------------------------------------------------------- #
def test_yt_loads_as_a_template_with_its_parts():
    t = loads('greeting: yt"Hello {user}, {count} new"\n')["greeting"]
    assert isinstance(t, Template)
    assert t.parts == [("text", "Hello "), ("hole", "user"),
                       ("text", ", "), ("hole", "count"), ("text", " new")]
    assert t.holes == ("user", "count")


def test_a_template_is_not_filled_by_the_document():
    # `user` exists in the document and must still be ignored (§6)
    t = loads('user: "nobody"\nt: yt"Hi {user}"\n')["t"]
    assert t.fill(user="someone") == "Hi someone"


def test_fill_takes_a_mapping_or_keywords():
    t = loads('t: yt"{a}-{b}"\n')["t"]
    assert t.fill({"a": "x", "b": "y"}) == "x-y"
    assert t.fill(a="x", b="y") == "x-y"


def test_str_fills_verbatim():
    assert loads('t: yt"[{s}]"\n')["t"].fill(s="a b\tc") == "[a b\tc]"


def test_int_bool_and_none_fill_as_canonical_spellings():
    t = loads('t: yt"{i}/{b}/{n}"\n')["t"]
    assert t.fill(i=8080, b=True, n=None) == "8080/True/None"


def test_bool_fills_as_a_bool_not_as_an_int():
    # bool subclasses int; the order of the checks is the rule
    assert loads('t: yt"{b}"\n')["t"].fill(b=False) == "False"


def test_float_fills_as_shortest_round_trip():
    t = loads('t: yt"{f}"\n')["t"]
    assert t.fill(f=3.10) == "3.1"          # not the lexeme rule (§5.4)
    assert t.fill(f=0.1 + 0.2) == "0.30000000000000004"


def test_bytes_fill_as_standard_base64():
    assert loads('t: yt"{b}"\n')["t"].fill(b=b"hello") == "aGVsbG8="


def test_unbound_hole_is_akan_at_fill():
    t = loads('t: yt"Hi {user}"\n')["t"]
    with pytest.raises(AkanError) as e:
        t.fill(other="x")
    assert "unbound hole {user}" in str(e.value)
    assert (e.value.line, e.value.col) == (1, 3)   # where the yt literal sits


def test_containers_cannot_fill_a_hole():
    t = loads('t: yt"{c}"\n')["t"]
    with pytest.raises(AkanError) as e:
        t.fill(c=[1, 2])
    assert "cannot fill {c} with a list" in str(e.value)


def test_dotted_holes_traverse_the_supplied_scope():
    t = loads('t: yt"{s.host}"\n')["t"]
    assert t.fill(s={"host": "h"}) == "h"


def test_dotted_hole_into_a_non_mapping_is_akan():
    with pytest.raises(AkanError) as e:
        loads('t: yt"{s.host}"\n')["t"].fill(s="plain")
    assert "is not a mapping" in str(e.value)


def test_root_is_meaningless_in_a_template():
    with pytest.raises(AkanError) as e:
        loads('t: yt"{__ROOT__.x}"\n')["t"].fill(x="y")
    assert "a template has none" in str(e.value)


def test_templates_compare_by_parts():
    assert loads('t: yt"a{b}"\n')["t"] == Template(
        [("text", "a"), ("hole", "b")])


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
