"""Independent YAML schema oracles and differential checks for YAMLPLUS.md.

PyYAML supplies the YAML syntax reader. These test-only loaders independently
transcribe the pinned schemas, not the profile implementation's predicates.
"""

import datetime
import math
import re

import pytest
import yaml
from yaml.nodes import ScalarNode

import yapyon
from yapyon import yamlplus


class Core12(yaml.SafeLoader):
    yaml_implicit_resolvers = {}


class Schema11(yaml.SafeLoader):
    yaml_implicit_resolvers = {}


def add(loader, tag, pattern):
    loader.add_implicit_resolver('tag:yaml.org,2002:' + tag, re.compile(pattern), None)


add(Core12, 'null', r'^(?:null|Null|NULL|~|)$')
add(Core12, 'bool', r'^(?:true|True|TRUE|false|False|FALSE)$')
add(Core12, 'int', r'^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$')
add(Core12, 'float', r'^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$')


def core_int(loader, node):
    text = loader.construct_scalar(node)
    base = 8 if text.startswith('0o') else 16 if text.startswith('0x') else 10
    return int(text, base)


Core12.add_constructor('tag:yaml.org,2002:int', core_int)

add(Schema11, 'bool', r'^(?:y|Y|yes|Yes|YES|n|N|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF)$')
add(Schema11, 'null', r'^(?:~|null|Null|NULL|)$')
add(Schema11, 'int', r'^(?:[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$')
add(Schema11, 'float', r'^(?:[-+]?(?:[0-9][0-9_]*)?\.[0-9.]*(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$')
add(Schema11, 'timestamp', r'^(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{4}-[0-9][0-9]?-[0-9][0-9]?(?:[Tt]|[ \t]+)[0-9][0-9]?:[0-9]{2}:[0-9]{2}(?:\.[0-9]*)?(?:(?:[ \t]*)Z|[-+][0-9][0-9]?(?::[0-9]{2})?)?)$')
add(Schema11, 'merge', r'^<<$')
add(Schema11, 'value', r'^=$')


def bool11(loader, node):
    return loader.construct_scalar(node) in {'y', 'Y', 'yes', 'Yes', 'YES',
                                            'true', 'True', 'TRUE', 'on', 'On', 'ON'}


Schema11.add_constructor('tag:yaml.org,2002:bool', bool11)


def load12(text):
    return yaml.load(text, Loader=Core12)


def load11(text):
    return yaml.load(text, Loader=Schema11)


