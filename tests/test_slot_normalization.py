"""Document-based acceptance cases for recursive named-slot normalization.

The main persona document is deliberately unchanged. All varying data comes
from complete external documents, filled by their labels, never by editing a
retained merge operand. The first three matrices retain the 120 + 30 + 432
bounded comparisons from the document-only condensation probes.
"""

import itertools
import re

import pytest

from yapyon import AkanError, Hole, OrderedMultimap, Template, parse


PERSONA = '''persona:
  mind:
    endpoint: "https://api.minimax.io"
    dialects:
      chat<chat.dialect>: {}
      responses<responses.dialect>: {}
      anthropic<anthropic.dialect>: {}
      |
      anthropic:
        api_uri: y"{endpoint}/anthropic"
'''

COMPACT_PERSONA = '''persona:
  mind:
    endpoint: "https://api.minimax.io"
    dialects:
      chat<chat.dialect>: {}
      responses<responses.dialect>: {}
      anthropic<anthropic.dialect>:
        api_uri: y"{endpoint}/anthropic"
'''

NAMES = ('chat', 'responses', 'anthropic')
FILL_ORDERS = tuple(itertools.permutations(NAMES))
ENDPOINT = 'https://api.minimax.io'
API_URI = ENDPOINT + '/anthropic'


def _value_facts(value):
    """Compare types and observable order, not Python's bool/int equality."""
    if isinstance(value, dict):
        return ('dict', tuple((key, _value_facts(item))
                              for key, item in value.items()))
    if isinstance(value, list):
        return ('list', tuple(_value_facts(item) for item in value))
    if isinstance(value, OrderedMultimap):
        return ('multimap', tuple((entry.key, _value_facts(entry.value))
                                  for entry in value))
    if isinstance(value, Template):
        return ('template', tuple(
            ('hole', part.ref, part.lexeme, _value_facts(part.value))
            if isinstance(part, Hole) else ('text', part)
            for part in value.parts))
    return (type(value).__name__, value)


def _error_outcome(error, phase):
    # Reloading changes diagnostic positions, not the semantic error or the
    # references it identifies. Keep everything except embedded coordinates.
    message = re.sub(r'first defined on line \d+',
                     'first defined on line <source>', error.msg)
    message = re.sub(r' at line \d+, col \d+', ' at <source>', message)
    return ('akan', phase, message)


def _assert_same_outcome(actual, expected, context):
    assert actual[0] == expected[0], (context, actual, expected)
    if actual[0] == 'value':
        assert _value_facts(actual[1]) == _value_facts(expected[1]), (
            context, actual, expected)
    else:
        assert actual == expected, (context, actual, expected)


def _roundtrip(text):
    tree = parse(text, source='persona.yap')
    before_warnings = tree.warnings[:]
    before_labels = [(slot.label, slot.abstract) for slot in tree.slots()]
    saved = tree.to_source()
    assert saved.endswith('\n')
    restored = parse(saved, source='saved-persona.yap')
    assert restored.to_source() == saved
    assert tree.to_source() == saved
    assert tree.warnings == before_warnings
    assert [(slot.label, slot.abstract) for slot in tree.slots()] == before_labels
    assert [(slot.label, slot.abstract) for slot in restored.slots()] == before_labels
    return saved


def _persona_outcome(text, documents, order):
    tree = parse(text, source='persona.yap')
    files = {name: parse(document, source=name + '.yap')
             for name, document in documents.items()}
    dialects = tree['persona']['mind']['dialects']
    # A label ending on another slot forwards that slot. Revisit the same
    # named field, following the new label rather than guessing a raw path.
    try:
        for _ in range(8):
            changed = False
            for name in order:
                place = dialects[name]
                if place.kind == 'slot' and place.label:
                    filler = files.get(place.label[0])
                    if filler is not None:
                        place.fill(filler)
                        changed = True
            if not changed:
                break
        else:
            pytest.fail(f'forwarded labels did not settle: {order!r}, {documents!r}')
    except AkanError as error:
        return _error_outcome(error, 'fill')
    try:
        return ('value', tree.resolve(env={}))
    except AkanError as error:
        return _error_outcome(error, 'resolve')


