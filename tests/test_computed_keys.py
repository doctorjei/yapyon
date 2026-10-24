"""SPEC §7: key values, visibility, dependencies, and record output."""

import copy
import itertools
import json
import tomllib

import pytest
import yaml

import yapyon
from yapyon import AkanError, loads, loads_record, lookup


def test_computed_key_reads_a_forward_value():
    assert loads('y"{name}": 1\nname: "x"\n') == {"x": 1, "name": "x"}


@pytest.mark.parametrize("order", list(itertools.permutations([
    'name: y"{base}"', 'base: "x"', 'data: {y"{name}": 42}',
    'answer: (data[name])'])))
def test_keys_and_subscripts_are_independent_of_mapping_order(order):
    assert loads("\n".join(order))["answer"] == 42


@pytest.mark.parametrize("key", ['"x"', 'y"x"', 'ry"x"'])
def test_quoted_and_computed_keys_never_become_names(key):
    with pytest.raises(AkanError, match="no value named"):
        loads(f'{key}: 1\nanswer: y"{{x}}"\n')
    with pytest.raises(AkanError, match="not names"):
        loads(f'data: {{{key}: 1}}\nanswer: (data.x)\n')
    assert loads(f'data: {{{key}: 1}}\nanswer: (data["x"])\n')["answer"] == 1


def test_quoted_key_does_not_shadow_an_outer_name():
    text = 'x: "outer"\ndata:\n  "x": "inner"\n  answer: y"{x}"\n'
    assert loads(text)["data"]["answer"] == "outer"


def test_key_text_is_available_through_relative_key_reference():
    text = 'name: "a-b"\ndata:\n  y"{name}":\n    key: y"{__PARENT__.__KEY__}"\n'
    assert loads(text)["data"]["a-b"]["key"] == "a-b"


@pytest.mark.parametrize("text", [
    'x: 1\ny"x": 2', 'y"x": 1\nx: 2',
    'name: "x"\ny"{name}": 1\n"x": 2',
    'name: "x"\ny"{name}": 1\ny"x": 2',
])
def test_computed_collisions_in_one_mapping_are_duplicates(text):
    with pytest.raises(AkanError, match="duplicate key 'x'"):
        loads(text)


@pytest.mark.parametrize("key", ["", "@type", "__x__"])
def test_computed_key_text_is_validated_after_resolution(key):
    with pytest.raises(AkanError):
        loads(f'name: {json.dumps(key)}\ny"{{name}}": 1\n')


def test_computed_key_cycles_reach_the_existing_cycle_diagnostic():
    with pytest.raises(AkanError, match="cycle"):
        loads('data: {y"{data[\"x\"]}": "x"}')


def test_key_size_is_subject_to_the_rendering_ceiling():
    with pytest.raises(AkanError, match="size ceiling"):
        loads('name: "abcdef"\ny"{name}": 1', max_size=5)


def test_a_necessary_bracket_is_silent_but_an_avoidable_one_warns():
    warnings = []
    loads('data: {"x": 1}\nanswer: (data["x"])', warn=warnings.append)
    assert warnings == []
    loads('data: {x: 1}\nanswer: (data["x"])', warn=warnings.append)
    assert len(warnings) == 1
    assert "long way" in warnings[0]


def test_subscripts_use_exact_text_before_folded_names():
    text = 'data: {name: 1, "ｎａｍｅ": 2}\na: (data["ｎａｍｅ"])\nb: (data.name)'
    result = loads(text)
    assert (result["a"], result["b"]) == (2, 1)


@pytest.mark.parametrize("transform", [lambda x: x, copy.copy, copy.deepcopy, lambda x: x.copy()])
def test_loaded_mapping_keeps_visibility_for_lookup(transform):
    data = transform(loads_record('named: 1\n"quoted": 2'))
    assert isinstance(data, dict)
    assert data == {"named": 1, "quoted": 2}
    assert lookup(data, data, "named") == 1
    assert lookup(data, data, '__ROOT__["quoted"]') == 2
    with pytest.raises(AkanError, match="no value named"):
        lookup(data, data, "quoted")


def test_mutating_loaded_values_does_not_promote_a_quoted_key():
    data = loads_record('"quoted": 1')
    data.update(quoted=2)
    data |= {"quoted": 3}
    with pytest.raises(AkanError):
        lookup(data, data, "quoted")
    del data["quoted"]
    data["quoted"] = 4
    assert lookup(data, data, "quoted") == 4


def test_expand_emits_computed_keys_as_quoted_literals():
    text = 'name: "model"\ndata: {y"{name}": 1}'
    expanded = yapyon.expand_record(text)
    result = loads_record(expanded)
    assert result["data"] == {"model": 1}
    assert lookup(result, result, 'data["model"]') == 1
    with pytest.raises(AkanError):
        lookup(result, result, "data.model")


@pytest.mark.parametrize("key", ['a-b', 'a.b', 'a/b', 'a~b', 'a"b', 'a\\b',
                                  'line\nbreak', 'tab\tkey', '\x00', 'é', 'True'])
def test_every_writer_round_trips_key_text(key):
    text = 'data: {' + json.dumps(key, ensure_ascii=False) + ': 42}\n'
    for writer, reader in [("json", json.loads), ("yaml", yaml.safe_load),
                           ("toml", tomllib.loads), ("yapyon", loads_record)]:
        source = text + f'out: data.__as_{writer}__()\n'
        output = loads(source)["out"]
        assert reader(output) == {key: 42}


@pytest.mark.parametrize("writer,reader", [("json", json.loads), ("toml", tomllib.loads)])
def test_metadata_paths_escape_key_text_without_collisions(writer, reader):
    text = ('data: {"ports/0": 0x1, ports: [0x2], "a~b": 0x3}\n'
            f'out: data.__as_{writer}__()')
    written = reader(loads(text)["out"])
    assert written["@_lexemes"] == {"ports~10": "0x1", "ports/0": "0x2", "a~0b": "0x3"}


def test_toml_omission_metadata_escapes_the_key_too():
    text = 'data: {"a/b": None}\nout: data.__as_toml__()'
    assert tomllib.loads(loads(text)["out"]) == {"@_lexemes": {"a~1b": "None"}}


@pytest.mark.parametrize("text", [
    '\"\"\"a\\nb\"\"\": 1',
    'outer:\n  \"\"\"a\n    b\"\"\": 1',
    '- \"\"\"a\n    b\"\"\": 1',
    '+ \"\"\"a\n    b\"\"\": 1',
])
def test_multiline_key_lexemes_survive_record_normalization(text):
    emitted = yapyon.emit(yapyon.parse(text))
    assert loads_record(emitted) == loads_record(text)
    assert yapyon.emit(yapyon.parse(emitted)) == emitted


def test_multimap_computed_keys_keep_the_list_view():
    result = loads('name: "x"\nmm:\n  + y"{name}": 1\n  + "x": 2\na: (mm["x"])\nb: (mm.x)')
    assert result["a"] == [1, 2]
    assert result["b"] == []
