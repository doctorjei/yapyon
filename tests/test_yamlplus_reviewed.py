"""Executable requirements from the reviewed YamlPlus standard, not the prototype."""

import io
import math

import pytest
import yaml

import yapyon
from yapyon import AkanError, yamlplus
from test_yamlplus_oracle import assert_data, load11, load12


@pytest.mark.parametrize('number,shared', [
    ('0b101', False), ('0o17', False), ('0q12', False), ('0z1F', False),
    ('1_000', False), ('1e5', False), ('1.0e5', False), ('1.0_0', False),
    ('-0xff', False), ('+0xff', False), ('0Xff', False), ('0x_f', False),
    ('00', True), ('000', True), ('01.5', True), ('0xff', True),
    ('0xABC', True), ('1.0e+5', True), ('-0.0', True), ('.5', True),
])
def test_numeric_admission_and_warning_are_reference_interpretations(number, shared):
    source = f'value: {number}\n'
    warnings = []
    got = yamlplus.loads(source, warn=warnings.append)['value']
    assert type(got) is type(yapyon.loads_record(source)['value'])
    assert bool(warnings) is not shared
    assert yamlplus.normalize(source) == source
    if shared:
        assert_data(load11(source)['value'], got)
        assert_data(load12(source)['value'], got)
    else:
        alternative = warnings[0].split('write ', 1)[1].split(' for a shared', 1)[0]
        for reader in (load11, load12, yamlplus.loads):
            fixed = reader(f'value: {alternative}\n')['value']
            assert_data(fixed, got)


@pytest.mark.parametrize('literal,content', [
    ('r"hello"', 'hello'), ('r"line\\nbreak"', 'line\\nbreak'),
    ("'line\\nbreak'", 'line\nbreak'), ("'\\101'", 'A'),
])
def test_valid_raw_and_single_quoted_differences_warn_without_rewriting(literal, content):
    source = f'text: {literal}\n'
    warnings = []
    assert yamlplus.loads(source, warn=warnings.append) == {'text': content}
    assert len(warnings) == 1
    assert 'shared string spelling' in warnings[0]
    assert yamlplus.normalize(source) == source


@pytest.mark.parametrize('digits,expected', [('01', '\x01'), ('012', '\n'),
                                           ('08', '\x008'), ('09', '\x009'),
                                           ('00', '\x00'), ('000', '\x00')])
@pytest.mark.parametrize('quote', ['"', "'"])
def test_active_zero_followed_by_any_digit_warns_and_formats_unambiguously(digits, expected, quote):
    source = f'text: {quote}\\{digits}{quote} # keep this explanation\n'
    warnings = []
    assert yamlplus.loads(source, warn=warnings.append)['text'] == expected
    assert any('active \\0 followed' in warning for warning in warnings)
    output = yamlplus.normalize(source)
    assert '# keep this explanation\n' in output
    assert yamlplus.loads(output)['text'] == expected
    assert yamlplus.normalize(output) == output
    assert_data(load11(output)['text'], expected)
    assert_data(load12(output)['text'], expected)


def test_standalone_and_escaped_zero_are_not_numeric_zero_warnings():
    warnings = []
    source = 'a: "\\0"\nb: "\\\\01"\nc: r"\\01"\n'
    yamlplus.check(source, warn=warnings.append)
    assert len(warnings) == 1 and 'raw literal' in warnings[0]
    assert yamlplus.normalize(source) == source


@pytest.mark.parametrize('literal,expected', [
    ('b"hi"', b'hi'), ('rb"hi"', b'hi'), ('bin"0110100001101001"', b'hi'),
    ('dna"CAATCAAC"', b'hi'), ('oct"320644"', b'hi'),
    ('hex"6869"', b'hi'), ('c32"D1MG"', b'hi'), ('b64"aGk="', b'hi'),
    ('b""', b''), ('b"\\xff"', b'\xff'),
    ('b"""hi\n  there"""', b'hi\nthere'),
])
def test_admitted_bytes_are_bytes_with_hora_not_scalar_coercion(literal, expected):
    source = f'payload: {literal}\n'
    warnings, notices = [], []
    assert yamlplus.loads(source, warn=warnings.append, info=notices.append) == {'payload': expected}
    assert warnings == []
    assert len(notices) == 1 and '1 bytes value(s)' in notices[0]
    assert 'hora:' in notices[0]
    assert yamlplus.normalize(source) == source
    assert isinstance(yaml.safe_load(source)['payload'], str)
    output = yamlplus.dumps({'payload': expected})
    assert yamlplus.loads(output) == {'payload': expected}