def _assert_persona_continuations(documents):
    saved = _roundtrip(PERSONA)
    first = None
    for order in FILL_ORDERS:
        context = (documents, order)
        original = _persona_outcome(PERSONA, documents, order)
        _assert_same_outcome(_persona_outcome(saved, documents, order),
                             original, context)
        # The compact input is independent of the writer under test.
        _assert_same_outcome(_persona_outcome(COMPACT_PERSONA, documents, order),
                             original, context)
        if first is None:
            first = original
        else:
            _assert_same_outcome(original, first, ('fill order', context))
    return first


def _documents(anthropic):
    return {'chat': 'dialect: {}', 'responses': 'dialect: {}',
            'anthropic': 'dialect: ' + anthropic}


def _expected_persona(chat=None, responses=None, anthropic=None):
    return {'persona': {'mind': {
        'endpoint': ENDPOINT,
        'dialects': {
            'chat': {} if chat is None else chat,
            'responses': {} if responses is None else responses,
            'anthropic': {'api_uri': API_URI} if anthropic is None else anthropic,
        },
    }}}


def test_exact_three_slot_persona_emits_the_requested_compact_document():
    assert _roundtrip(PERSONA) == COMPACT_PERSONA
    assert _roundtrip(COMPACT_PERSONA) == COMPACT_PERSONA


# Twenty complete external filler forms, each checked in all six fill orders.
@pytest.mark.parametrize('filler', [
    pytest.param('{}', id='empty-dictionary'),
    pytest.param('[1]', id='list'),
    pytest.param('[1] | [2]', id='list-program'),
    pytest.param('7', id='integer'),
    pytest.param('None', id='none'),
    pytest.param('"text"', id='text'),
    pytest.param('True', id='boolean'),
    pytest.param('b"hi"', id='bytes'),
    pytest.param('{+ item: 1}', id='multimap'),
    pytest.param('{other: 42}', id='retained-field'),
    pytest.param('{endpoint: "https://local.invalid"}', id='local-endpoint'),
    pytest.param('{api_uri: "inherited"}', id='overridden-uri'),
    pytest.param('{api_uri<>: {}}', id='satisfied-required-uri'),
    pytest.param('{kept<>: {}}', id='unsatisfied-required-field'),
    pytest.param('{y"api_uri": "old"}', id='computed-matching-key'),
    pytest.param('{y"x": 1, y"x": 2}', id='computed-duplicate'),
    pytest.param('{k: 1 for k in ["one", "two"]}', id='dictionary-comprehension'),
    pytest.param('[k for k in [1, 2]]', id='list-comprehension'),
    pytest.param('(endpoint)', id='contextual-copy'),
    pytest.param('__str__(1)', id='builtin-call'),
])
def test_persona_external_filler_matrix_survives_save_and_all_fill_orders(filler):
    _assert_persona_continuations(_documents(filler))


INTERACTIONS = [
    pytest.param({
        'chat': 'dialect: {observed: y"{anthropic.api_uri}"}',
        'responses': 'dialect: {endpoint: y"{__ROOT__.persona.mind.endpoint}/responses"}',
        'anthropic': 'dialect: {endpoint: y"{responses.endpoint}"}',
    }, id='cross-slot-endpoint-and-uri'),
    pytest.param({
        'chat': 'dialect: (anthropic)',
        'responses': 'dialect: (chat)',
        'anthropic': 'dialect: (responses)',
    }, id='mutual-copy-cycle'),
    pytest.param({
        'chat': 'dialect: {kept: 1}',
        'responses': 'dialect<chat.dialect>: {other: 2}',
        'anthropic': 'dialect<responses.dialect>: '
                     '{endpoint: y"{__ROOT__.persona.mind.endpoint}/forwarded"}',
    }, id='three-file-forwarding'),
    pytest.param({
        'chat': 'dialect: {config: {old: 1}, endpoint: "local"}',
        'responses': 'dialect<chat.dialect>: {config: "reset"}',
        'anthropic': 'dialect<responses.dialect>: {config: {new: 2}}',
    }, id='forwarded-nonempty-reset-program'),
    pytest.param({
        'chat': 'dialect: {observed: y"{anthropic.api_uri}"}',
        'responses': 'dialect: (chat)',
        'anthropic': 'dialect: {api_uri<>: {}}',
    }, id='required-uri-with-sibling-observer'),
]


