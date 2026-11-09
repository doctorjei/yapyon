"""The opt-in profile, its warnings, and its read/write boundaries."""

import io
import math
from pathlib import Path
import subprocess
import sys

import pytest

import yapyon
from yapyon import AkanError, yamlplus


@pytest.mark.parametrize("text", [
    'a: "hello"\n', 'a: True\nb: False\nc: None\n',
    '[1, 2, "three"]\n', '42\n', 'None\n', '"None"\n', '{}\n', '[]\n',
    'a:\n  - "x"\n  - {k: 1}\n', 'a:\n  42\n', '- - 1\n  - 2\n',
    '-\n    a: 1\n', '  a: 1\n  b: 2\n',
    '{a:[1], b:{c: 2}}\n', '{"a":1,"b":[2]}\n',
    '[1, 2,]\n', '{a: 1,}\n', '[1,\n  2,\n]\n',
    'for: 1\nif: 2\nelse: 3\nnot: 4\n',
    'a: "# not a comment" # comment\n', '# comment\na: 1\n',
    'a: 1\r\nb: 2\r\n', '"café": "日本語"\n',
    'a: "\\08"\nb: "\\09"\nc: "\\0x"\n',
    'a: \'a "quote"\'\n', 'a: "it\'s fine"\n',
    'a: "a\\\"b"\n', 'a: "\\x00\\u0085\\U0001f600"\n',
    '"é": "exact, not folded"\n', '"ｎａｍｅ": 1\n',
])
def test_profile_members_are_valid_records(text):
    assert yapyon.is_yamlplus(text)
    yamlplus.check(text)
    assert yamlplus.loads(text) == yapyon.loads_record(text.replace('\r\n', '\n'))
    output = yamlplus.normalize(text)
    assert yapyon.is_yamlplus(output)
    assert yamlplus.loads(output) == yamlplus.loads(text)
    assert yamlplus.normalize(output) == output


@pytest.mark.parametrize("number, expected", [
    ('0', 0), ('-0', 0), ('+0', 0), ('12', 12), ('-12', -12), ('+3', 3),
    ('0xff', 255), ('0xABC', 2748), ('3.10', 3.1), ('.5', .5),
    ('1.', 1.0), ('-.5', -.5), ('+1.0', 1.0), ('1.0e+5', 100000.0),
    ('1.0E-5', .00001), ('-0.0', -0.0),
])
def test_numeric_spellings_preserve_value_and_type(number, expected):
    got = yamlplus.loads(f'a: {number}\n')['a']
    assert type(got) is type(expected)
    assert got == expected
    assert yamlplus.normalize(f'a: {number}\n') == f'a: {number}\n'
    if number == '-0.0':
        assert math.copysign(1, got) < 0


@pytest.mark.parametrize("text", [
    '', '# only a comment\n', 'a: no\n', 'a: null\n', 'a: [1\n',
    'a:\n', '1: "numeric key"\n', 'True: 1\n', 'a: 1\na: 2\n',
    '"": 1\n', '"@metadata": 1\n', '"__private__": 1\n',
    '---\na: 1\n', 'a: "\\/"\n', 'a:\n- 1\n',
])
def test_invalid_yapyon_is_not_profile_input(text):
    assert not yapyon.is_yamlplus(text)
    with pytest.raises(AkanError):
        yamlplus.loads(text)


@pytest.mark.parametrize("text, reason", [
    ('a: """x"""\n', 'YAML syntax'), ('a: "\\101"\n', 'escape'),
    ('a: "\\\'"\n', 'escape'), ('a: {+}\n', 'multimap'),
    ('+ a: 1\n', 'multimap'), ('"a":1\n', 'YAML syntax'),
    ('a:1\nb: 2\n', 'YAML syntax'), ('a: b"a: b"\n', 'YAML syntax'),
    ('a: r"a: b"\n', 'YAML syntax'), ("a: 'it\\'s'\n", 'YAML syntax'),
    ('{"a"\n: 1}\n', 'same line'), ('{a # comment\n: 1}\n', 'same line'),
])
def test_valid_records_outside_profile_are_refused(text, reason):
    yapyon.loads_record(text)
    assert not yapyon.is_yamlplus(text)
    with pytest.raises(AkanError, match=reason):
        yamlplus.loads(text)


