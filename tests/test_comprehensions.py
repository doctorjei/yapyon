"""Collection construction: lexical bindings, filtering, and ordinary resolution."""

import textwrap

import pytest

from yapyon import AkanError, is_record, loads, loads_record, merge, parse, tier_of


def load(text, **kwargs):
    return loads(textwrap.dedent(text), **kwargs)


@pytest.mark.parametrize("body", [
    '{target: {provider: (persona.name), remote_model_id: (target)} for target in persona.mind.model_list}',
    '\n  target:\n    provider: (persona.name)\n    remote_model_id: (target)\n  for target in persona.mind.model_list',
])
def test_persona_grata_model_rows(body):
    out = loads('persona: {name: "example", mind: {model_list: ["m1", "M/2", \'m"3\']}}\n'
                + 'model_rows: ' + body + '\n')
    assert out['model_rows'] == {
        key: {'provider': 'example', 'remote_model_id': key}
        for key in ['m1', 'M/2', 'm"3']}


@pytest.mark.parametrize("suffix", ['[0]', '.__get__(0)'])
@pytest.mark.parametrize("dialects,expected", [
    ('{responses: {}, chat: {}}', 'responses'),
    ('{responses: None, chat: {}}', 'chat'),
    ('{chat: {}}', 'chat'),
    ('{responses: False, chat: {}}', 'responses'),
])
def test_inline_filtered_selection(suffix, dialects, expected):
    doc = ('supported_dialects: ["responses", "chat"]\n'
           f'persona: {{mind: {{dialects: {dialects}}}}}\n'
           'protocol: [dialect for dialect in supported_dialects '
           'if persona.mind.dialects.__get__(dialect) is not None]' + suffix)
    assert loads(doc)['protocol'] == expected


def test_optional_no_match_and_required_no_match_are_distinct():
    assert loads('xs: []\nx: [item for item in xs].__get__(0)')['x'] is None
    with pytest.raises(AkanError, match='past the end'):
        loads('xs: []\nx: [item for item in xs][0]')


@pytest.mark.parametrize("kind", ['list', 'dict', 'multimap'])
@pytest.mark.parametrize("source", ['[1, 2]', '{a: 1, b: 2}', '{+ a: 1, a: 2}'])
def test_each_input_kind_can_construct_each_output_kind(kind, source):
    binding = 'value' if source.startswith('[') else 'key, value'
    head = 'value' if kind == 'list' else 'value.__str__(): value'
    left, right = ('[', ']') if kind == 'list' else ('{+ ' if kind == 'multimap' else '{', '}')
    out = loads(f'input: {source}\noutput: {left}{head} for {binding} in input{right}')['output']
    forward = loads(f'output: {left}{head} for {binding} in input{right}\ninput: {source}')['output']
    assert forward == out
    if kind == 'list':
        assert out == [1, 2]
    elif kind == 'dict':
        assert out == {'1': 1, '2': 2}
    else:
        assert [(e.key, e.value) for e in out] == [('1', 1), ('2', 2)]


@pytest.mark.parametrize('body', [
    '{+ "same": item for item in input}',
    '\n  + "same": item\n  for item in input',
])
def test_multimap_output_keeps_repeated_keys(body):
    out = loads('input: [1, 2]\noutput: ' + body)['output']
    assert [(entry.key, entry.value) for entry in out] == [('same', 1), ('same', 2)]


def test_dictionary_duplicate_keys_are_akan():
    with pytest.raises(AkanError, match='duplicate key'):
        loads('input: ["x", "x"]\noutput: {item: 1 for item in input}')


@pytest.mark.parametrize('value', ['None', 'False', '0', '[]', '{}'])
def test_nonstring_result_keys_are_akan(value):
    with pytest.raises(AkanError, match='key.*string'):
        loads(f'input: [{value}]\noutput: {{item: 1 for item in input}}')


@pytest.mark.parametrize('value', ['True', 'False', 'None'])
def test_strict_conditions_allow_bool_and_none(value):
    out = loads(f'input: [1]\noutput: [item for item in input if {value}]')
    assert out['output'] == ([1] if value == 'True' else [])


@pytest.mark.parametrize('value', ['0', '1', '0.0', '"false"', '""', '[]', '{}', '{+}', 'b""'])
def test_conditions_do_not_implicitly_cast(value):
    with pytest.raises(AkanError, match='condition takes'):
        loads(f'input: [1]\noutput: [item for item in input if {value}]')


