"""`yapyon.lookup` — §5.2's scope search, offered over a loaded tree.

Approved by the operator 2026-10-12 for persona-grata, which assembles
separately loaded documents and must resolve references *by our ordering*
without holding a copy of the rule. The whole design is that this is the
resolver's search, not a second one, so the central test is agreement: a
reference resolved by a document hole and by `lookup` at the same position
must give the same answer.
"""

import pytest

from yapyon import AkanError, OrderedMultimap, loads, lookup

DOC = '''\
path: "/outer"
name: "root-name"
idx: 1
xs:
  - "x0"
  - "x1"
  - "x2"
mm:
  + k: "k1"
  + j: "j1"
  + k: "k2"
mind:
  dialects:
    chat:
      api_uri: "c-uri"
    responses:
      api_uri: "r-uri"
harness:
  protocol: "chat"
  path: "/inner"
  deep:
    - leaf: "L"
      name: "deep-name"
    - here: "SLOT"
'''

# (path to a slot, reference). The document side writes y"{ref}" at the
# slot; `lookup` stands at the node holding that slot. They agree whenever
# the reference does not name the slot's own key, which a hole skips and a
# node does not have.
CASES = [
    (("harness", "deep", 1, "here"), "path"),          # nearest: /inner
    (("harness", "deep", 0, "leaf"), "name"),          # a sibling in a list item
    (("harness", "deep", 1, "here"), "name"),          # lists add no frame
    (("harness", "deep", 1, "here"), "__ROOT__.path"),
    (("harness", "deep", 1, "here"), "__PARENT__.__PARENT__.path"),
    (("harness", "deep", 1, "here"), "__PARENT__.__PARENT__.__KEY__"),
    (("harness", "deep", 1, "here"), "xs[-1]"),
    (("harness", "deep", 1, "here"), "xs[idx]"),
    (("harness", "deep", 1, "here"), "mm.k[1]"),
    (("harness", "deep", 1, "here"), "mind.dialects[protocol].api_uri"),
    (("harness", "deep", 1, "here"), "mind['dialects'].chat.api_uri"),
]


def _with_hole(path, ref):
    """DOC with the slot at `path` replaced by a hole naming `ref`."""
    if path == ("harness", "deep", 0, "leaf"):
        return DOC.replace('leaf: "L"', f'leaf: y"{{{ref}}}"')
    return DOC.replace('here: "SLOT"', f'here: y"{{{ref}}}"')


def _get(tree, path):
    for step in path:
        tree = tree[step]
    return tree


@pytest.mark.parametrize("path,ref", CASES)
def test_lookup_agrees_with_a_document_hole(path, ref):
    by_hole = _get(loads(_with_hole(path, ref)), path)
    tree = loads(DOC)
    by_lookup = lookup(tree, _get(tree, path[:-1]), ref)
    assert by_lookup == by_hole


def test_lookup_over_an_assembled_tree():
    # the use it exists for: documents loaded separately, assembled, searched
    tree = loads('supported_dialects:\n  - "responses"\n  - "chat"\n')
    tree["mind"] = loads('dialects:\n  chat:\n    api_uri: "c"\n')
    tree["harness"] = harness = {"protocol": "chat"}
    assert lookup(tree, harness, "supported_dialects") == ["responses", "chat"]
    assert lookup(tree, harness, "mind.dialects[protocol].api_uri") == "c"


def test_the_search_starts_at_current_itself():
    # a node's own keys are nearest; there is no slot, so nothing is skipped
    tree = loads(DOC)
    assert lookup(tree, tree["harness"], "path") == "/inner"
    assert lookup(tree, tree, "path") == "/outer"


def test_parent_is_current_as_for_a_hole_inside_it():
    tree = loads(DOC)
    assert lookup(tree, tree["harness"], "__PARENT__.protocol") == "chat"
    assert lookup(tree, tree["harness"], "__PARENT__.__KEY__") == "harness"


def test_lookup_returns_containers_as_loaded():
    tree = loads(DOC)
    here = tree["harness"]
    assert lookup(tree, here, "mind.dialects.chat") == {"api_uri": "c-uri"}
    # a multimap by key is its list view, as in a document (§5.1)
    assert lookup(tree, here, "mm.k") == ["k1", "k2"]
    assert isinstance(lookup(tree, here, "mm"), OrderedMultimap)


def test_lookup_runs_a_serializer():
    tree = loads(DOC)
    out = lookup(tree, tree["harness"], "xs.__as_yapyon__()")
    assert out == '["x0", "x1", "x2"]\n'


def test_current_may_sit_inside_a_multimap():
    # found by identity, so repeated keys do not matter; entries add no frame
    tree = loads('name: "outer"\nmm:\n  + k:\n      a: 1\n  + k:\n      a: 2\n')
    second = tree["mm"]["k"].values()[1]
    assert lookup(tree, second, "a") == 2
    assert lookup(tree, second, "name") == "outer"


def test_current_may_be_a_list():
    tree = loads(DOC)
    assert lookup(tree, tree["xs"], "idx") == 1


# --------------------------------------------------------------------------- #
# Refusals: AkanError, located by where current sits
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ref,needle", [
    ("nope", "no value named 'nope'"),
    ("a b", "names in a path are joined by '.'"),
    ("xs[9]", "past the end"),
    ("__KEY__", "you are at a node"),
])
def test_refusals_are_akan_at_current(ref, needle):
    tree = loads(DOC)
    with pytest.raises(AkanError) as e:
        lookup(tree, tree["harness"], ref)
    assert needle in str(e.value)
    assert str(e.value).startswith("akan: at harness: ")
    assert e.value.line is None


@pytest.mark.parametrize("current,needle", [
    ({"a": 1}, "not a node of this tree"),
    ("/outer", "must be a mapping, list or multimap"),
])
def test_current_must_be_a_node_of_the_tree(current, needle):
    with pytest.raises(AkanError) as e:
        lookup(loads(DOC), current, "path")
    assert needle in str(e.value)


def test_current_placed_twice_has_no_single_answer():
    tree = loads(DOC)
    tree["again"] = tree["harness"]
    with pytest.raises(AkanError) as e:
        lookup(tree, tree["harness"], "path")
    assert "more than once" in str(e.value)


def test_a_tree_holding_something_other_than_data_is_refused():
    tree = {"a": {}, "b": object()}
    with pytest.raises(AkanError) as e:
        lookup(tree, tree["a"], "b")
    assert "not yapyon data" in str(e.value)
