"""SPEC §5.6, GRAMMAR §G4.8: `(ref)` is a copy of the value `ref` names.

Asked for by persona_grata (2026-10-23): a list a harness declares should be
able to point at a list defined elsewhere, kept typed. Rulings (operator,
2026-10-23; `workbook/designs/whole-value-copies.md`): spelled `(bar)`;
copy, not alias (linearity); resolved, then copied; literals in parentheses
only group; whitespace inside is layout; records admit no parentheses, and a
document using them is a ledger.
"""

import pytest

from yapyon import (AkanError, OrderedMultimap, Template, expand_record,
                    loads, loads_contract, loads_record, tier_of)


def test_a_copy_keeps_the_type():
    d = loads('wanted: ["responses", "chat"]\nsd: (wanted)\n')
    assert d["sd"] == ["responses", "chat"]
    d = loads("m: {a: 1, b: [2]}\nc: (m)\n")
    assert d["c"] == {"a": 1, "b": [2]}


def test_a_copy_uses_the_holes_lookup():
    text = ('mind:\n  dialects:\n    codex: {api: "responses"}\n'
            '  protocol: "codex"\n  chosen: (dialects[protocol])\n'
            'top: (__ROOT__.mind.protocol)\n'
            'deep: (mind.dialects["codex"].api)\n')
    d = loads(text)
    assert d["mind"]["chosen"] == {"api": "responses"}
    assert d["top"] == "codex" and d["deep"] == "responses"


def test_a_copy_of_a_key_or_a_variable_is_a_string():
    assert loads("k:\n  v: (__KEY__)\n") == {"k": {"v": "v"}}
    assert loads("k:\n  v: (__PARENT__.__KEY__)\n") == {"k": {"v": "k"}}
    assert loads("h: ($HOME)\n", env={"HOME": "/h"}) == {"h": "/h"}


def test_a_missing_target_is_akan_as_in_a_hole():
    with pytest.raises(AkanError, match="no value named 'nope'"):
        loads("a: (nope)\n")


def test_a_copy_is_not_the_same_object():
    d = loads('wanted: ["chat"]\nsd: (wanted)\n')
    assert d["sd"] is not d["wanted"]
    d["sd"].append("x")
    assert d["wanted"] == ["chat"]


def test_a_copy_is_deep():
    d = loads("m: {xs: [[1]]}\nc: (m)\n")
    assert d["c"]["xs"][0] is not d["m"]["xs"][0]


def test_resolved_where_written_then_copied():
    text = ('host: "example.com"\n'
            'base:\n  name: y"{__PARENT__.__KEY__}"\n'
            '  url: y"https://{host}/{name}"\n'
            'sites:\n  host: "elsewhere.org"\n  prod: (base)\n')
    d = loads(text)
    assert d["sites"]["prod"] == {"name": "base",
                                  "url": "https://example.com/base"}


@pytest.mark.parametrize("text", [
    'c: (b)\nb: y"{a}!"\na: "x"\n',             # the copy written first
    'a: "x"\nb: y"{a}!"\nc: (b)\n',
])
def test_a_copy_waits_for_its_value(text):
    assert loads(text)["c"] == "x!"


def test_copies_chain_and_are_read_through():
    d = loads('x: (b.c)\nb:\n  c: (a)\na: [1]\ny: y"{b.c[0]}"\n')
    assert d["x"] == [1] and d["y"] == "1"


def test_a_copy_of_a_multimap_view_is_a_list():
    d = loads("mm:\n  + k: 1\n  + k: 2\nv: (mm.k)\nw: (mm)\n")
    assert d["v"] == [1, 2]
    assert isinstance(d["w"], OrderedMultimap) and d["w"] == d["mm"]


def test_a_copy_of_a_template_is_a_template():
    d = loads('a: (b)\nb: yt"q{c}"\nc: 1\n')
    assert isinstance(d["a"], Template) and d["a"].render() == "q1"


def test_a_copy_keeps_lexemes():
    assert expand_record("a: (b)\nb: 0xff\n") == "a: 0xff\nb: 0xff\n"
    d = loads('b: 0xff\na: (b)\nj: y"{a.__AS_JSON__()}"\n')
    assert d["j"] == loads('b: 0xff\nj: y"{b.__AS_JSON__()}"\n')["j"]


@pytest.mark.parametrize("text", [
    "a: (b)\nb: (a)\n",
    "a: [1, (__ROOT__.a)]\n",
    "a:\n  b: (__PARENT__)\n",
    "a: (__ROOT__)\n",
])
def test_a_copy_cannot_contain_itself(text):
    with pytest.raises(AkanError):
        loads(text)


