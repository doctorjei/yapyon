"""SPEC §15: merge before resolving, compare the keys' resulting values."""

import pytest

from yapyon import AkanError, merge, parse


def test_different_expressions_with_equal_key_values_merge():
    earlier = parse('name: "x"\ndata: {y"{name}": {a: 1}}')
    later = parse('data: {y"x": {b: 2}}')
    tree = merge(earlier, later)
    assert tree.resolve() == {"name": "x", "data": {"x": {"a": 1, "b": 2}}}
    assert earlier.resolve()["data"] == {"x": {"a": 1}}


def test_a_later_computed_key_can_read_an_earlier_named_value():
    tree = merge(parse('name: "x"'), parse('y"{name}": 1'))
    assert tree.resolve() == {"name": "x", "x": 1}


def test_a_key_cannot_change_the_named_value_it_depends_on():
    tree = merge(parse('name: "name"'), parse('y"{name}": "other"'))
    with pytest.raises(AkanError, match="cycle"):
        tree.resolve()


def test_different_key_values_remain_different_keys():
    tree = merge(parse('data: {y"x": 1}'), parse('data: {y"y": 2}'))
    assert tree.resolve() == {"data": {"x": 1, "y": 2}}


def test_key_expressions_bind_after_all_layers_have_landed():
    tree = merge(parse('name: "old"\ndata: {y"{name}": {a: 1}}'),
                 parse('name: "new"\ndata: {"new": {b: 2}}'))
    assert tree.resolve() == {"name": "new", "data": {"new": {"a": 1, "b": 2}}}


def test_merge_does_not_evaluate_keys():
    tree = merge(parse('data: {y"{$HOME}": 1}'), parse('data: {"x": 2}'))
    assert tree.resolve(env={"HOME": "x"}) == {"data": {"x": 2}}
    assert tree.resolve(env={"HOME": "y"}) == {"data": {"y": 1, "x": 2}}


def test_overridden_values_are_not_resolved_before_key_matching():
    tree = merge(parse('data: {y"x": y"{missing}"}'), parse('data: {"x": 2}'))
    assert tree.resolve() == {"data": {"x": 2}}


def test_three_layers_keep_precedence_when_middle_key_is_computed():
    tree = merge(parse('data: {x: {a: 1, b: 1}}'),
                 parse('data: {y"x": {b: 2, c: 2}}'),
                 parse('data: {x: {c: 3}}'))
    assert tree.resolve() == {"data": {"x": {"a": 1, "b": 2, "c": 3}}}


def test_duplicates_in_one_input_are_not_silently_merged():
    tree = merge(parse('data: {y"x": 1, y"x": 2}'), parse('other: 1'))
    with pytest.raises(AkanError, match="duplicate key"):
        tree.resolve()


def test_slot_overrides_match_computed_filler_keys_by_value():
    filler = parse('data: {y"{name}": {a: 1}}')
    tree = parse('name: "x"\ndata<base.data>: {y"x": {b: 2}}')
    tree["data"].fill(filler)
    assert tree.resolve() == {"name": "x", "data": {"x": {"a": 1, "b": 2}}}


def test_computed_abstract_obligations_compare_resolved_keys():
    filler = parse('y"{name}"<>: {}')
    tree = parse('name: "x"\npart<source>: {y"x": 42}')
    tree['part'].fill(filler)
    assert tree.resolve() == {"name": "x", "part": {"x": 42}}


def test_a_missing_computed_abstract_override_is_akan_at_the_fill():
    filler = parse('y"{name}"<>: {}', source='base.yap')
    tree = parse('name: "x"\npart<source>: {y"other": 42}', source='user.yap')
    tree['part'].fill(filler)
    with pytest.raises(AkanError, match="overrides.*value") as err:
        tree.resolve()
    assert err.value.source == 'user.yap'


def test_a_computed_override_can_satisfy_a_named_abstract_slot():
    tree = parse('part<source>: {y"x": 42}')
    tree['part'].fill(parse('x<>: {}'))
    assert tree.resolve() == {"part": {"x": 42}}


def test_pending_key_locations_can_be_walked_filled_and_removed():
    tree = parse('name: "x"\ny"{name}"<source>: {}\ny"other": 1')
    slot = tree.slots()[0]
    assert slot.key_lexeme() == 'y"{name}"'
    slot.fill(parse('value: 42'))
    key, handle = tree.items()[-1]
    assert handle.value == 1
    handle.remove()
    with pytest.raises(KeyError):
        _ = handle.value
    assert tree.resolve() == {"name": "x", "x": {"value": 42}}


def test_walking_a_merged_tree_does_not_resolve_or_expose_parser_nodes():
    tree = merge(parse('name: "x"\ny"{name}": 1'), parse('other: 2'))
    keys = tree.keys()
    assert keys[0] == "name"
    assert keys[-1] == "other"
    assert tree[keys[1]].value == 1
    assert tree.resolve() == {"name": "x", "x": 1, "other": 2}


def test_edits_to_a_pending_merge_survive_another_merge():
    tree = merge(parse('name: "x"\ny"{name}": 1\ncfg: {a: 1}'),
                 parse('cfg: {b: 2}'))
    tree['cfg']['a'].merge(parse('9'))
    tree['cfg']['b'].remove()
    tree.merge(parse('other: 3'))
    assert tree.resolve() == {"name": "x", "x": 1, "cfg": {"a": 9}, "other": 3}


def test_pending_key_handles_survive_another_merge():
    tree = merge(parse('y"x": 1'), parse('y"y": 2'))
    handle = tree.items()[0][1]
    tree.merge(parse('other: 3'))
    assert handle.value == 1
    handle.merge(parse('4'))
    assert tree.resolve() == {"x": 4, "y": 2, "other": 3}


def test_copy_and_serializer_wait_for_merged_key_identity():
    tree = merge(parse('data: {y"x": {a: 1}}\ncopy: (data)\nout: data.__as_json__()'),
                 parse('data: {y"x": {b: 2}}'))
    result = tree.resolve()
    assert result["copy"] == {"x": {"a": 1, "b": 2}}
    assert '"b": 2' in result["out"]


def test_quoted_key_paths_are_exact_and_labels_require_names():
    tree = parse('"ｎａｍｅ": 1\nname: 2')
    assert tree['ｎａｍｅ'].value == 1
    assert tree['name'].value == 2
    slot = parse('x<source.name>: {}')
    with pytest.raises(AkanError, match="has no"):
        slot['x'].fill(parse('"name": {}'))