def assert_data(actual, expected):
    assert type(actual) is type(expected) or isinstance(actual, dict) and isinstance(expected, dict)
    if isinstance(expected, dict):
        assert list(actual) == list(expected)
        for key in expected:
            assert_data(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, e in zip(actual, expected):
            assert_data(a, e)
    else:
        assert actual == expected
        if isinstance(expected, float) and expected == 0:
            assert math.copysign(1, actual) == math.copysign(1, expected)


def yaml_meaning(value):
    if value is None:
        return 'None'
    if isinstance(value, dict):
        return {key: yaml_meaning(item) for key, item in value.items()}
    if isinstance(value, list):
        return [yaml_meaning(item) for item in value]
    return value


SCALARS = [None, True, False, 0, 1, -1, 2 ** 100, 0.0, -0.0, 1.0,
           1e20, 1e-20, 1.2345678901234567, '', 'None', 'null', 'yes',
           'a "quote"', "it's fine", 'slash\\escape', 'line\nbreak',
           '\x00' + '1', '\x00' + '8', '\x01', '\t\r\n', '\x7f\x85\x9f',
           '\u2028\u2029\ufeff\ufffe\uffff', '日本語', '😀', 'é', 'ｎａｍｅ']


@pytest.mark.parametrize('value', SCALARS)
def test_host_output_loads_under_all_three_yaml_rule_sets(value):
    text = yamlplus.dumps(value)
    assert yapyon.is_yamlplus(text)
    assert_data(yamlplus.loads(text), value)
    for reader in (yaml.safe_load, load11, load12):
        assert_data(reader(text), yaml_meaning(value))


@pytest.mark.parametrize('key', ['ordinary', 'yes', 'no', 'y', 'Y', 'on', 'off',
                                  'true', 'null', 'None', 'True', 'False',
                                  '123', '00', '-12', '+3', '1.5', '1e5',
                                  '0b101', '0o17', '0xff', '12:30', '.inf',
                                  '2001-12-15', '2001-12-15T02:59:43.1Z',
                                  '<<', '=', 'not-a-name', '日本語', 'é',
                                  'ｎａｍｅ', 'line\nbreak', 'quote"key'])
def test_written_keys_remain_strings_in_all_readers(key):
    value = {key: ['None', None, True, 1, 1.0]}
    text = yamlplus.dumps(value)
    assert_data(yamlplus.loads(text), value)
    for reader in (yaml.safe_load, load11, load12):
        assert_data(reader(text), yaml_meaning(value))


@pytest.mark.parametrize('seed', range(24))
def test_nested_output_and_normalization_have_independent_round_trips(seed):
    values = [SCALARS[(seed * 7 + i * 3) % len(SCALARS)] for i in range(5)]
    data = {'settings': {'yes': values, 'null': None, '1.5': 'value'},
            'rows': [{'name': 'x', 'enabled': True}, {}, []], 'tail': seed}
    text = yamlplus.dumps(data)
    assert_data(yamlplus.loads(text), data)
    assert yamlplus.normalize(text) == text
    for reader in (yaml.safe_load, load11, load12):
        assert_data(reader(text), yaml_meaning(data))


@pytest.mark.parametrize('text', [
    '{a:[1], b:{c: 2}}\n', '{"a":1,"b":[2]}\n',
    '[1, 2,]\n', '{a: 1,}\n', '[1,\n  2,\n]\n',
    '- - 1\n  - 2\n', '-\n    a: 1\n', 'a:\n  42\n',
    '"日本語": "😀"\n', 'a: "\\08"\nb: "\\09"\nc: "\\0x"\n',
    'a: 0xff\nb: 1.0e+5\nc: .5\nd: -0.0\n',
])
def test_shared_input_layout_has_matching_yaml_data(text):
    value = yamlplus.loads(text)
    for reader in (yaml.safe_load, load11, load12):
        assert_data(reader(text), value)


KEY_TEXTS = [
    'y', 'Y', 'yes', 'Yes', 'YES', 'YeS', 'n', 'N', 'no', 'No', 'NO',
    'true', 'True', 'TRUE', 'false', 'False', 'FALSE', 'on', 'On', 'ON',
    'off', 'Off', 'OFF', '~', 'null', 'Null', 'NULL', 'NuLl', 'None',
    '0', '+0', '-0', '12', '012', '00', '0b101', '-0b101', '0o17', '-0o17',
    '0x1f', '-0x1f', '0X1f', '1_000', '12:30', '12:60',
    '3.1', '.5', '1.', '1e5', '1.0e5', '1.0e+5', '1.0E-5',
    '.inf', '-.Inf', '+.INF', '.nan', '.NaN', '+.nan',
    '2001-12-15', '2001-12-15T02:59:43.1Z', '2001-1-2 3:04:05',
    '2001-1-2 3:04:05 -5', '2001-1-2 3:04:05-5',
    '<<', '=', 'ordinary', 'nan', 'inf', 'infinity', '日本語',
]


@pytest.mark.parametrize('text', KEY_TEXTS)
def test_warning_criterion_matches_independent_pinned_schema_resolution(text):
    tags = []
    for loader in (Schema11, Core12):
        resolver = loader('')
        try:
            tags.append(resolver.resolve(ScalarNode, text, (True, False)))
        finally:
            resolver.dispose()
    warns = any(tag != 'tag:yaml.org,2002:str' for tag in tags)
    warnings = []
    yamlplus.dumps({text: 1}, warn=warnings.append)
    assert bool(warnings) == warns, (text, tags, warnings)


def test_spec_11_and_pyyaml_difference_for_y_is_not_hidden():
    assert yaml.safe_load('y: 1\n') == {'y': 1}
    assert load11('y: 1\n') == {True: 1}
    warnings = []
    assert yamlplus.loads('y: 1\n', warn=warnings.append) == {'y': 1}
    assert len(warnings) == 1


def test_accepted_collision_is_visible_in_yaml_but_not_applied_by_profile():
    text = 'yes: "first"\non: "second"\n'
    assert yaml.safe_load(text) == {True: 'second'}
    assert load11(text) == {True: 'second'}
    assert load12(text) == {'yes': 'first', 'on': 'second'}
    warnings = []
    assert yamlplus.loads(text, warn=warnings.append) == {'yes': 'first', 'on': 'second'}
    assert len(warnings) == 2


def test_none_difference_is_deliberate_and_source_quotes_remain_significant():
    text = 'missing: None\nword: "None"\n'
    assert yamlplus.loads(text) == {'missing': None, 'word': 'None'}
    for reader in (yaml.safe_load, load11, load12):
        assert reader(text) == {'missing': 'None', 'word': 'None'}


def test_core_oracle_does_not_inherit_11_numeric_extensions():
    assert load12('0b101') == '0b101'
    assert load12('1_000') == '1_000'
    assert load12('-0xff') == '-0xff'
    assert load12('012') == 12
    assert load12('1.0e5') == 100000.0
    assert load12('0o17') == 15
    assert load11('0o17') == '0o17'
    assert isinstance(yaml.safe_load('2001-12-15'), datetime.date)
    assert load12('2001-12-15') == '2001-12-15'


def test_oracle_catches_missing_key_quoting_negative_control(monkeypatch):
    monkeypatch.setattr(yamlplus, '_implicit_type', lambda text: None)
    output = yamlplus.dumps({'yes': 1, 'on': 2})
    with pytest.raises(AssertionError):
        assert_data(yaml.safe_load(output), {'yes': 1, 'on': 2})


def test_oracle_catches_missing_numeric_warning_negative_control(monkeypatch):
    monkeypatch.setattr(yamlplus, '_FLOAT11', re.compile(r'.*'))
    warnings = []
    assert yapyon.is_yamlplus('a: 1e5\n', warn=warnings.append)
    assert warnings == []
    assert isinstance(load11('a: 1e5\n')['a'], str)
    assert isinstance(yamlplus.loads('a: 1e5\n')['a'], float)


def test_value_oracle_catches_quoted_null_negative_control():
    output = yamlplus.dumps({'missing': None}).replace('None', '"None"')
    with pytest.raises(AssertionError):
        assert_data(yamlplus.loads(output), {'missing': None})


def test_warning_oracle_catches_missing_read_warnings_negative_control(monkeypatch):
    monkeypatch.setattr(yamlplus, '_key_warning', lambda *args, **kwargs: '')
    warnings = []
    yamlplus.loads('yes: 1\n', warn=warnings.append)
    assert not any('conversion' in warning or 'convert' in warning for warning in warnings)
