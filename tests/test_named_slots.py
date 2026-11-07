"""Label-filtered discovery returns every match, with optional handle scoping."""

import pytest

from yapyon import parse


DOCUMENT = '''left:
  first<base.persona>: {}
  second<base.persona>: {}
right:
  third<base.persona>: {}
  fourth<base.harness>: {}
abstract<>: {}
'''


def test_label_discovery_returns_all_matches_in_document_order():
    tree = parse(DOCUMENT)
    assert [slot.key for slot in tree.slots('base.persona')] == ['first', 'second', 'third']
    assert [slot.key for slot in tree.slots(('base', 'harness'))] == ['fourth']
    assert tree.slots('absent') == []
    assert len(tree.slots()) == 5


def test_handle_scoping_does_not_select_a_same_label_in_another_branch():
    tree = parse(DOCUMENT)
    assert [slot.key for slot in tree['left'].slots('base.persona')] == ['first', 'second']
    assert [slot.key for slot in tree['right'].slots()] == ['third', 'fourth']
    assert [slot.key for slot in tree['abstract'].slots('')] == ['abstract']
    assert [slot.key for slot in tree.slots(())] == ['abstract']


def test_a_filtered_out_parent_slot_does_not_expose_its_unfilled_overrides():
    tree = parse('part<base>: {child<inner>: {}}')
    assert tree.slots('inner') == []
    assert tree['part'].slots('inner') == []
    tree.slots('base')[0].fill(parse('{}'))
    assert [slot.key for slot in tree.slots('inner')] == ['child']


def test_named_discovery_retains_live_handles_and_independent_fills():
    tree = parse(DOCUMENT)
    slots = tree['left'].slots('base.persona')
    for slot in slots:
        slot.fill(parse('persona: {value: 1}'))
    assert tree['left'].slots() == []
    tree['left']['first']['value'].replace(parse('2'))
    assert tree['left']['second']['value'].value == 1
    assert slots[0].kind == 'mapping'
    slots[0].remove()
    with pytest.raises(KeyError):
        _ = slots[0].kind


def test_label_matching_uses_name_folding_but_not_prefix_matching():
    tree = parse('one<ｂａｓｅ.persona>: {}\ntwo<base>: {}')
    assert [slot.key for slot in tree.slots('base.persona')] == ['one']
    assert [slot.key for slot in tree.slots(('ｂａｓｅ', 'persona'))] == ['one']
    assert [slot.key for slot in tree.slots('base')] == ['two']


@pytest.mark.parametrize('label', [1, ['base'], ('base', 1)])
def test_invalid_label_argument_raises_a_python_type_error(label):
    with pytest.raises(TypeError, match='slot label'):
        parse('{}').slots(label)


@pytest.mark.parametrize('body', [
    '[{part<base>: {}}] | [(missing)]',
    '[{ignored<gone>: {}}] | {key: {part<base>: {}} for key in ["a"]}',
    '{} | {+ entry: {part<base>: {}}}',
])
@pytest.mark.parametrize('groups', [0, 1, 2])
@pytest.mark.parametrize('scoped', [False, True])
def test_named_discovery_does_not_evaluate_pending_collection_positions(
        monkeypatch, body, groups, scoped):
    text = '(' * groups + body + ')' * groups
    tree = parse('branch: ' + text if scoped else text)

    def forbidden(*args, **kwargs):
        pytest.fail('slot discovery evaluated unfinished data')

    monkeypatch.setattr('yapyon.assembly.collection_merge', forbidden)
    monkeypatch.setattr('yapyon.resolver.Resolver.resolve', forbidden)
    assert [slot.label for slot in tree.slots()] == [('base',)]
    matches = (tree['branch'] if scoped else tree).slots('base')
    assert len(matches) == 1 and matches[0].label == ('base',)
    matches[0].fill(parse('value: 1'))
    assert tree.slots('base') == []


def test_reparse_rediscovers_named_slots_without_preserving_old_operand_paths():
    tree = parse('part<base>: {}\n|\npart: {value: 1}')
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        for slot in candidate.slots('base'):
            slot.fill(parse('other: 2'))
        assert candidate.resolve() == {'part': {'other': 2, 'value': 1}}
    assert tree.slots('base') == restored.slots('base') == []
