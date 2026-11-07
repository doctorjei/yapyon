"""Conservative source normalization preserves unresolved continuation behavior."""

import pytest

import yapyon
from yapyon import AkanError, merge, parse


DIALECT = '''dialect:
  name: "base_dialect"
  api_uri: y"{endpoint}"
  msg_uri: y"{api_uri}/v1/chat/completions"
  model_uri: y"{api_uri}/v1/models"
  emb_uri: y"{api_uri}/v1/embeddings"
  verify:
    check_uri: y"{msg_uri}"
    key_header: "Authorization: Bearer"
    headers: []
    body: ""
  |
  name: "anthropic"
  msg_uri: y"{api_uri}/v1/messages"
  emb_uri: None
  verify:
    headers: ["anthropic-version: 2023-06-01"]
'''

SIMPLIFIED_DIALECT = '''dialect:
  name: "anthropic"
  api_uri: y"{endpoint}"
  msg_uri: y"{api_uri}/v1/messages"
  model_uri: y"{api_uri}/v1/models"
  emb_uri: None
  verify:
    check_uri: y"{msg_uri}"
    key_header: "Authorization: Bearer"
    headers: ["anthropic-version: 2023-06-01"]
    body: ""
'''


def _reload(tree):
    text = tree.to_source()
    restored = parse(text, source="saved.yap")
    assert restored.to_source() == text
    return restored


def test_complete_dialect_collapses_without_rendering_its_expressions():
    tree = parse(DIALECT, source="dialect.tmpl")
    handle = tree['dialect']['msg_uri']
    before = handle.where, handle.lexeme, tree.warnings[:]
    assert tree.to_source() == SIMPLIFIED_DIALECT
    assert (handle.where, handle.lexeme, tree.warnings) == before
    assert tree.to_source() == SIMPLIFIED_DIALECT
    restored = _reload(tree)
    for endpoint in ('"https://one.invalid"', '"https://two.invalid"'):
        context = parse('endpoint: ' + endpoint)
        assert merge(tree, context).resolve() == merge(restored, context).resolve()


@pytest.mark.parametrize('text,expected', [
    ('{} | {}', '{}\n'),
    ('{a: 0x1} | {b: y"{later}"}', 'a: 0x1\nb: y"{later}"\n'),
    ('name: "base"\n|\nname: "chosen"', 'name: "chosen"\n'),
    ('value: BAD()\n|\nvalue: y"{later}"', 'value: y"{later}"\n'),
    ('value: y"{missing}"\n|\nvalue: None', 'value: None\n'),
    ('value: y"{missing}"\n|\nvalue:= {}', 'value:= {}\n'),
    ('[] | [y"{later}"]', '[y"{later}"]\n'),
    ('[y"{later}"] | []', '[y"{later}"]\n'),
    ('{+} | {+ a: y"{later}"}', '+ a: y"{later}"\n'),
    ('{+ a: y"{later}"} | {+}', '+ a: y"{later}"\n'),
    ('None | {a: y"{later}"}', 'a: y"{later}"\n'),
    ('{a: y"{later}"} | None', 'None\n'),
    ('[1] | {}', '{}\n'),
    ('{} | []', '[]\n'),
    ('[1] | None', 'None\n'),
    ('{a: {old: 1}} | {a: "reset"} | {a: {new: 2}}', 'a:\n  new: 2\n'),
])
def test_structurally_proven_winners_and_identities_have_no_redundant_pipe(text, expected):
    tree = parse(text)
    assert tree.to_source() == expected
    assert _reload(tree).to_source() == expected


@pytest.mark.parametrize('endpoint', ['None', 'False', '[]', '{}', '"https://later.invalid"'])
@pytest.mark.parametrize('over', [
    'dialect: {name: "later"}',
    'dialect: {emb_uri: [1]}',
    'dialect: {verify: {headers: ["extra"]}}',
    'dialect: {verify: {headers:= []}}',
    'dialect: {msg_uri:= "fixed"}',
    'dialect:= {}',
])
def test_dialect_preserves_future_override_and_error_outcomes(endpoint, over):
    tree = parse(DIALECT)
    restored = _reload(tree)
    context = parse('endpoint: ' + endpoint + '\n' + over)
    original, saved = merge(tree, context), merge(restored, context)
    try:
        expected = original.resolve()
    except AkanError as error:
        with pytest.raises(AkanError) as caught:
            saved.resolve()
        assert caught.value.msg == error.msg
    else:
        assert saved.resolve() == expected


