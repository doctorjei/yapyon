"""SPEC §15.2–§15.6: filling slots.

The meaning of any assembly of fills and merges is that of filling to
literal, merging, and repeating (operator, 2026-10-23: "fill-to-literal,
merge, wash rinse repeat"). The last part of this file is persona_grata's
templates (their letters of 2026-10-23, c and d), redrafted on slots.
"""

import itertools

import pytest

from yapyon import AkanError, merge, parse


# --------------------------------------------------------------------------- #
# Filling
# --------------------------------------------------------------------------- #
def test_a_fill_is_the_filler_under_the_overrides():
    tree = parse('persona<llamacpp>:\n  mind:\n    endpoint: "local"\n')
    llamacpp = parse('name: "llamacpp"\nmind:\n  endpoint: "remote"\n'
                     '  model: "q4"\n')
    tree["persona"].fill(llamacpp)
    assert tree.resolve() == {"persona": {
        "name": "llamacpp", "mind": {"endpoint": "local", "model": "q4"}}}


def test_empty_overrides_leave_the_filler_as_it_is():
    tree = parse("harness<claude>: {}\n")
    tree["harness"].fill(parse('"just a string"'))
    assert tree.resolve() == {"harness": "just a string"}


def test_one_filler_may_fill_many_slots_each_its_own():
    tree = parse("a<x>: {n: 1}\nb<x>: {n: 2}\n")
    x = parse("n: 0\nm: 0\n")
    tree["a"].fill(x)
    tree["b"].fill(x)
    assert tree.resolve() == {"a": {"n": 1, "m": 0}, "b": {"n": 2, "m": 0}}
    assert x.resolve() == {"n": 0, "m": 0}


def test_holes_in_a_filler_bind_where_it_lands():
    tree = parse('name: "local_ultron"\npersona<p>: {}\n')
    tree["persona"].fill(parse('desc: y"{name}"\n'))
    assert tree.resolve()["persona"]["desc"] == "local_ultron"


def test_overrides_may_hold_holes_too():
    tree = parse('who: "me"\np<x>:\n  hello: y"hi {who}"\n')
    tree["p"].fill(parse('hello: "default"\n'))
    assert tree.resolve()["p"]["hello"] == "hi me"


def test_only_a_slot_is_filled():
    tree = parse("a: {b: 1}\n")
    with pytest.raises(TypeError, match="not a slot"):
        tree["a"].fill(parse("c: 2\n"))


def test_slots_lists_what_is_left_to_fill():
    tree = parse("a<x>: {}\nb:\n  c<>: {}\n  d<y>: {e<z>: {}}\n")
    assert [h.path for h in tree.slots()] == [("a",), ("b", "c"), ("b", "d")]
    assert [h.label for h in tree.slots()] == [("x",), (), ("y",)]


def test_a_slot_reports_its_label_and_overrides():
    tree = parse("p<base.persona>:\n  mind: {model: \"m\"}\n")
    slot = tree["p"]
    assert slot.kind == "slot" and slot.label == ("base", "persona")
    assert slot.lexeme == "<base.persona>" and not slot.abstract
    assert slot.overrides.resolve() == {"mind": {"model": "m"}}


def test_an_unfilled_slot_is_akan_at_resolve():
    with pytest.raises(AkanError, match="p<x>: this slot is unfilled"):
        parse("p<x>: {}\n").resolve()


def test_a_filler_cannot_contain_its_slot():
    tree = parse("a:\n  b<x>: {}\n")
    with pytest.raises(AkanError, match="contains it"):
        tree["a"]["b"].fill(tree["a"])
    with pytest.raises(AkanError, match="tree that holds it"):
        tree["a"]["b"].fill(tree)


# --------------------------------------------------------------------------- #
# Labels reaching into the filler — SPEC §15.4
# --------------------------------------------------------------------------- #
BASE = parse('agent:\n  name: "agent_base"\n  path: "/p"\n')


def test_the_rest_of_the_label_is_followed_in_the_filler():
    tree = parse('agent<base.agent>:\n  name: "example"\n')
    tree["agent"].fill(BASE)
    assert tree.resolve() == {"agent": {"name": "example", "path": "/p"}}


def test_a_handle_is_used_as_it_is():
    tree = parse("agent<anything>: {}\n")
    tree["agent"].fill(BASE["agent"])
    assert tree.resolve() == {"agent": {"name": "agent_base", "path": "/p"}}


def test_a_path_the_filler_lacks_is_akan():
    tree = parse("agent<base.nope>: {}\n")
    with pytest.raises(AkanError, match="has no 'nope'"):
        tree["agent"].fill(BASE)


