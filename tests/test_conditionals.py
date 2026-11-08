"""Conditional values share the existing condition, lookup, and source paths."""

import pytest

from yapyon import (AkanError, OrderedMultimap, expand_record, is_record, loads,
                    loads_contract, loads_record, merge, parse, tier_of)


@pytest.mark.parametrize('condition,expected', [('True', 1), ('False', 2), ('None', 2)])
def test_choose_a_value_using_existing_bool_none_conditions(condition, expected):
    assert loads(f'out: 1 if {condition} else 2\n')['out'] == expected


@pytest.mark.parametrize('condition', ['0', '1', '0.0', '"yes"', '""', '[]', '{}', '{+}', 'b""'])
def test_condition_does_not_use_python_truthiness(condition):
    with pytest.raises(AkanError, match='condition takes'):
        loads(f'out: 1 if {condition} else 2\n')


@pytest.mark.parametrize('expression,value', [
    ('1 if True else missing', 1), ('missing if False else 2', 2),
    ('1 if True else BAD()', 1), ('BAD() if None else 2', 2),
    ('1 if True else [(missing), BAD()]', 1), ('1 if True else __int__("bad")', 1),
    ('1 if True else y"{$HOME}"', 1), ('1 if True else {required<>: {}}', 1),
    ('1 if True else [x for x in missing]', 1),
])
def test_only_the_selected_branch_is_evaluated(expression, value):
    assert loads(f'out: {expression}\n', env=None)['out'] == value


@pytest.mark.parametrize('literal,value', [
    ('None', None), ('False', False), ('0', 0), ('0.0', 0.0), ('""', ''),
    ('b"hi"', b'hi'), ('[]', []), ('{}', {}), ('{a: [1]}', {'a': [1]}),
])
def test_selected_value_is_not_coerced_or_pruned(literal, value):
    chosen = loads(f'out: {literal} if True else missing\n')['out']
    assert chosen == value
    assert isinstance(chosen, dict) if isinstance(value, dict) else type(chosen) is type(value)


def test_a_selected_multimap_retains_entry_sequence():
    out = loads('out: {+ k: 1, k: 2} if True else missing\n')['out']
    assert isinstance(out, OrderedMultimap)
    assert [(e.key, e.value) for e in out] == [('k', 1), ('k', 2)]


def test_right_association_and_logical_precedence():
    assert loads('out: 1 if True else 2 if False else 3')['out'] == 1
    assert loads('out: 1 if False else 2 if False else 3')['out'] == 3
    assert loads('out: False or True if False else 7')['out'] == 7
    assert loads('out: 1 if False or True else 2')['out'] == 1
    assert loads('out: 1 if (False if True else missing) else 2')['out'] == 2


def test_merge_pipe_remains_below_conditionals_and_block_inline_forms_agree():
    inline = '{a: 1} | {b: 2} if False else {c: 3}'
    block = '{a: 1}\n| {b: 2} if False else {c: 3}'
    assert loads(inline) == loads(block) == {'a': 1, 'c': 3}
    assert loads('({a: 1} | {b: 2}) if False else {c: 3}') == {'c': 3}
    assert loads('out: {a: 1} if False else {b: 2} | {c: 3}')['out'] == {'b': 2, 'c': 3}


def test_forward_condition_and_branch_reach_the_ordinary_fixpoint():
    out = loads('out: yes if flag else missing\nyes: [1]\nflag: (later)\nlater: True\n')
    assert out['out'] == [1]
    out['out'].append(2)
    assert out['yes'] == [1]


def test_selected_reference_resolves_where_its_value_was_written():
    out = loads('name: "outer"\nbase: {value: y"{name}"}\n'
                'section: {name: "inner", out: base if True else missing}\n')
    assert out['section']['out'] == {'value': 'outer'}


def test_untaken_self_reference_does_not_form_a_cycle():
    assert loads('out: 1 if True else out\n')['out'] == 1
    with pytest.raises(AkanError, match='cycle'):
        loads('out: other if True else 0\nother: (out)\n')


CONTRACT = '''CHECK:
  params: {}
  returns: "bool"
  impl: {python: {symbol: "check"}}
'''


def test_condition_call_is_not_repeated_when_the_chosen_branch_waits():
    calls = []
    def check():
        calls.append('condition')
        return True
    out = loads('out: later if CHECK() else missing\nlater: (last)\nlast: 2\n',
                contract=loads_contract(CONTRACT), provide={'check': check})
    assert out['out'] == 2 and calls == ['condition']


@pytest.mark.parametrize('name', ['if', 'else'])
@pytest.mark.parametrize('spacing', ['', ' '])
def test_contextual_words_can_still_name_declared_calls(name, spacing):
    contract = loads_contract(f'{name}: {{params: {{x: "int"}}, returns: "int", '
                              'impl: {python: {symbol: "identity"}}}\n')
    out = loads(f'out: {name}{spacing}(7)\n'
                f'chosen: 0 if False else {name}{spacing}(8)\n',
                contract=contract, provide={'identity': lambda value: value})
    assert out == {'out': 7, 'chosen': 8}


def test_contextual_words_remain_record_keys_and_reference_segments():
    source = 'if: 1\nelse: 2\nwords: {if: 3, else: 4}\n'
    assert is_record(source) and loads_record(source)['else'] == 2
    assert loads(source + 'out: words.if if True else words.else\n')['out'] == 3
    assert loads(source + 'out: (words.else)\n')['out'] == 4