@pytest.mark.parametrize('filler', [
    '{}', '7', 'None', '[]', '[1]', '{+ a: 1}',
    'name: {old: 1}\nemb_uri: {old: 1}\nverify: {headers: ["old"]}',
])
def test_dialect_can_be_one_grouped_override_of_an_arbitrary_filler(filler):
    text = DIALECT.replace('dialect:', 'dialect<base>:', 1)
    tree = parse('endpoint: "https://slot.invalid"\n' + text)
    restored = _reload(tree)
    for candidate in (tree, restored):
        candidate['dialect'].fill(parse(filler))
    assert restored.resolve() == tree.resolve()


@pytest.mark.parametrize('key', ['name', 'api_uri', 'msg_uri', 'emb_uri', 'verify'])
@pytest.mark.parametrize('operation', ['remove', 'replace', 'merge'])
def test_dialect_effective_field_edits_survive_normalization(key, operation):
    tree = parse(DIALECT)
    restored = _reload(tree)
    for candidate in (tree, restored):
        handle = candidate['dialect'][key]
        if operation == 'remove':
            handle.remove()
        elif operation == 'replace':
            handle.replace(parse('{}'))
        else:
            handle.merge(parse('None'))
        candidate.merge(parse('endpoint: "https://edit.invalid"'))
    try:
        expected = tree.resolve()
    except AkanError as error:
        with pytest.raises(AkanError) as caught:
            restored.resolve()
        assert caught.value.msg == error.msg
    else:
        assert restored.resolve() == expected


@pytest.mark.parametrize('text,expected', [
    ('x: {old: 1}\n|\nx:= {new: 2}', 'x:=\n  new: 2\n'),
    ('x:= 1\n|\nx: 2', 'x:= 2\n'),
])
def test_explicit_replacement_intent_survives_collapse_and_later_edits(text, expected):
    tree = parse(text)
    assert tree.to_source() == expected
    restored = _reload(tree)
    for candidate in (tree, restored):
        candidate['x'].replace(parse('{}'))
        assert merge(parse('x: {seed: 0}'), candidate).resolve() == {'x': {}}


def test_an_ordinary_reset_does_not_invent_a_replacement_annotation():
    tree = merge(parse('x: "reset"'), parse('x: {new: 2}'))
    assert tree.to_source() == 'x:\n  new: 2\n'
    assert ':=' not in tree.to_source()
    lower = parse('x: {seed: 0}')
    for candidate in (tree, _reload(tree)):
        assert merge(lower, candidate).resolve() == {'x': {'seed': 0, 'new': 2}}


def test_first_key_spelling_visibility_order_and_winning_lexeme_survive():
    tree = merge(parse('box: {"a": 0x1, ｘ: 3.10}'),
                 parse('box: {a: 0b10, z: r"text"}'))
    assert tree.to_source() == 'box:\n  "a": 0b10\n  ｘ: 3.10\n  z: r"text"\n'
    for candidate in (tree, _reload(tree)):
        assert candidate['box'].keys() == ['a', 'x', 'z']
        assert candidate['box']['a'].key_lexeme() == '"a"'
        assert candidate['box']['x'].lexeme == '3.10'
        candidate.merge(parse('out: y"{box.a}"'))
        with pytest.raises(AkanError, match='quoted and computed keys are not names'):
            candidate.resolve()


def test_known_parent_simplifies_while_uncertain_child_programs_remain():
    tree = merge(parse('name: "base"\ndata: {y"{key}": 1}\nitems: [(a)]'),
                 parse('name: "chosen"\ndata: {b: 2}\nitems: [(b)]'))
    saved = tree.to_source()
    assert saved.count('name:') == 1 and 'name: "chosen"' in saved
    assert 'data:\n' in saved and 'items:\n' in saved and '|' in saved
    restored = _reload(tree)
    for candidate in (tree, restored):
        candidate.merge(parse('key: "c"\na: 1\nb: 2'))
    assert restored.resolve() == tree.resolve()


def test_pending_key_validation_domains_remain_separate_after_later_collision():
    tree = parse('key: "a"\ndata: {y"{key}": 1}\n|\ndata: {b: 2}')
    restored = _reload(tree)
    assert '|' in restored.to_source()
    for candidate in (tree, restored):
        assert candidate.resolve()['data'] == {'a': 1, 'b': 2}
        candidate['key'].replace(parse('"b"'))
        assert candidate.resolve()['data'] == {'b': 2}


