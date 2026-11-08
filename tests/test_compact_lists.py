"""SPEC §14.1: density-gated hanging yapyon lists, without changing data."""

import json
import tomllib

import pytest

import yapyon
from yapyon._width import text_width
from yapyon.record import normalize


NUMBERS = list(range(1, 31))
SOURCE = 'numbers: [' + ', '.join(map(str, NUMBERS)) + ']\n'
EXPECTED = (
    'numbers: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, '
    '17, 18, 19, 20, 21, 22, 23, 24, 25,\n'
    '          26, 27, 28, 29, 30]\n'
)


def test_ordinary_one_line_form_remains_first():
    assert yapyon.dumps({'numbers': [1, 2, 3]}) == 'numbers: [1, 2, 3]\n'
    assert yapyon.dumps({'numbers': []}) == 'numbers: []\n'


def test_pack_greedily_at_the_exact_full_line_boundary():
    assert normalize(SOURCE) == EXPECTED
    assert [text_width(line) for line in EXPECTED.splitlines()] == [100, 29]
    assert yapyon.loads_record(EXPECTED) == {'numbers': NUMBERS}
    assert normalize(EXPECTED) == EXPECTED


def test_root_list_and_marked_value_use_the_same_layout():
    root = yapyon.dumps(NUMBERS)
    marked = yapyon.dumps([{'numbers': NUMBERS}])
    assert root.startswith('[1, 2, 3, ')
    assert root.splitlines()[1].startswith(' ')
    assert marked.startswith('- numbers: [1, 2, 3, ')
    assert all(text_width(line) <= 100 for line in (root + marked).splitlines())
    assert yapyon.loads_record(root) == NUMBERS
    assert yapyon.loads_record(marked) == [{'numbers': NUMBERS}]
    assert normalize(marked) == marked


def test_multimap_values_use_the_same_layout():
    source = '+ numbers: [' + ', '.join(map(str, NUMBERS)) + ']\n'
    text = normalize(source)
    assert text.startswith('+ numbers: [1, 2, 3, ')
    assert text.splitlines()[1].startswith(' ' * len('+ numbers: ['))
    assert yapyon.loads_record(text) == yapyon.loads_record(source)
    assert normalize(text) == text


def test_final_singleton_remainder_is_exempt_from_density():
    values = ['a' * 28, 'b' * 28, 'c' * 28, 'd' * 28]
    text = yapyon.dumps({'xs': values})
    assert text.startswith('xs: [')
    assert len(text.splitlines()) == 2
    assert text.splitlines()[-1] == ' ' * 5 + '"' + 'd' * 28 + '"]'
    assert yapyon.loads_record(text) == {'xs': values}


@pytest.mark.parametrize('dense_before_tail,accepted', [(2, False), (3, True)])
def test_exact_seventy_five_percent_density_boundary(dense_before_tail, accepted):
    pair = ['d' * 38, 'd' * 38]
    values = pair * (dense_before_tail - 1) + ['s' * 88] + pair + ['tail' * 10]
    text = yapyon.dumps({'xs': values})
    assert text.startswith('xs: [') is accepted
    if not accepted:
        assert text.startswith('xs:\n  - ')
    assert yapyon.loads_record(text) == {'xs': values}


def test_singleton_only_rows_cannot_qualify_by_the_tail_exemption():
    text = yapyon.dumps({'xs': ['x' * 60] * 4})
    assert text.startswith('xs:\n  - ')


def test_nested_short_lists_are_indivisible_top_level_elements():
    values = [[n, n + 1] for n in range(1, 25, 2)]
    text = yapyon.dumps({'xs': values})
    assert text.startswith('xs: [[')
    assert len(text.splitlines()) > 1
    for first, last in values:
        assert any(f'[{first}, {last}]' in line for line in text.splitlines())
    assert yapyon.loads_record(text) == {'xs': values}
    assert normalize(text) == text


def test_nested_descendants_do_not_inflate_the_density_count():
    values = [list(range(15))] * 4
    text = yapyon.dumps({'xs': values})
    assert text.startswith('xs:\n  - [')


@pytest.mark.parametrize('tail', ['{}', '{+}', '{a: 1}', '[[{a: 1}]]'])
def test_mapping_and_multimap_exclusion_is_recursive_even_when_late(tail):
    source = 'xs: [' + ', '.join(map(str, NUMBERS)) + ', ' + tail + ']\n'
    text = normalize(source)
    assert text.startswith('xs:\n  - 1\n')
    assert yapyon.loads_record(text) == yapyon.loads_record(source)


def test_nested_list_needing_multiline_layout_disqualifies_its_parent():
    values = [NUMBERS, [1, 2], [3, 4]]
    text = yapyon.dumps(values)
    assert text.startswith('- [1, 2, 3, ')
    assert not text.startswith('[[')
    assert yapyon.loads_record(text) == values


