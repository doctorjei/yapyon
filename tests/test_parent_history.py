"""Retained slot operations make their containing dictionary a program."""

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
def test_parent_retains_program_identity_after_save_remove_and_slot_reuse(layout, action, filler):
    tree = _make(layout, action)
    saved = tree.to_source()
    restored = parse(saved, source='saved.yap')
    assert restored.to_source() == saved
    supplied = yapyon.loads_record(filler)
    expected = supplied if isinstance(supplied, dict) else {}
    assert _empty_and_reuse(tree, layout, filler) == expected
    assert _empty_and_reuse(restored, layout, filler) == expected


@pytest.mark.parametrize('action', ACTIONS)
def test_parent_history_is_retained_by_the_edit_without_a_prior_save(action):
    tree = _make('root', action)
    assert _empty_and_reuse(tree, 'root', '7') == {}


@pytest.mark.parametrize('layout', LAYOUTS)
def test_an_emptied_parent_program_can_itself_be_saved_and_reloaded(layout):
    tree = _make(layout, 'dictionary')
    parent = _parent(tree, layout)
    parent['part'].remove()
    fragment = merge(parent)
    assert _reuse(fragment) == {}
    saved = fragment.to_source()
    restored = parse(saved)
    assert restored.to_source() == saved
    assert _reuse(restored) == {}


@pytest.mark.parametrize('text', [
    '{}', 'a: 1', 'part<base>: {}', 'part<base>:= {}',
    'part<base>: {} | {}', '[] | {a: 1}',
])
def test_literal_parent_controls_do_not_acquire_unrelated_history(text):
    tree = parse(text)
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        for key in list(candidate.keys()):
            candidate[key].remove()
        assert _reuse(candidate) == 7


def test_reading_and_saving_a_single_slot_does_not_change_its_parents_identity():
    tree = parse('part<base>: {config: "reset"}')
    assert tree['part'].label == ('base',)
    tree['part'].overrides.to_source()
    tree.to_source()
    tree['part'].remove()
    assert _reuse(tree) == 7


@pytest.mark.parametrize('action', ACTIONS)
def test_whole_parent_replacement_discards_its_former_operation_history(action):
    tree = _make('root', action)
    tree.root.replace(parse('{}'))
    assert tree.to_source() == '{}\n'
    assert _reuse(tree) == 7


@pytest.mark.parametrize('layout', ['mapping', 'sequence'])
def test_only_the_containing_mapping_keeps_the_lifted_program_not_unrelated_ancestors(layout):
    tree = _make(layout, 'dictionary')
    if layout == 'mapping':
        tree['branch'].remove()
        assert tree.to_source() == '{}\n'
        assert _reuse(tree) == 7
    else:
        tree[0].remove()
        assert tree.resolve() == []


def test_copies_retain_parent_history_without_aliasing_the_original_slot():
    tree = _make('root', 'dictionary')
    copied = merge(tree)
    copied['part'].remove()
    assert _reuse(copied) == {}
    assert tree['part'].label == ('base',)
    assert copied.to_source() == parse(copied.to_source()).to_source()


def test_pending_key_locations_survive_until_their_corresponding_removals():
    tree = parse('part<base>: {}\ny"{missing}": 1')
    tree['part'].merge(parse('config: 2'))
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        for key in list(candidate.keys()):
            candidate[key].remove()
        assert _reuse(candidate) == {}


def test_parent_history_does_not_erase_a_completed_fills_abstract_obligation():
    tree = _make('root', 'dictionary')
    tree['part'].fill(parse('name: "x"\ny"need_{name}"<>: {}'))
    with pytest.raises(AkanError, match='undecided abstract-slot obligation'):
        tree.to_source()


def test_retained_parent_saving_does_not_evaluate_or_mutate_the_input(monkeypatch):
    tree = _make('root', 'dictionary')
    handle = tree['part']
    before = handle.where, handle.label, list(tree.warnings)

    def forbidden(*args, **kwargs):
        pytest.fail('parent-history source writing evaluated unfinished data')

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


def test_finished_data_export_does_not_inherit_unresolved_program_history():
    tree = _make('root', 'dictionary')
    tree['part'].remove()
    data = tree.resolve()
    assert data == {}
    fresh = parse(yapyon.dumps(data))
    assert fresh.to_source() == '{}\n'
    assert _reuse(fresh) == 7