def test_constant_computed_keys_keep_their_pending_removal_locations():
    tree = merge(parse('data: {y"a": 1}'), parse('data: {"a": 2}'))
    restored = _reload(tree)
    assert 'y"a"' in restored.to_source()
    for candidate in (tree, restored):
        candidate['data']['a'].remove()
        assert candidate.resolve() == {'data': {'a': 1}}


@pytest.mark.parametrize('filler,expected', [
    ('{}', {'part': {'config': {'new': 2}}}),
    ('config: {old: 1}', {'part': {'config': {'new': 2}}}),
    ('config: {child<inner>: {}}', {'part': {'config': {'new': 2}}}),
])
def test_sequential_slot_overrides_are_not_combined_into_one_rhs(filler, expected):
    tree = parse('part<base>: {config: "reset"}\n|\npart: {config: {new: 2}}')
    restored = _reload(tree)
    assert '|' in restored.to_source()
    for candidate in (tree, restored):
        candidate['part'].fill(parse(filler))
        assert candidate.resolve() == expected


def test_higher_none_discards_a_named_slot_without_needing_its_filler():
    tree = parse('part<base>: {}\n|\npart: None')
    for candidate in (tree, _reload(tree)):
        assert candidate.slots() == []
        assert candidate.to_source() == 'part: None\n'
        assert candidate.resolve() == {'part': None}


def test_disjoint_slot_and_symbolic_fields_can_share_a_simplified_dictionary():
    tree = merge(parse('seed: "s"\na: y"{seed}"'), parse('b<base>: {x: 1}'))
    assert '|' not in tree.to_source()
    for candidate in (tree, _reload(tree)):
        candidate['seed'].replace(parse('"later"'))
        candidate['b'].fill(parse('y: 2'))
        assert candidate.resolve() == {'seed': 'later', 'a': 'later', 'b': {'y': 2, 'x': 1}}


def test_copies_and_comprehensions_are_not_frozen_from_current_inputs():
    tree = merge(parse('choice: None\nnames: ["a"]\ndata: {a: 1}\n'
                       'rows: {k: 1 for k in names}'),
                 parse('data: (choice)\nrows: {b: 2}'))
    restored = _reload(tree)
    assert '(choice)' in restored.to_source() and 'for k in names' in restored.to_source()
    for candidate in (tree, restored):
        candidate['choice'].replace(parse('7'))
        candidate['names'].replace(parse('["a", "c"]'))
        result = candidate.resolve()
        assert result['data'] == 7
        assert result['rows'] == {'a': 1, 'c': 1, 'b': 2}


@pytest.mark.parametrize('text', ['[0x1] | [1]', '{+ a: 0x1} | {+ a: 1}'])
def test_nonempty_collection_comparison_remains_deferred(text):
    tree = parse(text)
    assert '|' in tree.to_source()
    assert _reload(tree).resolve() == tree.resolve()


def test_simplification_performs_no_resolution_iteration_rendering_or_comparison(monkeypatch):
    tree = merge(parse(DIALECT), parse('home: y"{$HOME}"\ncall: RUN()\n'
                 'rows: {k: 1 for k in names}\nslot<base>: {}\n'
                 'items: [] | [(later)]'))

    def forbidden(*args, **kwargs):
        pytest.fail('source simplification evaluated unfinished data')

    for target in (
        'yapyon.tree.resolve', 'yapyon.tree.environment',
        'yapyon.resolver.Resolver.resolve', 'yapyon.resolver.Resolver._lookup',
        'yapyon.resolver.Resolver._call', 'yapyon.resolver.Resolver._env',
        'yapyon._expressions.evaluate', 'yapyon._expressions._comprehend',
        'yapyon.environment.Environment.get', 'yapyon.Template.render',
        'yapyon.assembly.collection_merge', 'yapyon.assembly._fingerprint',
    ):
        monkeypatch.setattr(target, forbidden)
    saved = tree.to_source()
    assert 'base_dialect' not in saved and '/v1/chat/completions' not in saved
    assert '{$HOME}' in saved and 'RUN()' in saved and 'for k in names' in saved
    assert 'slot<base>' in saved and '(later)' in saved
    assert parse(saved).to_source() == saved


