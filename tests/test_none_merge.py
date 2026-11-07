"""None uses ordinary scalar precedence, including over unfinished programs."""

import pytest

import yapyon
from yapyon import AkanError, merge, parse


VALUES = ('None', '7', 'False', '""', 'b""', '{}', '{a: 1}', '[]', '[1]', '{+}', '{+ a: 1}')


def _roundtrip(tree):
    text = tree.to_source()
    restored = parse(text, source='saved.yap')
    assert restored.to_source() == text
    return tree, restored


@pytest.mark.parametrize('value', VALUES)
@pytest.mark.parametrize('route', ('pipe', 'root-api', 'field-api'))
def test_higher_none_replaces_every_established_kind(value, route):
    if route == 'pipe':
        tree = parse(value + ' | None')
    elif route == 'root-api':
        tree = merge(parse(value), parse('None'))
    else:
        tree = parse('field: ' + value)
        tree['field'].merge(parse('None'))
    for candidate in _roundtrip(tree):
        assert candidate.resolve() == ({'field': None} if route == 'field-api' else None)


@pytest.mark.parametrize('value', VALUES)
@pytest.mark.parametrize('route', ('pipe', 'root-api', 'field-api'))
def test_higher_value_replaces_lower_none(value, route):
    expected = yapyon.loads_record(value)
    if route == 'pipe':
        tree = parse('None | ' + value)
    elif route == 'root-api':
        tree = merge(parse('None'), parse(value))
    else:
        tree = parse('field: None')
        tree['field'].merge(parse(value))
        expected = {'field': expected}
    for candidate in _roundtrip(tree):
        actual = candidate.resolve()
        assert actual == expected
        assert type(actual) is type(expected) or isinstance(actual, dict) and isinstance(expected, dict)


@pytest.mark.parametrize('lower', (
    '(missing)', 'MISSING()', 'y"{$UNEXPOSED}"',
    '{bad: (missing)}', '[(missing)]', '{+ a: (missing)}',
    '{name: 1 for name in missing}', '{y"{missing}": 1}',
    '{child<unfilled>: {}}',
))
def test_known_higher_none_discards_pending_data_without_evaluating_it(lower):
    for candidate in _roundtrip(parse(lower + ' | None')):
        assert candidate.slots() == []
        assert candidate.resolve(env_allow=set(), env={}) is None


@pytest.mark.parametrize('separator', (':', ':='))
def test_higher_none_discards_an_unfilled_named_slot_and_its_overrides(separator):
    tree = merge(parse('part<base>: {bad: (missing)}'), parse('part' + separator + ' None'))
    for candidate in _roundtrip(tree):
        assert candidate.slots() == []
        assert candidate.resolve() == {'part': None}


@pytest.mark.parametrize('container', ('{}', '{a: 1}', '[]', '[1]', '{+}', '{+ a: 1}'))
@pytest.mark.parametrize('origin', ('copy', 'call'))
def test_runtime_higher_none_replaces_containers(container, origin):
    contract = yapyon.loads_contract('NULL:\n  params: {}\n  returns: "None"\n'
                                    '  impl: {python: {symbol: "null"}}')
    higher = 'value: (nullable)\nnullable: None' if origin == 'copy' else 'value: NULL()'
    tree = merge(parse('value: ' + container), parse(higher))
    for candidate in _roundtrip(tree):
        assert candidate.resolve(contract=contract, provide={'null': lambda: None})['value'] is None


def test_higher_none_never_calls_a_discarded_function():
    contract = yapyon.loads_contract('RUN:\n  params: {}\n  returns: "Any"\n'
                                    '  impl: {python: {symbol: "run"}}')

    def forbidden():
        pytest.fail('discarded call was evaluated')

    for candidate in _roundtrip(parse('RUN() | None')):
        assert candidate.resolve(contract=contract, provide={'run': forbidden}) is None


@pytest.mark.parametrize('higher,expected', (
    ('part: None', None), ('part:= None', None), ('part: "done"', 'done'),
    ('part: []', []), ('part: {+}', yapyon.OrderedMultimap()),
))
def test_saving_discards_historical_obligations_only_with_their_whole_branch(higher, expected):
    tree = parse('part<base>: {other: 42}', source='user.yap')
    tree['part'].fill(parse('name: "x"\ny"need_{name}"<>: {}'))
    with pytest.raises(AkanError, match='undecided abstract-slot obligation'):
        tree.to_source()
    tree.merge(parse(higher))
    for candidate in _roundtrip(tree):
        assert candidate.resolve() == {'part': expected}


def test_lower_none_does_not_hide_an_incoming_missing_value():
    for candidate in _roundtrip(parse('None | (missing)')):
        with pytest.raises(AkanError, match='missing'):
            candidate.resolve()


def test_none_remains_present_and_distinct_from_absence_and_empty_values():
    tree = merge(parse('nullable: {old: 1}\nempty: {}'), parse('nullable: None'))
    for candidate in _roundtrip(tree):
        assert candidate.resolve() == {'nullable': None, 'empty': {}}
        assert 'absent' not in candidate.keys()


def test_later_contributions_can_change_none_and_replacement_remains_forceful():
    tree = merge(parse('field:= None'), parse('field: {a: 1}'))
    for candidate in _roundtrip(tree):
        assert candidate.resolve() == {'field': {'a': 1}}
        candidate['field'].merge(parse('None'))
        assert candidate.resolve() == {'field': None}
        candidate.merge(parse('field:= {}'))
        assert candidate.resolve() == {'field': {}}