@pytest.mark.parametrize('condition,expected', [
    ('not None', True), ('None or True', True), ('None or None', False),
    ('True and None', False), ('False and missing', False),
    ('True or missing', True), ('1 < 2 <= 2', True),
    ('"x" in ["x"]', True), ('"x" not in {a: 1}', True),
    ('None is None', True), ('0 is not None', True),
])
def test_boolean_and_comparison_expressions(condition, expected):
    out = loads(f'input: [1]\noutput: [item for item in input if {condition}]')
    assert out['output'] == ([1] if expected else [])


def test_excluded_body_is_not_evaluated():
    assert loads('input: [1]\noutput: [missing for item in input if False]')['output'] == []


def test_inline_selection_does_not_hide_later_iteration_errors():
    with pytest.raises(AkanError, match='condition takes'):
        loads('input: [True, 1]\noutput: [item for item in input if item][0]')


def test_lexical_binding_wins_over_nested_data_keys_and_does_not_leak():
    out = load('''
        target: "outer"
        input: ["inner"]
        output: [{target: "field", copied: (target), text: y"{target}"} for target in input]
        after: (target)
    ''')
    assert out['output'] == [{'target': 'field', 'copied': 'inner', 'text': 'inner'}]
    assert out['after'] == 'outer'


def test_forward_references_reach_the_same_fixpoint():
    out = loads('output: [item for item in input]\ninput: (later)\nlater: [1, 2]')
    assert out['output'] == [1, 2]


def test_each_constructed_value_has_fresh_mutable_children():
    out = loads('shared: {a: []}\ninput: [1, 2]\noutput: [(shared) for item in input]')
    out['output'][0]['a'].append(3)
    assert out['output'][1]['a'] == [] and out['shared']['a'] == []


@pytest.mark.parametrize('source,binding', [('[1]', 'a, b'), ('{a: 1}', 'a'), ('{+ a: 1}', 'a')])
def test_source_kind_requires_the_right_binding_count(source, binding):
    with pytest.raises(AkanError, match='iteration binding'):
        loads(f'input: {source}\noutput: [1 for {binding} in input]')


def test_comprehensions_are_not_records():
    doc = 'input: []\noutput: [item for item in input]'
    assert not is_record(doc)
    assert tier_of(doc) == 2
    with pytest.raises(AkanError, match='record'):
        loads_record(doc)


def test_dictionary_comprehensions_merge_with_later_mapping_layers():
    earlier = parse('input: ["m1", "m2"]\nrows: {item: {enabled: True, timeout: 30} for item in input}')
    later = parse('rows: {"m2": {timeout: 60}}')
    assert merge(earlier, later).resolve()['rows'] == {
        'm1': {'enabled': True, 'timeout': 30},
        'm2': {'enabled': True, 'timeout': 60}}
    root = merge(parse('items: ["a"]'), parse('{x: 1 for x in __ROOT__.items}'))
    assert root.resolve() == {'items': ['a'], 'a': 1}
    scoped = merge(parse('items: ["a"]\nprefix: "p"'),
                   parse('{y"{prefix}-{x}": 1 for x in __ROOT__.items}'))
    assert scoped.resolve() == {'items': ['a'], 'prefix': 'p', 'p-a': 1}


@pytest.mark.parametrize('text', [
    'input: [1, 2]\noutput: [item for item in input]',
    'input: ["x"]\noutput: {item: {v: (item)} for item in input}',
    'input: [1, 2]\noutput: {+ "x": item for item in input}',
    'input: [False, True]\noutput: [item for item in input if item].__get__(0)',
])
def test_source_roundtrip_keeps_comprehensions_unevaluated(text):
    tree = parse(text)
    saved = tree.to_source()
    assert ' for ' in saved
    restored = parse(saved)
    assert restored.resolve() == tree.resolve()
    assert restored.to_source() == saved


def test_block_list_head_and_filter_align_with_the_marker():
    out = load('''
        input: [None, False, True]
        output:
          - item
          for item in input
          if item
    ''')
    assert out['output'] == [True]


def test_nested_comprehensions_shadow_without_leaking():
    out = loads('input: [1, 2]\noutput: [[item for item in input] for item in input]')
    assert out['output'] == [[1, 2], [1, 2]]


def test_nested_predicates_use_the_innermost_binding():
    out = loads('input: [True, False]\noutput: [[x for x in input if x] for x in input]')
    assert out['output'] == [[True], [True]]
    nested = loads('input: [True, False]\noutput: [[x for x in input if [(x)] == [True]] for x in input]')
    assert nested['output'] == [[True], [True]]


def test_nested_dictionary_predicates_and_keys_use_the_innermost_binding():
    out = loads('input: ["a", "b"]\noutput: [{x: (x) for x in input if x == "a"} for x in input]')
    assert out['output'] == [{'a': 'a'}, {'a': 'a'}]