def test_multiline_scalar_spelling_is_not_rewritten_to_force_flow():
    source = 'xs: [' + ', '.join(map(str, NUMBERS)) + ', """a\n  b"""]\n'
    text = normalize(source)
    assert text.startswith('xs:\n  - 1\n')
    assert '"""a\n' in text
    assert yapyon.loads_record(text) == yapyon.loads_record(source)


@pytest.mark.parametrize('key', ['界' * 3, 'é' * 3, '❤️' * 3])
def test_hanging_alignment_uses_display_columns_not_string_length(key):
    text = yapyon.dumps({key: NUMBERS})
    lines = text.splitlines()
    assert len(lines) > 1 and lines[0].endswith(',')
    first_column = text_width(lines[0].split('[', 1)[0]) + 1
    assert len(lines[1]) - len(lines[1].lstrip(' ')) == first_column
    assert all(text_width(line) <= 100 for line in lines)
    assert yapyon.loads_record(text) == {key: NUMBERS}


def test_preserve_scalar_and_key_lexemes_in_a_compact_list():
    literals = ['0xff', '3.10', "'single'", 'r"a\\nb"', 'hex"6869"'] * 5
    text = normalize('"quoted": [' + ', '.join(literals) + ']\n')
    assert text.startswith('"quoted": [')
    assert all(literal in text for literal in literals)
    assert normalize(text) == text


def test_shared_yapyon_entry_points_and_non_evaluating_source(monkeypatch):
    expected = yapyon.dumps({'numbers': NUMBERS})
    assert expected == EXPECTED
    assert yapyon.emit(yapyon.parse(SOURCE)) == expected
    assert yapyon.expand_record(SOURCE) == expected
    doc = SOURCE + 'out: numbers.__as_yapyon__()\n'
    assert yapyon.loads_record(yapyon.loads(doc)['out']) == NUMBERS
    import yapyon.resolver as resolver

    def refuse(*args, **kwargs):
        raise AssertionError('source layout evaluated a document')

    monkeypatch.setattr(resolver, 'resolve', refuse)
    tree = yapyon.parse(SOURCE + 'later: y"{$HOME}"\n')
    saved = tree.to_source()
    assert saved.startswith(expected)
    assert 'y"{$HOME}"' in saved
    assert yapyon.parse(saved).to_source() == saved


def test_export_budget_counts_compact_indentation_punctuation_and_newlines():
    value = {'界': NUMBERS}
    text = yapyon.dumps(value)
    size = len(text.encode('utf-8'))
    assert yapyon.dumps(value, max_size=size) == text
    with pytest.raises(ValueError, match='max_size'):
        yapyon.dumps(value, max_size=size - 1)


def test_rejected_large_hanging_candidate_does_not_consume_fallback_budget():
    value = {'k' * 80: NUMBERS + ['z' * 80]}
    text = yapyon.dumps(value)
    size = len(text.encode('utf-8'))
    assert text.startswith('k' * 80 + ':\n')
    assert yapyon.dumps(value, max_size=size) == text
    with pytest.raises(ValueError, match='max_size'):
        yapyon.dumps(value, max_size=size - 1)


def test_accepted_hanging_layout_cannot_change_to_block_to_evade_byte_limit():
    key, values = 'k' * 80, NUMBERS
    text = yapyon.dumps({key: values})
    block_size = len(key + ':\n' + ''.join(f'  - {value}\n' for value in values))
    assert len(text.encode('utf-8')) > block_size
    with pytest.raises(ValueError, match='max_size'):
        yapyon.dumps({key: values}, max_size=block_size)


def test_variation_selector_at_a_scalar_chunk_boundary_cannot_overflow_a_row():
    value = 'x' * 91 + '́' * 932 + '❤️'
    values = ['d' * 38] * 6 + [value] + ['d' * 38] * 3
    text = yapyon.dumps({'xs': values})
    assert text.startswith('xs:\n')
    assert all(text_width(line) <= 100 for line in text.splitlines())
    assert yapyon.loads_record(text) == {'xs': values}


def test_unresolved_list_elements_are_saved_without_evaluation():
    source = 'xs: [' + ', '.join(['y"{$HOME}"'] * 20) + ']\n'
    tree = yapyon.parse(source)
    saved = tree.to_source()
    assert saved.startswith('xs: [y"{$HOME}", ')
    assert len(saved.splitlines()) > 1
    assert yapyon.parse(saved).to_source() == saved
    assert tree.resolve(env={'HOME': '/example'}) == {'xs': ['/example'] * 20}


def test_other_format_writer_layouts_are_unchanged():
    doc = SOURCE + ('j: numbers.__as_json__(lexemes=False)\n'
                    'y: numbers.__as_yaml__()\n'
                    't: __as_toml__(__ROOT__.settings)\n'
                    'settings: {numbers: (numbers)}\n')
    out = yapyon.loads(doc)
    assert json.loads(out['j']) == NUMBERS
    assert out['j'].startswith('[\n  1,\n')
    assert out['y'].startswith('- 1\n- 2\n')
    assert tomllib.loads(out['t']) == {'numbers': NUMBERS}
    assert out['t'].startswith('numbers = [\n  1,\n')
