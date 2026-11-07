"""Empty dictionary overrides use ordinary merging, without hidden history."""

import pytest

from yapyon import AkanError, merge, parse


FILLERS = ('7', 'None', 'False', '""', '[]', '[1]', '{+}', '{+ a: 1}', '{}', 'seed: 1')
EMPTY = ('{}', '{} | {}', '({} | {})', '{} | ({} | {})')


@pytest.mark.parametrize('filler', FILLERS)
@pytest.mark.parametrize('overrides', EMPTY)
@pytest.mark.parametrize('separator', (':', ':='))
def test_empty_dictionary_overrides_apply_the_ordinary_kind_rule(filler, overrides, separator):
    original = parse('part<base>' + separator + ' ' + overrides)
    text = original.to_source()
    restored = parse(text)
    assert restored.to_source() == text
    expected = {'seed': 1} if filler == 'seed: 1' else {}
    for tree in (original, restored):
        tree['part'].fill(parse(filler))
        assert tree.resolve() == {'part': expected}


@pytest.mark.parametrize('overrides', EMPTY)
def test_empty_overrides_do_not_forbid_later_overrides(overrides):
    original = parse('part<base>: ' + overrides)
    restored = parse(original.to_source())
    for tree in (original, restored):
        tree['part'].merge(parse('added: 2'))
        tree['part'].fill(parse('seed: 1'))
        assert tree.resolve() == {'part': {'seed': 1, 'added': 2}}


def test_empty_override_kind_rule_agrees_with_ordinary_incompatible_kind_merges():
    assert parse('7 | {}').resolve() == {}
    assert parse('[] | {}').resolve() == {}


def test_emptying_a_compacted_mapping_leaves_no_hidden_history():
    original = merge(parse('first: 1'), parse('last: 2'))
    restored = parse(original.to_source())
    for tree in (original, restored):
        for key in list(tree.keys()):
            tree[key].remove()
        assert tree.to_source() == '{}\n'
        host = parse('part<base>: {}')
        host['part'].merge(tree)
        host['part'].fill(parse('7'))
        assert host.resolve() == {'part': {}}


@pytest.mark.parametrize('collection', ('[{need<>: {}}]', '{+ a: {need<>: {}}}'))
@pytest.mark.parametrize('nested', (False, True))
@pytest.mark.parametrize('overrides', ('{}', '{added: 2}'))
def test_dictionary_overrides_discard_abstract_obligations_inside_incompatible_collections(
        collection, nested, overrides):
    filler = 'branch: ' + collection if nested else collection
    contribution = '{branch: ' + overrides + '}' if nested else overrides
    tree = parse('part<base>: ' + contribution)
    for candidate in (tree, parse(tree.to_source())):
        candidate['part'].fill(parse(filler))
        expected = {'added': 2} if 'added' in overrides else {}
        assert candidate.resolve() == {'part': {'branch': expected} if nested else expected}


def test_pending_override_validation_is_not_skipped_as_if_already_empty():
    original = parse('names: ["x", "x"]\npart<base>: {name: 1 for name in names}')
    restored = parse(original.to_source())
    for tree in (original, restored):
        tree['part'].fill(parse('{}'))
        with pytest.raises(AkanError, match='duplicate'):
            tree.resolve()


@pytest.mark.parametrize('filler', ('7', 'None', '[1]', '{+ a: 1}'))
def test_empty_comprehension_overrides_replace_non_dictionary_fillers(filler):
    original = parse('names: []\npart<base>: {name: 1 for name in names}')
    restored = parse(original.to_source())
    assert 'for name in names' in restored.to_source()
    for tree in (original, restored):
        tree['part'].fill(parse(filler))
        assert tree.resolve() == {'names': [], 'part': {}}


@pytest.mark.parametrize('overrides', EMPTY)
def test_empty_overrides_discard_non_dictionary_pending_fillers_without_evaluating_them(overrides):
    tree = parse('part<base>: ' + overrides)
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        candidate['part'].fill(parse('[(missing)]'))
        assert candidate.resolve() == {'part': {}}
