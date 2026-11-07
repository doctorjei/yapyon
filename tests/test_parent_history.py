"""Empty parent dictionaries do not retain hidden override operations."""

import pytest

import yapyon
from yapyon import AkanError, merge, parse


LAYOUTS = ('root', 'mapping', 'sequence')
ACTIONS = ('dictionary', 'none', 'list', 'multimap', 'moved-slot')
FILLERS = ('7', 'None', '[]', '{+ a: 1}', '{}', 'seed: 1')


def _parent(tree, layout):
    if layout == 'mapping':
        return tree['branch']
    if layout == 'sequence':
        return tree[0]
    return tree.root


def _make(layout, action):
    body = 'part<base>: {config: "reset"}'
    text = ('branch: {' + body + '}' if layout == 'mapping' else
            '[{' + body + '}]' if layout == 'sequence' else body)
    tree = parse(text, source='original.yap')
    slot = _parent(tree, layout)['part']
    if action == 'moved-slot':
        slot.fill(parse('part<middle>: {other: 2}')['part'])
    else:
        source = {'dictionary': 'config: {new: 2}', 'none': 'None',
                  'list': '[1]', 'multimap': '{+ a: 1}'}[action]
        slot.merge(parse(source))
    return tree


def _reuse(fragment, filler='7'):
    target = parse('target<base>: {}')
    target['target'].merge(fragment)
    target['target'].fill(parse(filler))
    return target.resolve()['target']


def _empty_and_reuse(tree, layout, filler):
    parent = _parent(tree, layout)
    for key in list(parent.keys()):
        parent[key].remove()
    return _reuse(merge(parent), filler)


@pytest.mark.parametrize('layout', LAYOUTS)
@pytest.mark.parametrize('action', ACTIONS)
@pytest.mark.parametrize('filler', FILLERS)
def test_emptied_parent_has_no_overrides_after_save_remove_and_slot_reuse(layout, action, filler):
    tree = _make(layout, action)
    saved = tree.to_source()
    restored = parse(saved, source='saved.yap')
    assert restored.to_source() == saved
    expected = {'seed': 1} if filler == 'seed: 1' else {}
    assert _empty_and_reuse(tree, layout, filler) == expected
    assert _empty_and_reuse(restored, layout, filler) == expected


@pytest.mark.parametrize('action', ACTIONS)
def test_emptied_parent_has_no_hidden_overrides_without_a_prior_save(action):
    tree = _make('root', action)
    assert _empty_and_reuse(tree, 'root', '7') == {}


@pytest.mark.parametrize('layout', LAYOUTS)
def test_an_emptied_parent_saves_as_a_plain_empty_dictionary(layout):
    tree = _make(layout, 'dictionary')
    parent = _parent(tree, layout)
    parent['part'].remove()
    fragment = merge(parent)
    assert _reuse(fragment) == {}
    saved = fragment.to_source()
    assert saved == '{}\n'
    restored = parse(saved)
    assert restored.to_source() == saved
    assert _reuse(restored) == {}


@pytest.mark.parametrize('text', [
    '{}', 'a: 1', 'part<base>: {}', 'part<base>:= {}',
    'part<base>: {} | {}', '[] | {a: 1}',
])
def test_all_emptied_parent_spellings_have_the_same_override_identity(text):
    tree = parse(text)
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        for key in list(candidate.keys()):
            candidate[key].remove()
        assert _reuse(candidate) == {}


def test_reading_and_saving_a_single_slot_does_not_change_its_parent():
    tree = parse('part<base>: {config: "reset"}')
    assert tree['part'].label == ('base',)
    tree['part'].overrides.to_source()
    tree.to_source()
    tree['part'].remove()
    assert _reuse(tree) == {}


@pytest.mark.parametrize('action', ACTIONS)
def test_whole_parent_replacement_is_an_empty_override_identity(action):
    tree = _make('root', action)
    tree.root.replace(parse('{}'))
    assert tree.to_source() == '{}\n'
    assert _reuse(tree) == {}


@pytest.mark.parametrize('layout', ['mapping', 'sequence'])
def test_removing_a_changed_parent_does_not_leave_operations_in_its_ancestors(layout):
    tree = _make(layout, 'dictionary')
    if layout == 'mapping':
        tree['branch'].remove()
        assert tree.to_source() == '{}\n'
        assert _reuse(tree) == {}
    else:
        tree[0].remove()
        assert tree.resolve() == []


def test_copying_and_emptying_a_parent_does_not_alias_its_original_slot():
    tree = _make('root', 'dictionary')
    copied = merge(tree)
    copied['part'].remove()
    assert _reuse(copied) == {}
    assert tree['part'].label == ('base',)
    assert copied.to_source() == parse(copied.to_source()).to_source()


def test_removed_pending_key_locations_do_not_leave_hidden_overrides():
    tree = parse('part<base>: {}\ny"{missing}": 1')
    tree['part'].merge(parse('config: 2'))
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        for key in list(candidate.keys()):
            candidate[key].remove()
        assert _reuse(candidate) == {}


def test_empty_override_handling_does_not_erase_a_completed_fills_abstract_obligation():
    tree = _make('root', 'dictionary')
    tree['part'].fill(parse('name: "x"\ny"need_{name}"<>: {}'))
    with pytest.raises(AkanError, match='undecided abstract-slot obligation'):
        tree.to_source()


def test_parent_saving_does_not_evaluate_or_mutate_the_input(monkeypatch):
    tree = _make('root', 'dictionary')
    handle = tree['part']
    before = handle.where, handle.label, list(tree.warnings)

    def forbidden(*args, **kwargs):
        pytest.fail('source writing evaluated unfinished data')

    for target in ('yapyon.tree.resolve', 'yapyon.tree.environment',
                   'yapyon.resolver.Resolver._lookup', 'yapyon.resolver.Resolver._call',
                   'yapyon._expressions.evaluate', 'yapyon.assembly._fingerprint'):
        monkeypatch.setattr(target, forbidden)
    saved = tree.to_source()
    assert (handle.where, handle.label, tree.warnings) == before
    assert tree.to_source() == saved
    assert parse(saved).to_source() == saved


@pytest.mark.parametrize('operand', ['[]', '{}', '{part<base>: {}}'])
def test_replacing_a_field_with_a_deep_slot_free_value_does_not_project_it(operand):
    donor = parse(' | '.join([operand] * 1200))
    receiver = parse('x: 0')
    receiver['x'].replace(donor)
    receiver['x'].remove()
    assert receiver.to_source() == '{}\n'


def test_finished_empty_data_and_emptied_source_have_the_same_override_identity():
    tree = _make('root', 'dictionary')
    tree['part'].remove()
    data = tree.resolve()
    assert data == {}
    fresh = parse(yapyon.dumps(data))
    assert fresh.to_source() == '{}\n'
    assert _reuse(fresh) == _reuse(tree) == {}
