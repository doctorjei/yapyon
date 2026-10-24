"""GRAMMAR §G6, SPEC §7.1: `{+}` is the empty multimap; `{}` stays a mapping.

Operator, 2026-10-19: "I think it's OK to load {} as a map. We should have a
way to recognize that as an empty multimap", then `{+}` over `<>` — "I don't
want to change the flow form" (§9 reserves `{+ a: 1, + a: 2}`). Three
tokens, so whitespace between them is layout, as in `{ }`.
"""

import pytest

from yapyon import (AkanError, OrderedMultimap, emit, expand_record, loads, loads_record, tier_of)
from yapyon.parser import parse


@pytest.mark.parametrize("text", ["{+}", "{ + }", "{+\n}", "{\n  +\n}"])
def test_the_empty_multimap(text):
    value = loads(f"a: {text}\n")["a"]
    assert isinstance(value, OrderedMultimap) and len(value) == 0


def test_an_empty_mapping_is_still_a_mapping():
    assert loads("a: {}\n")["a"] == {} and isinstance(loads("a: {}\n")["a"], dict)
    assert loads("a: {+}\n")["a"] != loads("a: {}\n")["a"]   # §7.1: never equal


def test_it_stands_wherever_a_value_does():
    d = loads("{+}\n")
    assert isinstance(d, OrderedMultimap)
    d = loads("xs: [{+}, {}]\nmm:\n  + k: {+}\n")
    assert isinstance(d["xs"][0], OrderedMultimap) and d["xs"][1] == {}
    assert isinstance(list(d["mm"])[0].value, OrderedMultimap)


def test_it_is_a_record():
    assert tier_of("a: {+}\n") == 1
    assert isinstance(loads_record("a: {+}\n")["a"], OrderedMultimap)


@pytest.mark.parametrize("text,written", [
    ("a: { + }\n", "a: {+}\n"),            # the writer's one spelling
    ("{+}\n", "{+}\n"),                    # at the root too
    ("mm:\n  + k: {+}\n", "mm:\n  + k: {+}\n"),
])
def test_writers_spell_it_back(text, written):
    assert emit(parse(text)) == written
    assert expand_record(text) == written
    assert loads_record(written) == loads_record(text)


def test_as_yapyon_and_the_other_serializers():
    d = loads("e: {+}\nj: y\"{e.__as_json__()}\"\nt: y\"{x.__as_toml__()}\"\n"
              "y: y\"{e.__as_yaml__()}\"\np: y\"{e.__as_yapyon__()}\"\n"
              "x:\n  e: {+}\n")
    assert d["p"] == "{+}\n"
    assert d["j"] == '{"@type": "multimap", "entries": {"@list": []}}'
    assert d["t"] == 'e."@type" = "multimap"\ne.entries = []\n'
    assert d["y"].endswith("!multimap!pairs []\n")


@pytest.mark.parametrize("text,needle", [
    ("a: {+ k: 1}\n", "a flow multimap with entries is reserved"),
    ("a: {+ +}\n", "a flow multimap with entries is reserved"),
    ("a: {k: 1, +}\n", "found a multimap's '+'"),
    ("a: [+]\n", ""),                      # only directly inside braces
    ("a: +\n", "opens a block frame"),
])
def test_what_is_not_the_empty_multimap(text, needle):
    with pytest.raises(AkanError) as e:
        loads(text)
    assert needle in str(e.value)


def test_a_signed_number_inside_braces_is_still_a_number():
    assert loads("a: {b: +1, c: -2}\n")["a"] == {"b": 1, "c": -2}
