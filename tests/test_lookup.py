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

# (path to the slot, reference) — every target here is a string, so the
# document side can splice it with y"{ref}" and the two can be compared.
CASES = [
    (("harness", "deep", 1, "here"), "path"),          # nearest: /inner
    (("harness", "path"), "path"),                    # own key skipped
    (("harness", "deep", 0, "leaf"), "name"),          # a sibling in a list item
    (("harness", "deep", 1, "here"), "name"),          # lists add no frame
    (("harness", "deep", 1, "here"), "__ROOT__.path"),
    (("harness", "deep", 1, "here"), "__PARENT__.__PARENT__.path"),
    (("harness", "deep", 1, "here"), "__KEY__"),
    (("harness", "deep", 1, "here"), "xs[-1]"),
    (("harness", "deep", 1, "here"), "xs[idx]"),
    (("harness", "deep", 1, "here"), "mm.k[1]"),
    (("harness", "deep", 1, "here"), "mind.dialects[protocol].api_uri"),
    (("harness", "deep", 1, "here"), "mind['dialects'].chat.api_uri"),
]


def _with_hole(path, ref):
    """DOC with the slot at `path` replaced by a hole naming `ref`."""
    text = DOC
    if path == ("harness", "path"):
        return text.replace('  path: "/inner"', f'  path: y"{{{ref}}}"')
    if path == ("harness", "deep", 0, "leaf"):
        return text.replace('leaf: "L"', f'leaf: y"{{{ref}}}"')
    return text.replace('here: "SLOT"', f'here: y"{{{ref}}}"')


def _get(tree, path):
    for step in path:
        tree = tree[step]
    return tree


@pytest.mark.parametrize("path,ref", CASES)
def test_lookup_agrees_with_a_document_hole(path, ref):
    by_hole = _get(loads(_with_hole(path, ref)), path)
    by_lookup = lookup(loads(DOC), ref, at=path)
    assert by_lookup == by_hole


def test_lookup_over_an_assembled_tree():
    # the use it exists for: documents loaded separately, assembled, searched
    tree = loads('supported_dialects:\n  - "responses"\n  - "chat"\n')
    tree["mind"] = loads('dialects:\n  chat:\n    api_uri: "c"\n')
    tree["harness"] = {"protocol": "chat", "uri": "${...}"}
    assert lookup(tree, "supported_dialects",
                  at=("harness", "uri")) == ["responses", "chat"]
    assert lookup(tree, "mind.dialects[protocol].api_uri",
                  at=("harness", "uri")) == "c"


def test_a_slot_never_finds_its_own_key():
    # as `protocol: y"{protocol}"` cannot: a hole skips the key it sits under
    tree = {"harness": {"protocol": "chat"}}
    with pytest.raises(AkanError):
        lookup(tree, "protocol", at=("harness", "protocol"))


def test_lookup_returns_containers_as_loaded():
    tree = loads(DOC)
    assert lookup(tree, "mind.dialects.chat", at=("harness", "protocol")) == {
        "api_uri": "c-uri"}
    # a multimap by key is its list view, as in a document (§5.1)
    assert lookup(tree, "mm.k", at=("harness", "protocol")) == ["k1", "k2"]
    assert isinstance(lookup(tree, "mm", at=("harness", "protocol")),
                      OrderedMultimap)


def test_lookup_runs_a_serializer():
    out = lookup(loads(DOC), "xs.__AS_YAPYON__()", at=("harness", "protocol"))
    assert out == '- "x0"\n- "x1"\n- "x2"\n'


def test_path_keys_are_folded_like_document_keys():
    tree = loads(DOC)
    assert lookup(tree, "path", at=("ｈａｒｎｅｓｓ", "protocol")) == "/inner"


def test_the_root_is_a_position():
    assert lookup(loads(DOC), "__ROOT__.idx") == 1


# --------------------------------------------------------------------------- #
# Refusals: AkanError, located by the path
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ref,at,needle", [
    ("nope", ("harness", "protocol"), "no value named 'nope'"),
    ("a b", ("harness", "protocol"), "not an identifier"),
    ("xs[9]", ("harness", "protocol"), "past the end"),
    ("path", ("nokey",), "no key 'nokey' on the path"),
    ("path", ("xs", 9), "outside a list of 3"),
    ("path", ("path", "x"), "cannot step 'x' into a scalar"),
    ("path", ("mm", "k"), "a path cannot pick one entry"),
])
def test_refusals_are_akan_at_the_path(ref, at, needle):
    with pytest.raises(AkanError) as e:
        lookup(loads(DOC), ref, at=at)
    assert needle in str(e.value)
    assert str(e.value).startswith(f"akan: at {'.'.join(map(str, at))}: ")
    assert e.value.line is None


def test_a_tree_holding_something_other_than_data_is_refused():
    with pytest.raises(AkanError) as e:
        lookup({"a": object()}, "a", at=("a",))
    assert "not yapyon data" in str(e.value)