@pytest.mark.parametrize('documents', INTERACTIONS)
def test_persona_multi_slot_interactions_survive_save_and_all_fill_orders(documents):
    _assert_persona_continuations(documents)


# Twelve seeds, six placements of the copy chain, and six fill orders: 432 pairs.
@pytest.mark.parametrize('seed', [
    pytest.param('{}', id='empty-dictionary'),
    pytest.param('[1]', id='list'),
    pytest.param('None', id='none'),
    pytest.param('7', id='integer'),
    pytest.param('{endpoint: "local"}', id='local-endpoint'),
    pytest.param('{api_uri: "inherited"}', id='inherited-uri'),
    pytest.param('{other: 42}', id='retained-field'),
    pytest.param('[1] | [2]', id='list-program'),
    pytest.param('{k: 1 for k in ["a", "b"]}', id='dictionary-comprehension'),
    pytest.param('[x for x in [1, 2]]', id='list-comprehension'),
    pytest.param('{y"x": 1, y"x": 2}', id='computed-duplicate'),
    pytest.param('(endpoint)', id='contextual-copy'),
])
def test_persona_copy_chain_placements_preserve_values_and_errors(seed):
    for first, second, third in itertools.permutations(NAMES):
        documents = {
            first: 'dialect: ' + seed,
            second: 'dialect: (' + first + ')',
            third: 'dialect: (' + second + ')',
        }
        _assert_persona_continuations(documents)


@pytest.mark.parametrize('filler', [
    pytest.param('0', id='zero'),
    pytest.param('3.10', id='float'),
    pytest.param('False', id='false'),
    pytest.param('""', id='empty-text'),
    pytest.param('b""', id='empty-bytes'),
    pytest.param('[]', id='empty-list'),
    pytest.param('{+}', id='empty-multimap'),
    pytest.param('yt"unjoined"', id='template'),
])
def test_every_established_filler_kind_is_replaced_by_the_dictionary_override(filler):
    outcome = _assert_persona_continuations(_documents(filler))
    _assert_same_outcome(outcome, ('value', _expected_persona()), filler)


@pytest.mark.parametrize('filler,expected', [
    pytest.param('{other: 42, api_uri: "inherited"}',
                 {'other': 42, 'api_uri': API_URI}, id='retain-other-field'),
    pytest.param('{endpoint: "https://local.invalid"}',
                 {'endpoint': 'https://local.invalid',
                  'api_uri': 'https://local.invalid/anthropic'}, id='nearest-endpoint'),
    pytest.param('{api_uri<>: {}}', {'api_uri': API_URI}, id='fulfill-required-uri'),
    pytest.param('{y"api_uri": "inherited"}', {'api_uri': API_URI},
                 id='cross-contribution-key-collision-is-not-duplicate'),
    pytest.param('{k: 1 for k in ["one", "two"]}',
                 {'one': 1, 'two': 1, 'api_uri': API_URI}, id='retain-comprehension'),
])
def test_persona_successes_have_independent_value_and_order_oracles(filler, expected):
    outcome = _assert_persona_continuations(_documents(filler))
    _assert_same_outcome(outcome, ('value', _expected_persona(anthropic=expected)), filler)


@pytest.mark.parametrize('filler,phase,message', [
    pytest.param('{kept<>: {}}', 'fill', r'abstract slot kept<>',
                 id='required-field-is-not-silently-discharged'),
    pytest.param('{y"x": 1, y"x": 2}', 'resolve', r"duplicate key 'x'",
                 id='same-contribution-computed-duplicate'),
    pytest.param('{k: 1 for k in ["x", "x"]}', 'resolve', r"duplicate key 'x'",
                 id='comprehension-duplicate'),
    pytest.param('{y"{missing}": 1}', 'resolve', r"no value named 'missing'",
                 id='computed-key-missing-reference'),
    pytest.param('{y"{anthropic["x"]}": "x"}', 'resolve', r'cycle',
                 id='computed-key-cycle'),
    pytest.param('{kept: y"{missing}"}', 'resolve', r"no value named 'missing'",
                 id='retained-value-missing-reference'),
])
def test_persona_semantic_errors_survive_with_their_fill_or_resolve_phase(
        filler, phase, message):
    outcome = _assert_persona_continuations(_documents(filler))
    assert outcome[:2] == ('akan', phase), (filler, outcome)
    assert re.search(message, outcome[2]), (filler, outcome)