def test_a_path_ending_on_a_slot_moves_that_slot_in():
    example = parse('agent<base.agent>:\n  name: "example"\n')
    top = parse('agent<example.agent>:\n  path: "/top"\n')
    top["agent"].fill(example)
    moved = top["agent"]
    assert moved.kind == "slot" and moved.label == ("base", "agent")
    moved.fill(BASE)
    assert top.resolve() == {"agent": {"name": "example", "path": "/top"}}


def test_a_path_through_an_unfilled_slot_is_akan():
    example = parse('agent<base.agent>:\n  name: "example"\n')
    top = parse("agent<example.agent.name>: {}\n")
    with pytest.raises(AkanError, match="fill that one first"):
        top["agent"].fill(example)


def chain_results():
    """Every order of filling a three-document chain."""
    def build(order):
        top = parse('agent<example.agent>:\n  path: "/top"\n')
        example = parse('agent<base.agent>:\n  name: "example"\n')
        steps = {
            "example-first": lambda: example["agent"].fill(BASE),
            "top-first": lambda: top["agent"].fill(example),
        }
        for step in order:
            steps[step]()
        if top["agent"].kind == "slot":       # moved in: fill it in place
            top["agent"].fill(BASE)
        return top.resolve()
    return [build(order) for order in
            itertools.permutations(["example-first", "top-first"])]


def test_the_order_of_filling_does_not_change_the_result():
    results = chain_results()
    assert all(r == results[0] for r in results)
    assert results[0] == {"agent": {"name": "example", "path": "/top"}}


# --------------------------------------------------------------------------- #
# Slots in a merge — SPEC §15.2's table
# --------------------------------------------------------------------------- #
def test_a_mapping_over_a_slot_joins_its_overrides():
    tree = merge(parse("p<x>: {a: 1}\n"), parse("p: {b: 2}\n"))
    assert tree["p"].kind == "slot"
    tree["p"].fill(parse("a: 0\nb: 0\nc: 0\n"))
    assert tree.resolve() == {"p": {"a": 1, "b": 2, "c": 0}}


def test_a_later_slot_replaces_a_slot_overrides_and_all():
    tree = merge(parse("p<llamacpp>: {mind: {endpoint: \"x\"}}\n"),
                 parse("p<claude>: {}\n"))
    assert tree["p"].label == ("claude",)
    tree["p"].fill(parse('mind: {endpoint: "claude"}\n'))
    assert tree.resolve() == {"p": {"mind": {"endpoint": "claude"}}}


def test_a_slot_over_a_value_replaces_it():
    tree = merge(parse("secret_backend: {}\n"),
                 parse("secret_backend<pass>: {}\n"))
    assert tree["secret_backend"].kind == "slot"


def test_a_value_over_a_slot_replaces_it():
    assert merge(parse("p<x>: {a: 1}\n"),
                 parse('p: "plain"\n')).resolve() == {"p": "plain"}


# --------------------------------------------------------------------------- #
# Abstract slots — SPEC §15.5
# --------------------------------------------------------------------------- #
TEMPLATE = parse("agent:\n  name: \"t\"\n  harness<>:\n    timeout: 30\n")


def test_a_label_completes_an_abstract_slot_keeping_its_overrides():
    tree = parse("agent<template.agent>:\n  harness<claude>: {}\n")
    tree["agent"].fill(TEMPLATE)
    harness = tree["agent"]["harness"]
    assert harness.label == ("claude",)
    harness.fill(parse('bin: "claude"\ntimeout: 10\n'))
    assert tree.resolve() == {"agent": {
        "name": "t", "harness": {"bin": "claude", "timeout": 30}}}


def test_leaving_an_abstract_slot_without_a_value_is_akan_at_that_fill():
    tree = parse('agent<template.agent>:\n  name: "mine"\n')
    with pytest.raises(AkanError, match=r"abstract slot harness<>"):
        tree["agent"].fill(TEMPLATE)


def test_the_obligation_may_be_passed_on_explicitly():
    middle = parse("agent<template.agent>:\n  harness<>:\n    retries: 2\n")
    middle["agent"].fill(TEMPLATE)
    assert middle["agent"]["harness"].abstract
    user = parse("agent<middle.agent>:\n  harness<claude>: {}\n")
    user["agent"].fill(middle)
    user["agent"]["harness"].fill(parse('bin: "c"\n'))
    assert user.resolve()["agent"]["harness"] == {
        "bin": "c", "timeout": 30, "retries": 2}


@pytest.mark.parametrize("value,result", [
    ("{}", {}), ("None", None), ('{bin: "mine"}', {"bin": "mine"}),
])
def test_a_plain_value_replaces_an_abstract_slot(value, result):
    tree = parse(f"agent<template.agent>:\n  harness: {value}\n")
    tree["agent"].fill(TEMPLATE)
    assert tree.resolve()["agent"]["harness"] == result