def test_safe_method_after_constructed_field_access_preserves_its_question_mark():
    assert loads('out: {part: None}.part?.__str__()')['out'] is None


def test_safe_dot_still_requires_a_call_immediately_after_it():
    with pytest.raises(AkanError, match='only before a call'):
        loads('out: {part: [1]}?.part.__get__(0)')


def test_fresh_output_preserves_all_literal_types():
    out = loads('input: [None, "", [], {}, 0, False, b"hi"]\noutput: [item for item in input]')
    assert out['output'] == out['input']
    assert [type(item) for item in out['output']] == [type(item) for item in out['input']]


def test_expression_whitespace_is_not_restricted():
    out = loads('input: [{id: "x"}]\noutput: [item . id for item in input][ 0 ] . __str__ ( )')
    assert out['output'] == 'x'
    adjacent = loads('input: [1]\noutput: [item for item in input if"x"=="x"]')
    assert adjacent['output'] == [1]


def test_contextual_words_remain_ordinary_keys_and_path_segments():
    out = loads('words: {for: 1, if: 2, in: 3, is: 4, and: 5, or: 6, not: 7}\n'
                'input: [0]\noutput: [words.for for item in input]')
    assert out['output'] == [1]


def test_comprehension_keys_keep_exact_unicode_and_are_not_names():
    out = loads('input: ["name", "ｎａｍｅ"]\noutput: {item: 1 for item in input}')
    assert list(out['output']) == ['name', 'ｎａｍｅ']
    symbolic = parse('input: [1]\noutput: [ｉｆ for ｉｆ in input]')
    saved = symbolic.to_source()
    assert 'for ｉｆ in' in saved
    assert parse(saved).resolve() == symbolic.resolve()
    with pytest.raises(AkanError, match='not names|no key'):
        loads('input: ["name"]\noutput: {item: 1 for item in input}\nx: (output.name)')


@pytest.mark.parametrize('tail', ['for more in input', 'if True if False'])
def test_only_one_for_and_one_if_are_admitted(tail):
    with pytest.raises(AkanError, match='one for clause'):
        loads('input: [1]\noutput: [item for item in input ' + tail + ']')


def test_binding_names_cannot_repeat():
    with pytest.raises(AkanError, match='distinct'):
        loads('input: {a: 1}\noutput: [item for item, item in input]')


def test_a_self_containing_comprehension_uses_the_existing_dependency_refusal():
    with pytest.raises(AkanError, match='cycle|contain'):
        loads('output: [item for item in __ROOT__.output]')


def test_materialization_meets_the_existing_size_ceiling():
    with pytest.raises(AkanError, match='ceiling'):
        loads('input: [1, 2, 3]\noutput: [{a: "long"} for item in input]', max_size=8)


def test_ordinary_inline_multimap_is_a_record():
    doc = '{+ a: 1, a: 2, "a": 3,}'
    assert is_record(doc)
    assert [(e.key, e.value) for e in loads_record(doc)] == [('a', 1), ('a', 2), ('a', 3)]


def test_dictionary_comprehension_merge_save_refuses_without_evaluation():
    tree = merge(parse('items: ["a"]\nrows: {item: {base: 1} for item in items}', source='base.yap'),
                 parse('rows: {"b": {later: 2}}'))
    with pytest.raises(AkanError, match='cannot save.*comprehension') as exc:
        tree.to_source()
    assert exc.value.source == 'base.yap'
    assert tree.resolve()['rows'] == {'a': {'base': 1}, 'b': {'later': 2}}


@pytest.mark.parametrize('reverse', [False, True])
def test_empty_mapping_layers_do_not_prevent_saving_a_comprehension(reverse):
    comp = parse('items: ["a"]\nrows: {item: 1 for item in items}')
    empty = parse('rows: {}')
    tree = merge(empty, comp) if reverse else merge(comp, empty)
    assert parse(tree.to_source()).resolve() == tree.resolve()


def test_three_layer_dictionary_comprehension_merge_preserves_contributions():
    tree = merge(parse('items: ["a"]\nrows: {item: {first: 1} for item in items}'),
                 parse('rows: {"a": {second: 2}}'), parse('rows: {"b": 3}'))
    assert tree.resolve()['rows'] == {'a': {'first': 1, 'second': 2}, 'b': 3}


def test_remaining_runtime_slot_can_be_filled_after_source_roundtrip():
    tree = parse('runtime<chosen>: {}\noutput: [item for item in runtime.items].__get__(0)')
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        candidate['runtime'].fill(parse('items: ["x"]'))
    assert restored.resolve() == tree.resolve()