def test_source_simplification_may_lower_output_tier_but_does_not_change_original_record_rules():
    tree = parse('1 | 2')
    assert yapyon.tier_of('1 | 2') == 2
    assert tree.to_source() == '2\n'
    assert yapyon.tier_of(tree.to_source()) == 1
    assert yapyon.loads_record(tree.to_source()) == 2
    with pytest.raises(AkanError, match='record'):
        yapyon.emit(tree)


def test_historical_fill_obligation_is_not_erased_by_a_static_projection():
    tree = parse('part<base>: {other: 42}', source='user.yap')
    tree['part'].fill(parse('name: "x"\ny"need_{name}"<>: {}'))
    tree.merge(parse('extra: 1'))
    with pytest.raises(AkanError, match='undecided abstract-slot obligation'):
        tree.to_source()


def test_collapsed_abstract_slots_keep_each_abstract_override_contribution():
    tree = merge(parse('part<>: {lower: 1}'), parse('part<>: {upper: 2}'))
    restored = _reload(tree)
    assert restored['part'].abstract
    assert restored.to_source().count('part<>:') == 2
    for candidate in (tree, restored):
        candidate['part'].fill(parse('seed: 0'))
        assert candidate.resolve() == {'part': {'seed': 0, 'lower': 1, 'upper': 2}}


@pytest.mark.parametrize('text', [
    'True or (False | False)',
    'True or ({} | {})',
    '({a: 1} | {b: 2}).a',
    '("lower" | "higher").__str__()',
])
def test_simplified_grouped_operands_are_idempotent_in_surrounding_expressions(text):
    tree = parse(text)
    restored = _reload(tree)
    assert restored.resolve() == tree.resolve()


@pytest.mark.parametrize('text', [
    '[] | [' + ', '.join('1' for _ in range(20)) + ']',
    '{+} | {+ ' + ', '.join('a: 1' for _ in range(20)) + '}',
])
def test_empty_collection_identity_materialization_still_meets_the_work_ceiling(text):
    with pytest.raises(AkanError, match='merge comparison/materialization.*work ceiling'):
        parse(text).resolve(max_size=4)


@pytest.mark.parametrize('filler', ['7', 'None', '[]', '{+ a: 1}'])
def test_empty_dictionary_program_applies_ordinary_merging_as_slot_overrides(filler):
    tree = parse('part<base>: {} | {}')
    restored = _reload(tree)
    for candidate in (tree, restored):
        candidate['part'].fill(parse(filler))
        assert candidate.resolve() == {'part': {}}


@pytest.mark.parametrize('text', [
    '{} | {}', '{a: 1} | {b: 2}', '[] | {}', 'None | {}', '[] | {a: 1}',
])
def test_emptied_dictionaries_apply_ordinary_merging_after_edits_and_slot_reuse(text):
    tree = parse(text)
    restored = _reload(tree)
    for candidate in (tree, restored):
        for key in list(candidate.keys()):
            candidate[key].remove()
        host = parse('part<base>: {}')
        host['part'].merge(candidate)
        host['part'].fill(parse('7'))
        assert host.resolve() == {'part': {}}


def test_an_emptied_compacted_nested_dictionary_has_no_overrides_after_extraction():
    tree = parse(DIALECT)
    restored = _reload(tree)
    for candidate in (tree, restored):
        fragment = merge(candidate['dialect'])
        for key in list(fragment.keys()):
            fragment[key].remove()
        host = parse('part<base>: {}')
        host['part'].merge(fragment)
        host['part'].fill(parse('7'))
        assert host.resolve() == {'part': {}}


@pytest.mark.parametrize('count', [550, 700])
def test_history_inspection_does_not_add_a_host_recursion_limit(count):
    tree = merge(*(parse('{a: 1}') for _ in range(count)))
    text = tree.to_source()
    assert parse(text).resolve() == {'a': 1}
    assert parse(text).to_source() == text


def test_reduced_source_work_can_avoid_a_resource_refusal_without_relaxing_limits():
    tree = parse(' | '.join('{key' + str(index) + ': 0}' for index in range(12)))
    with pytest.raises(AkanError, match='work ceiling'):
        tree.resolve(max_size=64)
    restored = _reload(tree)
    assert '|' not in restored.to_source()
    assert restored.resolve(max_size=64) == {'key' + str(index): 0 for index in range(12)}
    limited = parse('value: y"12345"')
    with pytest.raises(AkanError, match='ceiling'):
        _reload(limited).resolve(max_size=1)