def test_replacing_an_ancestor_meets_the_obligation():
    tree = parse("top<t>:\n  agent: None\n")
    tree["top"].fill(parse("agent:\n  harness<>: {}\n"))
    assert tree.resolve() == {"top": {"agent": None}}


def test_code_may_fill_an_abstract_slot_directly():
    tree = parse("agent<>: {}\n")
    tree["agent"].fill(parse('name: "direct"\n'))
    assert tree.resolve() == {"agent": {"name": "direct"}}


def test_an_abstract_slot_left_at_resolve_is_akan():
    with pytest.raises(AkanError, match="agent<>: this abstract slot"):
        parse("agent<>: {}\n").resolve()


# --------------------------------------------------------------------------- #
# persona_grata's templates (letters 2026-10-23c, d)
# --------------------------------------------------------------------------- #
PG = {
    "global": "agent<>: {}\nsecret_backend: {}\nagent_store: \"/store\"\n",
    "base.agent": (
        'agent:\n  name: "agent_base"\n  desc: y"{name}"\n'
        '  path: y"{agent_store}/{name}"\n  persona<>: {}\n  harness<>: {}\n'),
    "base.persona": (
        'persona:\n  name: "persona_base"\n  desc: y"{name}"\n'
        '  mind:\n    endpoint: "http://default"\n    model: "default"\n'
        '    dialects:\n      responses:\n        api_uri: y"{endpoint}/v1"\n'),
    "minimax.persona": (
        'persona<base.persona>:\n  name: "minimax"\n'
        '  mind:\n    model: "MiniMax-M2"\n'),
    "base.harness": (
        'harness:\n  name: "harness_base"\n  path: y"{agent.path}/harness"\n'),
    "claude.harness": (
        'harness<base.harness>:\n  name: "claude"\n'
        '  config_store:\n    model: y"{persona.mind.model}"\n'
        '    model_provider: y"{name}"\n    env:\n'
        '      BASE_URL: y"{persona.mind.dialects.responses.api_uri}"\n'),
    "minimax_claude.agent": (
        'agent<base.agent>:\n  name: "minimax_claude"\n'
        '  persona<minimax.persona>: {}\n'
        '  harness<claude.harness>:\n    config_store:\n      env:\n'
        '        AUTO_COMPACT: "1000000"\n'),
}


def pg(name):
    return parse(PG[name], source=f"{name}.tmpl")


def fill_all(tree):
    """A consumer's loop: fill each slot from the label, until none is left."""
    while tree.slots():
        slot = tree.slots()[0]
        slot.fill(pg(".".join(slot.label)))


def pg_tree():
    tree = pg("global")
    tree["agent"].fill(pg("minimax_claude.agent")["agent"])     # code fills global's <>
    fill_all(tree)
    return tree.resolve()


def test_pg_reach_in_labels_and_two_deep_abstract_slots():
    agent = pg_tree()["agent"]
    assert agent["name"] == "minimax_claude"
    assert agent["persona"]["name"] == "minimax"
    assert agent["harness"]["name"] == "claude"
    assert agent["harness"]["config_store"]["env"]["AUTO_COMPACT"] == "1000000"


def test_pg_a_slot_replaces_a_plain_value():
    tree = merge(pg("global"), parse("secret_backend<pass>: {}\n"))
    assert tree["secret_backend"].kind == "slot"


def test_pg_holes_bind_where_content_lands():
    agent = pg_tree()["agent"]
    store = agent["harness"]["config_store"]
    # a sibling slot's content, across agent
    assert store["model"] == "MiniMax-M2"
    # the enclosing agent, by the key it was filled under
    assert agent["harness"]["path"] == "/store/minimax_claude/harness"
    # {name} is nearest-first: the harness's, the persona's, the agent's
    assert store["model_provider"] == "claude"
    assert agent["persona"]["desc"] == "minimax"
    assert agent["desc"] == "minimax_claude"
    # a filled dialect finds persona.mind.endpoint
    assert store["env"]["BASE_URL"] == "http://default/v1"


def test_pg_any_fill_order_gives_one_answer():
    def run(first_persona):
        tree = pg("global")
        tree["agent"].fill(pg("minimax_claude.agent")["agent"])
        while tree.slots():
            slots = tree.slots()
            pick = (slots[0] if first_persona or len(slots) == 1
                    else slots[-1])
            pick.fill(pg(".".join(pick.label)))
        return tree.resolve()
    assert run(True) == run(False) == pg_tree()