@pytest.mark.parametrize('operation', [yamlplus.check, yamlplus.is_yamlplus,
                                      yamlplus.loads, yamlplus.normalize])
def test_hora_is_separate_summarized_and_located_per_operation(operation):
    source = 'a: [b"a", b64"Yg==", None, None]\ntext: "None"\n'
    warnings, notices = [], []
    operation(source, warn=warnings.append, info=notices.append, source='settings.yaml')
    assert warnings == []
    assert len(notices) == 2
    assert 'settings.yaml:1:4: 2 bytes value(s)' in notices[0]
    assert 'settings.yaml:1:21: 2 None value(s)' in notices[1]
    assert all(notice.startswith('hora:') for notice in notices)


def test_host_hora_has_paths_and_counts_acyclic_output_occurrences():
    shared = [b'hi', None]
    notices, warnings = [], []
    source = yamlplus.dumps({'one': shared, 'two': shared}, info=notices.append, warn=warnings.append)
    assert yamlplus.loads(source) == {'one': shared, 'two': shared}
    assert len(notices) == 2
    assert "at root['one'][0]: 2 bytes" in notices[0]
    assert "at root['one'][1]: 2 None" in notices[1]
    assert warnings == []
    stream = io.StringIO()
    notices.clear()
    yamlplus.dump({'value': None}, stream, info=notices.append)
    assert len(notices) == 1 and stream.getvalue() == 'value: None\n'
    notices.clear()
    stream.seek(0)
    assert yamlplus.load(stream, info=notices.append) == {'value': None}
    assert len(notices) == 1


@pytest.mark.parametrize('operation', [yamlplus.check, yamlplus.is_yamlplus,
                                      yamlplus.loads, yamlplus.normalize])
def test_callback_failures_propagate_outside_predicate_invalidity(operation):
    def fail(message):
        raise AkanError('consumer callback failed', 0, 0)

    with pytest.raises(AkanError, match='consumer callback failed'):
        operation('value: None\n', info=fail)
    with pytest.raises(AkanError, match='consumer callback failed'):
        operation('value: 1e5\n', warn=fail)
    with pytest.raises(TypeError, match='info must be callable'):
        operation('value: None\n', info=1)


@pytest.mark.parametrize('source,expected,warnings', [
    ('{port:8080}\n', '{port: 8080}\n', 1),
    ('port:8080\n', 'port: 8080\n', 1),
    ('{ports:[8080,8443]}\n', '{ports:[8080,8443]}\n', 0),
    ('{"port":8080}\n', '{"port":8080}\n', 0),
    ('value: 1# keep\n', 'value: 1 # keep\n', 1),
    ('value:= 1\n', 'value: = 1\n', 1),
])
def test_selected_boundary_fixes_preserve_comments_and_field_intent(source, expected, warnings):
    seen = []
    output = yamlplus.normalize(source, warn=seen.append)
    assert len(seen) == warnings
    assert output == expected
    assert yamlplus.loads(output) == yamlplus.loads(source)
    assert yamlplus.normalize(output) == output
    list(yaml.parse(output))
    if ':=' in source:
        assert yapyon.parse(output).to_source() == 'value:= 1\n'


def test_source_formatter_preserves_comment_associations_layout_and_unselected_spellings():
    source = ('# application settings\n'
              'settings: {yes: 1e5, # retry limit\n'
              '           "ｎａｍｅ": r"hello", # exact text\n'
              '           timeout: 01.5} # seconds\n'
              '\n# keep disabled example: on: "no"\n'
              'payload: hex"6869" # transport data\n')
    output = yamlplus.normalize(source)
    assert output == source.replace('yes:', '"yes":')
    assert yamlplus.loads(output) == yamlplus.loads(source)
    assert yamlplus.normalize(output) == output


def test_folded_names_are_admitted_without_invented_folding_warnings():
    source = 'ｎａｍｅ: 1\né: 2\n'
    warnings = []
    assert yamlplus.loads(source, warn=warnings.append) == {'name': 1, 'é': 2}
    assert warnings == []
    assert yamlplus.normalize(source) == source


@pytest.mark.parametrize('literal', ['r"hello"', "'a\\nb'", 'b"hi"', 'hex"6869"',
                                    '0b101', '00', '01.5', '1e5', 'None', '"None"'])