@pytest.mark.parametrize("text", [
    'a: y"x"\n', 'a: yt"x"\n', 'a: (b)\nb: 1\n',
    'a: (1)\n', 'a<x>: {}\n', 'a: __int__("1")\n',
    'a: [x for x in [1]]\n', 'a: 1 if True else 2\n',
    'a: {} | {}\n', 'a: {}\n| {}\n',
])
def test_profile_never_evaluates_non_records(text):
    assert not yapyon.is_yamlplus(text)
    with pytest.raises(AkanError):
        yamlplus.loads(text)
    with pytest.raises(AkanError):
        yamlplus.normalize(text)


@pytest.mark.parametrize('raw', ['\x00', '\x07', '\x0b', '\x1f', '\x7f',
                                 '\x85', '\x9f', '\u2028', '\u2029',
                                 '\ufeff', '\ufffe', '\uffff'])
def test_non_shared_raw_characters_require_escapes(raw):
    assert not yapyon.is_yamlplus(f'a: "{raw}"\n')
    assert not yapyon.is_yamlplus(f'a: 1 # {raw}\n')
    output = yamlplus.dumps({'a': raw})
    assert raw not in output
    assert yamlplus.loads(output) == {'a': raw}


WORDS = ['y', 'Y', 'yes', 'Yes', 'YES', 'n', 'N', 'no', 'No', 'NO',
         'true', 'TRUE', 'false', 'FALSE', 'on', 'On', 'ON', 'off', 'Off', 'OFF',
         'null', 'Null', 'NULL']


@pytest.mark.parametrize('word', WORDS)
def test_automatic_key_conversion_is_legal_but_warns(word):
    warnings = []
    text = f'{word}: "hello"\n'
    assert yapyon.is_yamlplus(text, warn=warnings.append, source='settings.yaml')
    assert len(warnings) == 1
    assert 'shiran: settings.yaml:1:0:' in warnings[0]
    assert 'automatically convert' in warnings[0]
    assert 'collide' in warnings[0]
    assert yamlplus.loads(text) == {word: 'hello'}
    warnings.clear()
    output = yamlplus.normalize(text, warn=warnings.append)
    assert output == f'"{word}": "hello"\n'
    assert len(warnings) == 1 and 'quoting' in warnings[0]
    warnings.clear()
    assert yamlplus.normalize(output, warn=warnings.append) == output
    assert warnings == []


@pytest.mark.parametrize('word', ['YeS', 'nO', 'oN', 'OfF', 'NuLl', 'none',
                                  'nan', 'inf', 'infinity', 'ordinary'])
def test_warnings_follow_yaml_patterns_not_lowercased_guessing(word):
    warnings = []
    assert yamlplus.loads(f'{word}: 1\n', warn=warnings.append) == {word: 1}
    assert warnings == []


def test_reading_warns_about_possible_collisions_without_coalescing_keys():
    warnings = []
    got = yamlplus.loads('yes: 1\non: 2\nno: 3\noff: 4\n', warn=warnings.append)
    assert list(got.items()) == [('yes', 1), ('on', 2), ('no', 3), ('off', 4)]
    assert len(warnings) == 4


def test_quoted_keys_are_exact_non_names_and_do_not_warn():
    warnings = []
    got = yamlplus.loads('block:\n  "yes": 1\n  normal: 2\n', warn=warnings.append)
    assert warnings == []
    assert yapyon.lookup(got, got, 'block["yes"]') == 1
    assert yapyon.lookup(got, got, 'block.normal') == 2
    with pytest.raises(AkanError):
        yapyon.lookup(got, got, 'block.yes')


def test_selected_quoting_changes_name_visibility_not_key_text():
    source = 'block:\n  yes: 1\n  normal: 2\n'
    before = yamlplus.loads(source)
    after = yamlplus.loads(yamlplus.normalize(source))
    assert before == after
    assert yapyon.lookup(before, before, 'block.yes') == 1
    with pytest.raises(AkanError):
        yapyon.lookup(after, after, 'block.yes')
    assert yapyon.lookup(after, after, 'block["yes"]') == 1


@pytest.mark.parametrize('key', ['yes', 'null', 'y', '123', '-12', '1.5',
                                  '1e5', '0b101', '0o17', '0xff', '.NaN',
                                  '2001-12-15', '2001-12-15T02:59:43.1Z',
                                  '<<', '='])
def test_host_output_warns_and_quotes_every_automatic_key_type(key):
    warnings = []
    text = yamlplus.dumps({key: 'hello'}, warn=warnings.append)
    assert text.startswith('"')
    assert yamlplus.loads(text) == {key: 'hello'}
    assert len(warnings) == 1
    assert 'at root[' in warnings[0] and 'quoting' in warnings[0]


