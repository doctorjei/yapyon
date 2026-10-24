"""GRAMMAR §G6–§G7: literal and deferred string keys."""

import pytest

from yapyon import AkanError, is_record, tier_of
from yapyon.lexer import tokenize
from yapyon.parser import Mapping, MultiMap, Scalar, YString, parse


@pytest.mark.parametrize("spelling", ['"some-key"', "'some-key'", '"""some-key"""'])
def test_plain_quoted_keys_are_literal_non_names(spelling):
    tree = parse(f"{spelling}: 1\n")
    pair = tree.pairs[0]
    assert pair.key == "some-key"
    assert not pair.named
    assert pair.lexeme == spelling
    assert tree.by_key["some-key"].value == 1
    assert is_record(f"{spelling}: 1\n")
    assert tier_of(f"{spelling}: 1\n") == 1


@pytest.mark.parametrize("prefix", ["y", "ry"])
def test_computed_keys_remain_unresolved_at_parse(prefix):
    tree = parse(f'name: "x"\n{prefix}"{{name}}": 1\n', source="keys.yap")
    pair = tree.pairs[1]
    assert isinstance(pair.key, YString)
    assert not pair.named
    assert pair.key.source == "keys.yap"
    assert pair.source == "keys.yap"
    assert list(tree.by_key) == ["name"]
    assert tier_of(f'{prefix}"x": 1\n') == 2


def test_lexing_distinguishes_string_keys_from_string_values():
    tokens = tokenize('"x": "value"\n')
    assert [t.kind for t in tokens] == ["QKEY", "COLON", "STRING", "NEWLINE", "EOF"]
    assert isinstance(parse('"value"'), Scalar)


def test_string_keys_work_in_flow_mappings_and_multimaps():
    tree = parse('{"x-y": 1, y"z": 2}')
    assert isinstance(tree, Mapping)
    assert tree.pairs[0].key == "x-y"
    assert isinstance(tree.pairs[1].key, YString)
    tree = parse('+ "x-y": 1\n+ "x-y": 2\n')
    assert isinstance(tree, MultiMap)
    assert [p.key for p in tree.entries] == ["x-y", "x-y"]


def test_quoted_names_are_not_folded():
    tree = parse('name: 1\n"ｎａｍｅ": 2\n')
    assert [p.key for p in tree.pairs] == ["name", "ｎａｍｅ"]


@pytest.mark.parametrize("text", ['name: 1\n"name": 2\n', '"x": 1\n"\\x78": 2\n'])
def test_equal_literal_keys_are_duplicates_regardless_of_kind(text):
    with pytest.raises(AkanError, match="duplicate key"):
        parse(text)


@pytest.mark.parametrize("key", ['""', '"@type"', '"__hidden__"'])
def test_reserved_literal_key_text_is_refused(key):
    with pytest.raises(AkanError):
        parse(f"{key}: 1\n")


@pytest.mark.parametrize("key", ['r"x"', 'b"x"', 'yb"x"', 'yt"x"', "42", "True", "(1)"])
def test_only_the_approved_string_key_forms_are_admitted(key):
    with pytest.raises(AkanError):
        parse(f"{key}: 1\n")


@pytest.mark.parametrize("key", ['"x"', 'y"x"', 'ry"x"'])
def test_a_string_key_can_carry_a_slot_label(key):
    tree = parse(f"{key} < source . branch > : {{}}\n")
    assert tree.pairs[0].value.label == ("source", "branch")


@pytest.mark.parametrize("key", ['"x"', 'y"x"'])
@pytest.mark.parametrize("prefix", ['- 1\n', '+ a: 1\n'])
def test_mixing_string_pairs_with_another_block_kind_is_akan(key, prefix):
    with pytest.raises(AkanError, match="not both"):
        parse(prefix + f'{key}: 2\n')


def test_key_holes_participate_in_tier_detection():
    assert tier_of('y"{$HOME}": 1') == 3
    assert tier_of('y"{NAME()}": 1') == 4