@pytest.mark.parametrize('expression', [
    '"yes"if(True)else"no"', '"yes" if (True) else ("no")',
    '("yes"if[True][0]else["no"][0])',
    '(\n "yes"\n if\n True\n else\n "no"\n)',
])
def test_inter_token_whitespace_is_not_restricted(expression):
    assert loads('out: ' + expression)['out'] == 'yes'


def test_conditional_comprehension_heads_and_parenthesized_clause_values():
    out = loads('xs: [True, False, None]\n'
                'out: ["yes" if x else "no" for x in xs]\n'
                'filtered: [x for x in xs if x is not None]\n'
                'selected: [x for x in (xs if True else missing) '
                'if (True if x is None else x)]\n'
                'mapping: {"yes" if x else "no": (x) for x in [True, False]}\n')
    assert out['out'] == ['yes', 'no', 'no']
    assert out['filtered'] == [True, False]
    assert out['selected'] == [True, None]
    assert out['mapping'] == {'yes': True, 'no': False}


def test_block_comprehension_and_conditionals_keep_lexical_bindings():
    out = loads('xs: [True, False]\nout:\n'
                '  - {flag: (x), value: 1 if x else 2}\n'
                '  for x in xs\n  if True\n')
    assert out['out'] == [{'flag': True, 'value': 1}, {'flag': False, 'value': 2}]


def test_constructed_conditional_supports_postfix_operations():
    assert loads('out: ([1, 2] if True else missing)[-1]')['out'] == 2
    assert loads('out: (12 if True else missing).__str__()')['out'] == '12'
    assert loads('out: (None if True else missing)?.__str__()')['out'] is None


@pytest.mark.parametrize('source', [
    'flag: True\nout: {a: 0xff} if flag else missing\n',
    'out: [1, 2] if True else y"{$HOME}"\n',
    'xs: [True, False]\nout: [1 if x else 2 for x in xs]\n',
    'out: ({a: 1} | {b: 2}) if True else {c: 3}\n',
    'out: {a: 1} | {b: 2} if False else {c: 3}\n',
])
def test_source_roundtrip_keeps_conditionals_unevaluated_and_idempotent(source):
    tree = parse(source)
    saved = tree.to_source()
    assert ' if ' in saved and ' else ' in saved
    assert parse(saved).to_source() == saved
    assert parse(saved).resolve(env=None) == tree.resolve(env=None)


def test_source_save_does_not_select_a_branch_before_later_environment():
    source = 'out: "set" if __env__("HOME") is not None else "unset"\n'
    saved = parse(source).to_source()
    assert parse(saved).resolve(env={}) == {'out': 'unset'}
    assert parse(saved).resolve(env={'HOME': '/example'}) == {'out': 'set'}


def test_expansion_preserves_selected_lexemes_and_key_provenance():
    text = expand_record('out: {"quoted": 0xff} if True else missing\n')
    assert '"quoted": 0xff' in text
    assert loads_record(text) == {'out': {'quoted': 255}}


def test_merge_can_discard_a_conditional_without_resolving_it():
    tree = merge(parse('out: missing if UNKNOWN() else missing\n'), parse('out: None\n'))
    assert tree.resolve() == {'out': None}
    assert 'missing' not in tree.to_source()


@pytest.mark.parametrize('source,tier', [
    ('out: 1 if True else 2', 2), ('out: 1 if True else y"{$HOME}"', 3),
    ('out: 1 if True else UNKNOWN()', 4),
])
def test_tier_and_record_filter_are_static_even_for_untaken_branches(source, tier):
    assert tier_of(source) == tier and not is_record(source)
    with pytest.raises(AkanError, match='record holds no expressions'):
        loads_record(source)


@pytest.mark.parametrize('source,pattern', [
    ('out: 1 if True', 'needs else'), ('out: 1 if True else', 'expected a value'),
    ('out: 1 if else 2', 'expected a value'),
    ('out: 1 if True else {a: 1, a: 2}', 'duplicate key'),
    ('out: 1 if True else missing[+1]', 'index'),
    ('out: 1 if True else __BAD__', 'reserved name'),
])
def test_syntax_and_static_checks_apply_to_all_branches(source, pattern):
    with pytest.raises(AkanError, match=pattern):
        loads(source)


def test_implicit_reference_syntax_is_static_for_other_short_circuit_operands_too():
    with pytest.raises(AkanError):
        loads('out: False and missing[+1]\n')
    assert loads('out: False and missing\n')['out'] is False


def test_condition_error_names_the_original_source_location():
    with pytest.raises(AkanError, match='example.yap:1:10'):
        loads('out: 1 if 0 else 2\n', source='example.yap')


def test_selected_work_uses_existing_resource_ceilings():
    with pytest.raises(AkanError, match='rendered-size ceiling'):
        loads('xs: [1, 2, 3, 4]\nout: xs if True else []\n', max_size=3)
    source = 'a0: 1\n' + ''.join(f'a{i}: a{i-1} if True else missing\n' for i in range(1, 9))
    with pytest.raises(AkanError, match='depth ceiling'):
        loads(source, max_depth=5)