def test_none_quotation_is_part_of_the_value_not_a_post_load_guess():
    source = 'missing: None\nword: "None"\nother: \'None\'\ntext: "null"\n'
    got = yamlplus.loads(source)
    assert got == {'missing': None, 'word': 'None', 'other': 'None', 'text': 'null'}
    assert yamlplus.normalize(source) == source
    text = yamlplus.dumps(got)
    assert 'missing: None\n' in text
    assert 'word: "None"\n' in text and 'other: "None"\n' in text
    assert yamlplus.loads(text) == got


def test_source_normalization_keeps_comments_and_other_literal_lexemes():
    source = "# comment\na: 'hello'\nb: 3.10\nc: 0xff\nyes: None\n"
    assert yamlplus.normalize(source) == "# comment\na: 'hello'\nb: 3.10\nc: 0xff\n\"yes\": None\n"


@pytest.mark.parametrize('value', [1e20, 1e-20, .5, -0.0, 0.0, 1.23456789012345])
def test_host_floats_have_shared_dotted_exponent_spellings(value):
    text = yamlplus.dumps(value)
    assert '.' in text
    assert yapyon.is_yamlplus(text)
    got = yamlplus.loads(text)
    assert type(got) is float and got == value
    if value == 0:
        assert math.copysign(1, got) == math.copysign(1, value)


def test_host_writer_preserves_order_types_unicode_and_acyclic_sharing():
    shared = ['line\nbreak', True, None, 1, 1.0, 'None', '日本語']
    data = {'first': shared, 'second': shared}
    text = yamlplus.dumps(data)
    got = yamlplus.loads(text)
    assert list(got) == ['first', 'second']
    assert got == data
    assert got['first'] is not got['second']
    assert type(got['first'][3]) is int and type(got['first'][4]) is float
    assert shared[0] == 'line\nbreak'


@pytest.mark.parametrize('data', [{1: 'x'}, {True: 'x'}, {1.5: 'x'}, {None: 'x'}])
def test_host_writer_does_not_stringify_numeric_or_null_keys(data):
    with pytest.raises(TypeError, match='key must be a string'):
        yamlplus.dumps(data)


@pytest.mark.parametrize('data', [yapyon.OrderedMultimap(), {'nested': yapyon.OrderedMultimap()}])
def test_profile_unsupported_record_types_refuse_before_stream_output(data):
    stream = io.StringIO('original')
    with pytest.raises(AkanError):
        yamlplus.dump(data, stream)
    assert stream.getvalue() == 'original'


def test_stream_operations_follow_shared_export_contract():
    stream = io.StringIO()
    assert yamlplus.dump({'name': 'hello'}, stream) is None
    assert stream.getvalue() == 'name: "hello"\n'
    stream.seek(0)
    assert yamlplus.load(stream) == {'name': 'hello'}

    class ShortWrite:
        def write(self, text):
            return len(text) - 1

    with pytest.raises(OSError, match='complete write'):
        yamlplus.dump({}, ShortWrite())
    with pytest.raises(TypeError, match='callable text write'):
        yamlplus.dump({}, object())


def test_file_source_is_inherited_and_explicit_source_wins(tmp_path):
    path = tmp_path / 'settings.yaml'
    path.write_text('a: 1\nb: "\\101"\n', encoding='utf-8')
    with path.open(encoding='utf-8') as fp:
        with pytest.raises(AkanError) as caught:
            yamlplus.load(fp)
    assert caught.value.source == str(path)
    assert (caught.value.line, caught.value.col) == (2, 4)
    with path.open(encoding='utf-8') as fp:
        with pytest.raises(AkanError) as caught:
            yamlplus.load(fp, source='chosen')
    assert caught.value.source == 'chosen'


def test_whole_document_predicate_rejects_syntax_and_lexical_errors():
    assert not yapyon.is_yamlplus('')
    assert not yapyon.is_yamlplus('a: [1,\n')
    assert not yapyon.is_yamlplus('a: f"bad"\n')
    for work in (yamlplus.check, yamlplus.loads, yamlplus.normalize):
        with pytest.raises(TypeError, match='warn must be callable'):
            work('a: 1\n', warn=1)
    with pytest.raises(TypeError, match='text must be a string'):
        yapyon.is_yamlplus(b'a: 1\n')


