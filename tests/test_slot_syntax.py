"""GRAMMAR §G4.9, §G6, §G7 and SPEC §15: how a slot is written.

`key<label>: {overrides}` makes the key's value a slot — a value its
consumer fills (operator, 2026-10-23; `workbook/designs/tree-assembly.md`).
These tests cover reading one; filling and merging are in
`test_slots.py`.
"""

import pytest

from yapyon import AkanError, is_record, loads, loads_record, tier_of
from yapyon.parser import Mapping, Slot, parse


def slot_at(text, *path):
    node = parse(text)
    for key in path:
        node = node.by_key[key]
    return node


def test_a_label_makes_the_value_a_slot():
    slot = slot_at('persona<llamacpp>:\n  mind:\n    endpoint: "e"\n',
                   "persona")
    assert isinstance(slot, Slot)
    assert slot.label == ("llamacpp",) and slot.lexeme == "<llamacpp>"
    assert not slot.abstract
    [overrides] = slot.layers
    assert isinstance(overrides, Mapping)
    assert overrides.by_key["mind"].by_key["endpoint"].value == "e"


def test_an_empty_label_is_abstract():
    slot = slot_at("harness<>: {}\n", "harness")
    assert slot.abstract and slot.label == ()


def test_a_label_may_reach_into_its_filler():
    assert slot_at("agent<base.agent>: {}\n", "agent").label == (
        "base", "agent")


@pytest.mark.parametrize("text", [
    "p<a.b>: {}\n", "p <a.b>: {}\n", "p\t<a.b>: {}\n", "p< a . b >: {}\n",
    "p<\n  a . b\n>: {}\n", "x: {p <a.b>: {}}\n", "x: {\n  p\n  <a.b>: {}}\n",
])
def test_whitespace_is_free(text):
    node = parse(text)
    if "x" in node.by_key:
        node = node.by_key["x"]
    assert node.by_key["p"].label == ("a", "b")


def test_a_newline_before_the_label_is_layout_outside_brackets():
    with pytest.raises(AkanError):
        parse("p\n<a>: {}\n")


def test_labels_are_compared_as_names():
    assert slot_at("p<ｃｌａｕｄｅ>: {}\n", "p").label == ("claude",)


def test_the_label_keeps_its_spelling():
    assert slot_at("p< a . b >: {}\n", "p").lexeme == "< a . b >"


def test_a_slot_stands_in_a_flow_map():
    slot = slot_at("x: {p<a>: {b: 1}}\n", "x", "p")
    assert slot.label == ("a",)


@pytest.mark.parametrize("text", [
    "p<a>: 1\n", 'p<a>: "s"\n', "p<a>: [1]\n", "p<a>: {+}\n",
    "p<a>:\n  - 1\n", "p<a>:\n  + k: 1\n", "p<a>: None\n",
])
def test_overrides_must_be_a_mapping(text):
    with pytest.raises(AkanError, match="overrides, a mapping"):
        parse(text)


def test_no_value_is_still_akan():
    with pytest.raises(AkanError, match="has no value"):
        parse("p<a>:\n")


@pytest.mark.parametrize("text,match", [
    ("p<True>: {}\n", "keyword"),
    ("p<__x__>: {}\n", "dunder"),
    ("p<a..b>: {}\n", "one is missing"),
    ("p<a.>: {}\n", "one is missing"),
    ("p<1a>: {}\n", "not a label name"),
    ("p<a b>: {}\n", "not a label name"),
    ("p<a: {}\n", "unclosed '<'"),
    ('p<a: {}\nq: ">"\n', "unclosed '<'"),
])
def test_bad_labels(text, match):
    with pytest.raises(AkanError, match=match):
        parse(text)


@pytest.mark.parametrize("text", [
    "a: 1 < 2\n", "a: [<b>]\n", "<a>: {}\n", "p<a><b>: {}\n",
])
def test_a_stray_angle_bracket_is_akan(text):
    with pytest.raises(AkanError):
        parse(text)


def test_a_label_on_a_value_word_is_still_a_bare_word():
    with pytest.raises(AkanError, match="bare word"):
        parse("a: b<c>\n")


def test_no_slot_in_a_multimap_entry():
    with pytest.raises(AkanError, match="reserved"):
        parse("m:\n  + k<a>: {}\n")


def test_keys_beside_a_slot_follow_the_usual_rules():
    with pytest.raises(AkanError, match="duplicate key"):
        parse("p<a>: {}\np: 1\n")
    with pytest.raises(AkanError, match="dunder"):
        parse("__p__<a>: {}\n")


def test_an_unfilled_slot_is_akan_when_resolving():
    with pytest.raises(AkanError, match=r"p<llamacpp>: this slot is unfilled"):
        loads("x: 1\np<llamacpp>: {}\n")
    with pytest.raises(AkanError, match=r"h<>: this abstract slot"):
        loads("h<>: {}\n")


def test_a_slot_makes_a_template():
    assert tier_of("p<a>: {}\n") == 3
    assert not is_record("p<a>: {}\n")
    with pytest.raises(AkanError, match="holds no slots"):
        loads_record("p<a>: {}\n")