@pytest.mark.parametrize('layout', ['{value: %s}\n', '[%s]\n', 'value: %s\n',
                                    'value:\n  %s\n', '- %s\n'])
def test_admitted_literals_work_in_each_collection_context(literal, layout):
    source = layout % literal
    assert yamlplus.is_yamlplus(source)
    list(yaml.parse(source))
    assert yamlplus.loads(yamlplus.normalize(source)) == yapyon.loads_record(source)


@pytest.mark.parametrize('body', ['a,b', 'a: b', 'a # b', '[x]', '{x}', 'a]b',
                                 'a,b: c', 'a:[]', 'a\\nb', 'a"b', "a'b"])
@pytest.mark.parametrize('prefix', ['r', 'b'])
@pytest.mark.parametrize('layout', ['value: %s\n', '[%s]\n', '{value: %s}\n'])
def test_yaml_surface_check_uses_yaml_not_yapyon_literal_boundaries(body, prefix, layout):
    literal = prefix + repr(body)
    source = layout % literal
    assert yapyon.is_record(source)
    try:
        list(yaml.parse(source))
        valid = True
    except yaml.YAMLError:
        valid = False
    assert yamlplus.is_yamlplus(source) is valid, source


@pytest.mark.parametrize('source', ['a: "x"# comment\n', 'a: [1]# comment\n',
                                  '{a: 1}# comment\n'])
def test_reference_comment_separation_is_enforced_despite_permissive_readers(source):
    assert yapyon.is_record(source)
    with pytest.raises(AkanError, match='separate an inline comment'):
        yamlplus.check(source)


@pytest.mark.parametrize('source,valid', [
    ('[b"a,:foo"]\n', False), ('[b"a,: foo"]\n', False),
    ('[b"a,?foo"]\n', True), ('[b"a,? foo"]\n', True),
    ('[b"a,*missing"]\n', False), ('[b"a,!tag x"]\n', True),
    ('[b"a,!!str x"]\n', True), ('[b"a,!foo!bar x"]\n', False),
    ('[b"a,&x b,*x,c"]\n', True),
    ('a:\n  b"x: &foo"\n', False),
    ('- b"""x: |\n    hi\n    """\n', True),
])
def test_yaml_indicators_inside_byte_literals_are_checked_in_yaml_context(source, valid):
    assert yapyon.is_record(source)
    try:
        list(yaml.parse(source))
        oracle = True
    except yaml.YAMLError:
        oracle = False
    assert oracle is valid
    assert yamlplus.is_yamlplus(source) is valid
    if valid:
        assert yamlplus.loads(yamlplus.normalize(source)) == yapyon.loads_record(source)


def test_checking_does_not_construct_values_or_resolve(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('membership checking must not resolve or build loaded values')

    monkeypatch.setattr(yamlplus, 'build', forbidden)
    assert yamlplus.is_yamlplus('payload: b"hi"\n')
    yamlplus.check('value: 1e5\n')


def test_negative_control_catches_missing_yaml_surface_validation(monkeypatch):
    monkeypatch.setattr(yamlplus, 'check_syntax', lambda *args: None)
    source = 'value: "\\101"\n'
    assert yamlplus.is_yamlplus(source)
    with pytest.raises(yaml.YAMLError):
        list(yaml.parse(source))


def test_comment_retention_oracle_catches_comment_loss_negative_control(monkeypatch):
    original = yamlplus.normalize
    monkeypatch.setattr(yamlplus, 'normalize', lambda text: original(text).split('#')[0])
    with pytest.raises(AssertionError):
        assert yamlplus.normalize('a: 1 # required setting\n') == 'a: 1 # required setting\n'


def test_cli_hora_is_opt_in_summarized_and_not_payload():
    from test_yamlplus import cli

    source = 'data: [b"a", b"b", None, None]\n'
    quiet = cli(source)
    assert quiet.returncode == 0 and quiet.stderr == '' and quiet.stdout == ''
    visible = cli(source, '--info')
    assert visible.returncode == 0 and visible.stderr.count('hora:') == 2
    assert visible.stdout == ''
    formatted = cli(source, '--write', '--info')
    assert formatted.returncode == 0 and formatted.stdout == source
    assert formatted.stderr.count('hora:') == 2
    assert 'hora:' not in formatted.stdout