def test_layer_replacement_discards_unneeded_generated_body_expressions():
    tree = merge(parse('xs: ["a"]\nrows: {x: {bad: (missing)} for x in xs}'),
                 parse('rows: {"a": None}'))
    assert tree.resolve()['rows'] == {'a': None}


def test_generated_body_resolves_after_its_mapping_overrides():
    tree = merge(parse('xs: ["a"]\nrows: {x: {name: "base", label: (name)} for x in xs}'),
                 parse('rows: {"a": {name: "later"}}'))
    assert tree.resolve()['rows'] == {'a': {'name': 'later', 'label': 'later'}}


def test_only_comprehension_authored_values_receive_lexical_bindings():
    tree = merge(parse('x: "outer"\nxs: ["a"]\nrows: {x: {local: (x)} for x in xs}'),
                 parse('rows: {"a": {outside: (x)}}'))
    assert tree.resolve()['rows'] == {'a': {'local': 'a', 'outside': 'outer'}}


def test_indexing_ordinary_literals_and_call_results_uses_the_same_postfix_rules():
    out = loads('input: [[3]]\na: [1, 2][0]\nb: input.__get__(0)[0]\nc: {a: 4}["a"]')
    assert [out[key] for key in ('a', 'b', 'c')] == [1, 3, 4]


@pytest.mark.parametrize('predicate', [
    '(True)', 'not(None)', '1<2', '"x" in["x"]', '(1 < 2)and(True)',
])
def test_no_incidental_whitespace_requirement_in_predicates(predicate):
    assert loads('xs: [1]\nout: [x for x in xs if(' + predicate + ')]')['out'] == [1]


def test_comparison_in_a_head_does_not_scan_a_later_colon_as_a_label():
    assert loads('out: [x < 2 for key, x in {a: 1}]')['out'] == [True]


def test_postfix_operations_work_inside_grouping_parentheses():
    assert loads('xs: [[3]]\nout: (xs.__get__(0)[0])')['out'] == 3


@pytest.mark.parametrize('expression', [
    '[None][0]?.__get__(missing)',
    '[None][0]?.__str__()[0]',
    'xs.__get__(0)?.__str__()[0]',
])
def test_safe_postfix_chains_skip_arguments_and_later_selection(expression):
    assert loads('xs: []\nout: ' + expression)['out'] is None


def test_grouping_ends_a_safe_postfix_chain():
    with pytest.raises(AkanError, match='not a list'):
        loads('out: ([None][0]?.__str__())[0]')


def test_declared_predicate_and_body_calls_run_in_iteration_order():
    from yapyon import loads_contract
    contract = loads_contract('''
PRED:
  params: {x: "int"}
  returns: "bool"
  impl: {python: {symbol: "pred"}}
BODY:
  params: {x: "int"}
  returns: "int"
  impl: {python: {symbol: "body"}}
''')
    calls = []
    def pred(x):
        calls.append(('predicate', x))
        return True
    def body(x):
        calls.append(('body', x))
        return x
    out = loads('xs: [1, 2]\nout: [BODY(x) for x in xs if PRED(x)][0]',
                contract=contract, provide={'pred': pred, 'body': body})
    assert out['out'] == 1
    assert calls == [('predicate', 1), ('body', 1), ('predicate', 2), ('body', 2)]


def test_source_save_does_not_invoke_declared_functions_or_read_environment():
    doc = ('runtime<chosen>: {}\n'
           'out: {x: {env: y"{$HOME}", called: RUN(x)} for x in runtime.items if CHECK(x)}')
    tree = parse(doc, source='unfinished.yap')
    saved = tree.to_source()
    assert 'RUN(x)' in saved and 'CHECK(x)' in saved and '{$HOME}' in saved
    assert parse(saved).to_source() == saved
    assert tree['out'].kind == 'comprehension'
    assert [handle.label for handle in tree.slots()] == [('chosen',)]


def test_generated_relative_key_and_sibling_scope_use_output_positions():
    out = loads('xs: ["a", "b"]\nout: {x: {a: 3, b: (a), key: (__PARENT__.__KEY__)} for x in xs}')
    assert out['out'] == {key: {'a': 3, 'b': 3, 'key': key} for key in ('a', 'b')}


def test_dict_comprehension_source_roundtrip_can_be_filled_before_resolving():
    tree = parse('runtime<chosen>: {}\nout: {x: {v: (x)} for x in runtime.items}')
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        assert len(candidate.slots()) == 1
        candidate['runtime'].fill(parse('items: ["a"]'))
    assert restored.resolve() == tree.resolve()