def test_predicate_does_not_swallow_a_warning_callback_exception():
    def refusing_callback(message):
        raise AkanError('callback failed', 0, 0)

    with pytest.raises(AkanError, match='callback failed'):
        yapyon.is_yamlplus('yes: 1\n', warn=refusing_callback)


def test_implicit_key_length_counts_quotes_escapes_and_space_before_colon():
    assert yapyon.is_yamlplus('a' * 1024 + ': 1\n')
    assert not yapyon.is_yamlplus('a' * 1025 + ': 1\n')
    assert yapyon.is_yamlplus('"' + 'a' * 1022 + '": 1\n')
    assert not yapyon.is_yamlplus('"' + 'a' * 1023 + '": 1\n')
    assert not yapyon.is_yamlplus('a' + ' ' * 1024 + ': 1\n')
    with pytest.raises(AkanError, match='1,024'):
        yamlplus.dumps({'not-a-name-' * 100: 1})
    with pytest.raises(AkanError, match='1,024'):
        yamlplus.dumps({'\x00' * 200: 1})


def test_bounded_export_refusals_and_cycles_are_shared():
    with pytest.raises(ValueError, match='max_depth'):
        yamlplus.dumps({'a': {'b': 1}}, max_depth=1)
    with pytest.raises(ValueError, match='max_size'):
        yamlplus.dumps({'a': '\x00' * 10}, max_size=30)
    with pytest.raises(ValueError, match='max_size'):
        yamlplus.normalize('a: 1\n', max_size=4)
    cycle = []
    cycle.append(cycle)
    with pytest.raises(AkanError, match='cycle'):
        yamlplus.dumps(cycle)
    with pytest.raises(ValueError, match='finite'):
        yamlplus.dumps(float('inf'))


def test_long_decimal_uses_shared_conversion_and_warning_not_host_limit():
    text = '1' * 4500 + '\n'
    warnings = []
    value = yamlplus.loads(text, warn=warnings.append)
    assert len(warnings) == 1 and '4,500 digits' in warnings[0]
    assert yamlplus.dumps(value) == text


def cli(text, *args):
    return subprocess.run([sys.executable, '-m', 'yapyon', 'yamlplus', *args],
                          input=text, text=True, capture_output=True)


def test_cli_checker_warns_without_payload_or_failure():
    result = cli('yes: "hello"\n')
    assert result.returncode == 0 and result.stdout == ''
    assert 'shiran:' in result.stderr and 'collide' in result.stderr


def test_cli_write_quotes_without_putting_diagnostics_in_payload():
    result = cli('yes: None\nword: "None"\n', '--write')
    assert result.returncode == 0
    assert result.stdout == '"yes": None\nword: "None"\n'
    assert result.stderr.count('shiran:') == 1
    assert 'shiran:' not in result.stdout


def test_cli_failure_has_location_and_no_payload(tmp_path):
    path = tmp_path / 'bad.yaml'
    path.write_text('a: "\\101"\n', encoding='utf-8')
    result = cli('', '--write', str(path))
    assert result.returncode == 1 and result.stdout == ''
    assert f'{path}:1:4:' in result.stderr
    assert 'Traceback' not in result.stderr


def test_cli_output_limit_is_a_diagnostic_not_a_traceback(monkeypatch, capsys):
    def limited(text, **kwargs):
        raise ValueError('serialized UTF-8 exceeds max_size')

    monkeypatch.setattr(yamlplus, 'normalize', limited)
    monkeypatch.setattr(sys, 'stdin', io.StringIO('a: 1\n'))
    assert yamlplus.main(['yamlplus', '--write']) == 1
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'akan: line 1, col 0:' in captured.err and 'max_size' in captured.err
    assert 'Traceback' not in captured.err


def test_existing_yapyon_loading_and_writing_do_not_gain_profile_warnings():
    warnings = []
    assert yapyon.loads('yes: 1\non: 2\n', warn=warnings.append) == {'yes': 1, 'on': 2}
    assert yapyon.dumps({'yes': 1}, warn=warnings.append) == 'yes: 1\n'
    assert warnings == []
    assert 'is_yamlplus' in yapyon.__all__


def test_normative_document_python_example_executes():
    text = (Path(__file__).resolve().parents[1] / 'docs' / 'YAMLPLUS.md').read_text()
    example = text.split('```python\n', 1)[1].split('```', 1)[0]
    exec(compile(example, 'docs/YAMLPLUS.md', 'exec'), {})
