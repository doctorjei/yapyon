"""SPEC §13.1, GRAMMAR §G5: `?.` — a call that a `None` receiver skips.

Operator, 2026-10-24: the `None` passthrough is explicit syntax rather than
a property of each caster; without `?.`, `None` reaching a caster is akan.
A `None` before `?.` ends the whole chain as `None`, as JavaScript, C#, and
Swift do.
"""

import re

import pytest

from yapyon import AkanError, loads
from yapyon.lexer import parse_ref

EMPTY = 'persona:\n  mind:\n    model_list: []\n'


def value(expr, doc=EMPTY):
    return loads(doc + f"out: ({expr})\n")["out"]


def test_none_before_a_safe_call_is_none():
    assert value("persona.mind.model_list.__get__(0)?.__str__()") is None


def test_the_whole_rest_of_the_chain_is_skipped():
    assert value("persona.mind.model_list.__get__(0)?.__str__()"
                 ".__as_json__()") is None


def test_a_value_passes_through_as_an_ordinary_call():
    doc = 'xs: ["m"]\n'
    assert value("xs.__get__(0)?.__str__()", doc) == "m"
    assert value("xs?.__get__(0)", doc) == "m"


def test_without_the_question_mark_none_is_akan():
    with pytest.raises(AkanError, match="cannot take None"):
        value("persona.mind.model_list.__get__(0).__str__()")


def test_a_skipped_chain_splices_as_none():
    out = loads(EMPTY + 'u: y"[{persona.mind.model_list.__get__(0)?.'
                        '__str__()}]"\n')["u"]
    assert out == "[None]"


def test_a_skipped_argument_stops_at_its_own_chain():
    doc = 'n: None\n'
    assert value('__as_json__(n?.__str__())', doc) == "null"


def test_an_environment_receiver_may_be_safe():
    assert loads('h: ($HOME?.__str__())\n', env={"HOME": "/h"}) == {"h": "/h"}


@pytest.mark.parametrize("ref", ["a?.f()", "a ?. f()", "a.b?.f().g()",
                                 "f(x)?.g()", "$HOME?.f()"])
def test_safe_calls_parse(ref):
    parse_ref(ref)


@pytest.mark.parametrize("ref,why", [
    ("a?.b", "only before a call"), ("a?[0]", "part of '?.'"),
    ("a?f()", "part of '?.'"), ("a?", "part of '?.'"),
    ("a? .f()", "part of '?.'"), ("__ROOT__?.f()", "contains this hole"),
])
def test_question_mark_only_as_part_of_a_safe_call(ref, why):
    with pytest.raises(ValueError, match=re.escape(why)):
        parse_ref(ref)