def test_a_builtins_result_can_be_copied():
    d = loads("b: {x: 1}\na: (b.__AS_JSON__())\n")
    assert d["a"] == '{"x": 1}'
    d = loads('a: (__ENV__("X"))\nb: (__ENV__("X", fallback=c))\nc: [1]\n',
              env={})
    assert d["a"] is None and d["b"] == [1]           # typed, not "None"


PAIRS = """
pairs:
  params:
    n: "int"
  returns: "list[dict[str, int]]"
  impl:
    python:
      symbol: "pairs"
"""


def test_a_declared_functions_result_can_be_copied():
    shared = [{"a": 1}]
    d = loads("x: (pairs(2))\ny: (pairs(n=1))\n",
              contract=loads_contract(PAIRS),
              provide={"pairs": lambda n: shared * n})
    assert d["x"] == [{"a": 1}, {"a": 1}] and d["y"] == [{"a": 1}]
    assert d["x"][0] is not d["x"][1] and d["x"][0] is not shared[0]
    assert tier_of("x: (pairs(2))\n") == 4


def test_a_call_in_a_copy_waits_for_its_arguments():
    d = loads('a: (b.__AS_JSON__())\nb: {x: y"{c}"}\nc: "z"\n')
    assert d["a"] == '{"x": "z"}'


@pytest.mark.parametrize("text,value", [
    ("a: (1)\n", 1), ('a: ("x")\n', "x"), ("a: (True)\n", True),
    ("a: (None)\n", None), ('a: (b"x")\n', b"x"), ('a: (y"z")\n', "z"),
    ("a: ([1, 2])\n", [1, 2]), ("a: ((1))\n", 1), ("a: (-1)\n", -1),
])
def test_parentheses_around_a_literal_only_group(text, value):
    assert loads(text)["a"] == value


@pytest.mark.parametrize("text", [
    "a: ( b )\nb: 1\n", "a: ( b . c )\nb: {c: 1}\n", "a: (\n  b\n)\nb: 1\n",
    "a: ( 1 )\n", "a: [(b),\n  (b)]\nb: 1\n",
])
def test_whitespace_inside_is_layout(text):
    loads(text)


@pytest.mark.parametrize("text,why", [
    ("a: ()\n", "tuple"), ("a: (1,)\n", "tuple"), ("a: (1, 2)\n", "tuple"),
    ("a: (x,)\nx: 1\n", "tuple"), ("a: 1)\n", "unmatched"),
    ("a: (b\n", "unclosed"), ("(a): 1\n", "not a valid key"),
])
def test_what_parentheses_refuse(text, why):
    with pytest.raises(AkanError, match=why):
        loads(text)


def test_copies_stand_wherever_a_value_does():
    d = loads("b: 2\nl: [(b)]\nm: {x: (b)}\ns:\n  - (b)\nmm:\n  + k: (b)\n")
    assert d["l"] == [2] and d["m"] == {"x": 2} and d["s"] == [2]
    assert list(d["mm"])[0].value == 2


@pytest.mark.parametrize("text,what", [
    ("a: (1)\n", "no parentheses"), ("a: (b)\nb: 1\n", "a copy"),
])
def test_a_record_admits_no_parentheses(text, what):
    with pytest.raises(AkanError, match=what):
        loads_record(text)


@pytest.mark.parametrize("text,tier", [
    ("a: (1)\n", 2), ("a: (b)\nb: 1\n", 2),
    ("a: ($HOME)\n", 3), ("a: (b)\nb: yt\"x\"\n", 3),
])
def test_the_tier(text, tier):
    assert tier_of(text) == tier


def test_expand_writes_the_value():
    assert (expand_record('a: (1)\nb: (c)\nc: [1, "s"]\n')
            == 'a: 1\nb: [1, "s"]\nc: [1, "s"]\n')


def test_copies_meet_the_size_ceiling():
    lines = ["a0: [1, 2, 3, 4, 5, 6, 7, 8]"]
    lines += [f"a{i}: [(a{i - 1}), (a{i - 1})]" for i in range(1, 12)]
    with pytest.raises(AkanError, match="rendered-size ceiling"):
        loads("\n".join(lines) + "\n", max_size=10_000)


def test_copies_meet_the_depth_ceiling():
    lines = ["a0: 1"] + [f"a{i}: (a{i - 1})" for i in range(1, 10)]
    with pytest.raises(AkanError, match="depth ceiling"):
        loads("\n".join(lines) + "\n", max_depth=5)
