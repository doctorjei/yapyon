"""SPEC §15.2, §15.7: a Tree — a document read but not resolved — walked
with live handles and combined with merge.

Rulings (operator, 2026-10-23; `workbook/designs/tree-assembly.md`): an
opaque tree, not the AST; live handles; merge recurses only between two
mappings, a later value wins across kinds, `None` is kept; holes bind
where content lands.
"""

import pytest

import yapyon
from yapyon import AkanError, Tree, merge, parse


# --------------------------------------------------------------------------- #
# Walking
# --------------------------------------------------------------------------- #
def test_parse_returns_a_tree_that_resolves_like_loads():
    text = 'name: "gw"\nport: 8080\naddr: y"{name}:{port}"\n'
    tree = parse(text)
    assert isinstance(tree, Tree)
    assert tree.resolve() == yapyon.loads(text)


def test_handles_walk_mappings_and_sequences():
    tree = parse('personas:\n  orion:\n    tags: ["helper", "terse"]\n')
    tags = tree["personas"]["orion"]["tags"]
    assert tags.kind == "sequence" and len(tags) == 2
    assert tags[0].value == "helper" and tags[0].lexeme == '"helper"'
    assert tags[-1].value == "terse"
    assert [h.value for h in tags] == ["helper", "terse"]
    assert tree.keys() == ["personas"] and "personas" in tree
    assert tree.at("personas", "orion", "tags", 1).value == "terse"


def test_lexemes_survive():
    tree = parse("v: 3.10\nh: 0xff\ns: 'x'\nb: b64'aGk='\n")
    assert tree["v"].value == 3.1 and tree["v"].lexeme == "3.10"
    assert tree["h"].lexeme == "0xff" and tree["s"].lexeme == "'x'"
    assert tree["b"].type == "bytes" and tree["b"].value == b"hi"


def test_y_strings_and_copies_are_unresolved_but_spelled():
    tree = parse("a: 1\nb: ry'{a}\\n'\nc: (a)\nt: yt\"{a}\"\n")
    assert tree["b"].kind == "ystring" and tree["b"].type == "str"
    assert tree["b"].lexeme == "ry'{a}\\n'"
    assert tree["c"].kind == "copy" and tree["c"].lexeme == "(a)"
    assert tree["t"].type == "template"
    with pytest.raises(TypeError, match="no value until the tree is resolved"):
        tree["b"].value


def test_where_names_the_document():
    tree = parse("a:\n  b: 1\n", source="x.yap")
    assert tree["a"]["b"].where == ("x.yap", 2, 5)


def test_keys_are_compared_as_names():
    tree = parse("ｎａｍｅ: 1\n")
    assert tree["name"].value == 1 and tree["ｎａｍｅ"].key_lexeme() == "ｎａｍｅ"


def test_missing_steps_raise_like_a_dict_or_list():
    tree = parse("a: [1]\n")
    with pytest.raises(KeyError):
        tree["b"]
    with pytest.raises(IndexError):
        tree["a"][3]
    with pytest.raises(KeyError):
        tree["a"]["x"]


def test_handles_are_live_locations():
    tree = parse("a: 1\nb: 2\n")
    a = tree["a"]
    a.replace(parse('"one"'))
    assert a.value == "one"                     # sees the edit
    a.replace(parse("[1]"))
    assert a.kind == "sequence"                 # and the next
    a.remove()
    with pytest.raises(KeyError):
        a.kind                                  # the place is gone
    assert tree.resolve() == {"b": 2}


def test_parse_file_names_the_source(tmp_path):
    path = tmp_path / "agent.tmpl"
    path.write_text('a: y"{missing}"\n', encoding="utf-8")
    tree = yapyon.parse_file(path)
    assert tree.source == str(path)
    with pytest.raises(AkanError, match="agent.tmpl:1:3"):
        tree.resolve()


def test_resolving_leaves_the_tree_as_it_was():
    tree = parse('a: 1\nb: y"{a}"\n')
    assert tree.resolve() == {"a": 1, "b": "1"}
    assert tree["b"].kind == "ystring"
    tree["a"].replace(parse("2"))
    assert tree.resolve() == {"a": 2, "b": "2"}


def test_emit_takes_a_tree():
    assert yapyon.emit(parse("a:   1\n")) == "a: 1\n"


# --------------------------------------------------------------------------- #
# Merging — SPEC §15.2
# --------------------------------------------------------------------------- #
def test_mappings_merge_key_by_key_later_wins():
    base = parse('mind:\n  model: "m1"\n  endpoint: "e"\nname: "b"\n')
    over = parse('mind:\n  model: "m2"\n  extra: 1\n')
    assert merge(base, over).resolve() == {
        "mind": {"model": "m2", "endpoint": "e", "extra": 1}, "name": "b"}


def test_merge_keeps_the_earlier_order_then_appends():
    out = merge(parse("b: 1\na: 2\n"), parse("c: 3\na: 4\n")).resolve()
    assert list(out) == ["b", "a", "c"] and out["a"] == 4


@pytest.mark.parametrize("earlier,later,result", [
    ('a: "s"\n', "a: {x: 1}\n", {"x": 1}),      # a node replaces a string
    ("a: {x: 1}\n", 'a: "s"\n', "s"),           # and a string a node
    ("a: [1, 2]\n", "a:= [3]\n", [3]),
    ("a: {x: 1}\n", "a:= None\n", None),
    ("a: {x: 1}\n", "a: {x: None}\n", {"x": None}),
])
def test_incompatible_kinds_and_explicit_replacement(earlier, later, result):
    assert merge(parse(earlier), parse(later)).resolve() == {"a": result}


def test_merge_takes_many_layers_in_order():
    out = merge(parse("a: 1\nb: 1\nc: 1\n"), parse("b: 2\nc: 2\n"),
                parse("c: 3\n")).resolve()
    assert out == {"a": 1, "b": 2, "c": 3}


def test_merge_leaves_its_inputs_alone():
    base, over = parse("a: {x: 1}\n"), parse("a: {y: 2}\n")
    merge(base, over)
    assert base.resolve() == {"a": {"x": 1}} and over.resolve() == {"a": {"y": 2}}


def test_merge_into_a_branch_and_placing_where_nothing_is():
    tree = parse("personas:\n  orion: {name: \"o\"}\n")
    tree.merge(parse('model: "m"\n'), at=("personas", "orion"))
    tree.merge(parse('name: "k"\n'), at=("personas", "kisama"))
    assert tree.resolve() == {"personas": {
        "orion": {"name": "o", "model": "m"}, "kisama": {"name": "k"}}}


def test_a_handle_merges_too():
    tree = parse("a: {x: 1}\n")
    tree["a"].merge(parse("y: 2\n"))
    assert tree.resolve() == {"a": {"x": 1, "y": 2}}


def test_holes_bind_where_the_merge_lands():
    tree = parse('name: "agent"\nmodel: "m1"\n')
    tree.merge(parse('persona:\n  say: y"{name} uses {model}"\n'))
    assert tree.resolve()["persona"]["say"] == "agent uses m1"


def test_a_merged_value_is_reported_in_its_own_document():
    tree = parse("a: 1\n", source="base.yap")
    tree.merge(parse('b: y"{missing}"\n', source="user.yap"))
    with pytest.raises(AkanError, match=r"user\.yap:1:3"):
        tree.resolve()