def test_cross_slot_context_is_resolved_at_the_landing_location():
    documents = {
        'chat': 'dialect: {observed: y"{anthropic.api_uri}"}',
        'responses': 'dialect: {endpoint: y"{__ROOT__.persona.mind.endpoint}/responses"}',
        'anthropic': 'dialect: {endpoint: y"{responses.endpoint}"}',
    }
    endpoint = ENDPOINT + '/responses'
    outcome = _assert_persona_continuations(documents)
    _assert_same_outcome(outcome, ('value', _expected_persona(
        chat={'observed': endpoint + '/anthropic'},
        responses={'endpoint': endpoint},
        anthropic={'endpoint': endpoint, 'api_uri': endpoint + '/anthropic'},
    )), documents)


def test_forwarded_nonempty_overrides_keep_the_reset_before_the_local_dictionary():
    documents = {
        'chat': 'dialect: {config: {old: 1}, endpoint: "local"}',
        'responses': 'dialect<chat.dialect>: {config: "reset"}',
        'anthropic': 'dialect<responses.dialect>: {config: {new: 2}}',
    }
    outcome = _assert_persona_continuations(documents)
    _assert_same_outcome(outcome, ('value', _expected_persona(
        chat={'config': {'old': 1}, 'endpoint': 'local'},
        responses={'config': 'reset', 'endpoint': 'local'},
        anthropic={'config': {'new': 2}, 'endpoint': 'local',
                   'api_uri': 'local/anthropic'},
    )), documents)


def test_mutual_cross_slot_copies_remain_a_cycle_not_a_save_time_error():
    documents = {
        'chat': 'dialect: (anthropic)',
        'responses': 'dialect: (chat)',
        'anthropic': 'dialect: (responses)',
    }
    outcome = _assert_persona_continuations(documents)
    assert outcome[:2] == ('akan', 'resolve')
    assert 'cycle' in outcome[2]


@pytest.mark.parametrize('prefix', ['', 'outer:\n', 'outer:\n  inner:\n'])
def test_empty_named_slot_absorption_recurses_at_known_dictionary_depths(prefix):
    indent = '  ' * prefix.count('\n')
    body = 'part<base>: {}\n|\npart: {value: 1}\n'
    compact = 'part<base>:\n  value: 1\n'
    text = prefix + ''.join(indent + line + '\n' for line in body.splitlines())
    expected = prefix + ''.join(indent + line + '\n' for line in compact.splitlines())
    saved = _roundtrip(text)
    assert saved == expected
    for source in (text, saved):
        tree = parse(source)
        place = tree.root
        for key in ('outer', 'inner')[:prefix.count('\n')]:
            place = place[key]
        place['part'].fill(parse('kept: 2'))
        result = tree.resolve()
        for key in ('outer', 'inner')[:prefix.count('\n')]:
            result = result[key]
        assert result['part'] == {'kept': 2, 'value': 1}


@pytest.mark.parametrize('text,expected', [
    pytest.param('part<>: {}\n|\npart: {value: 1}\n',
                 'part:\n  value: 1\n', id='abstract-slot-is-selected-not-retained'),
    pytest.param('part<base>: {}\n|\npart:= {value: 1}\n',
                 'part:=\n  value: 1\n', id='explicit-replacement-discards-slot'),
])
def test_absorption_does_not_invent_an_abstract_or_replaced_slot(text, expected):
    saved = _roundtrip(text)
    assert saved == expected
    for source in (text, saved):
        tree = parse(source)
        assert tree.slots() == []
        assert tree.resolve() == {'part': {'value': 1}}


def test_nonempty_reset_is_not_mistaken_for_an_empty_slot_override():
    text = 'part<base>: {config: "reset"}\n|\npart: {config: {new: 2}}\n'
    saved = _roundtrip(text)
    assert '|' in saved
    for source in (text, saved):
        tree = parse(source)
        tree['part'].fill(parse('config: {old: 1}'))
        assert tree.resolve() == {'part': {'config': {'new': 2}}}
