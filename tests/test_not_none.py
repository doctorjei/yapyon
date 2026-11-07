"""SPEC §5.1.6: explicit recursive None removal before serialization."""

import json
import tomllib

import pytest
import yaml

from yapyon import (AkanError, OrderedMultimap, Template, loads, loads_record)


DOC = '''foo:
  gone: None
  nested:
    gone: None
    values: [None, 0, False, "", "None", {}, [], [None], {gone: None}]
  empty: {gone: None}
  empty_list: [None]
'''
CLEAN = {"nested": {"values": [0, False, "", "None", {}, [], [], {}]},
         "empty": {}, "empty_list": []}


def test_recursively_remove_only_none_and_leave_an_independent_copy():
    data = loads(DOC + 'clean: foo.__not_none__()\n')
    assert data["clean"] == CLEAN
    assert data["foo"]["gone"] is None
    assert data["foo"]["nested"]["values"][0] is None
    assert data["foo"]["empty"] == {"gone": None}
    assert data["foo"]["empty_list"] == [None]
    data["clean"]["nested"]["values"][-1]["new"] = 1
    assert data["foo"]["nested"]["values"][-1] == {"gone": None}


def test_multimap_removes_individual_none_entries_and_preserves_order():
    data = loads('foo: {+ k: None, k: {gone: None, xs: [None, 2]}, '
                 'j: None, k: 3, j: 0}\nclean: foo.__not_none__()\n')
    assert isinstance(data["clean"], OrderedMultimap)
    assert [(e.key, e.value) for e in data["clean"]] == [
        ("k", {"xs": [2]}), ("k", 3), ("j", 0)]
    assert data["foo"].count("k") == 3
    assert data["foo"].get("k")[1].value["xs"] == [None, 2]


@pytest.mark.parametrize("name,read", [
    ("json", json.loads), ("toml", tomllib.loads),
    ("yaml", yaml.safe_load), ("yapyon", loads_record),
])
def test_chain_cleaned_data_into_each_serializer(name, read):
    data = loads(DOC + f'body: foo.__not_none__().__as_{name}__()\n')
    assert read(data["body"]) == CLEAN
    assert data["foo"]["gone"] is None


def test_serializers_still_keep_none_without_an_explicit_transform():
    data = loads(DOC + 'body: foo.__as_json__()\n')
    assert json.loads(data["body"]) == data["foo"]


@pytest.mark.parametrize("expression", [
    "__not_none__(foo)", "__as_json__(__not_none__(foo))",
    "foo.__not_none__().__not_none__()",
])
def test_function_spelling_nesting_and_repeated_calls(expression):
    data = loads(DOC + f'clean: {expression}\n')
    value = data["clean"]
    assert (json.loads(value) if isinstance(value, str) else value) == CLEAN


def test_wait_for_keys_and_values_and_preserve_literal_spellings():
    data = loads('body: foo.__not_none__().__as_yapyon__()\n'
                 'foo: {y"{key}": (nothing), kept: (later), '
                 'xs: [(nothing), {gone: (nothing)}]}\n'
                 'key: "drop"\nnothing: None\nlater: 0xff\n')
    assert loads_record(data["body"]) == {"kept": 255, "xs": [{}]}
    assert "0xff" in data["body"]


def test_clean_the_completed_composition_not_its_individual_operands():
    data = loads('foo: {kept: None, gone: 1} | {kept: 2, gone: None}\n'
                 'body: foo.__not_none__().__as_json__()\n')
    assert json.loads(data["body"]) == {"kept": 2}
    assert data["foo"] == {"kept": 2, "gone": None}


@pytest.mark.parametrize("literal,value", [
    ("None", None), ("False", False), ("0", 0), ('"None"', "None"),
])
def test_scalar_input_keeps_its_value(literal, value):
    assert loads(f'clean: __not_none__({literal})\n')["clean"] == value


@pytest.mark.parametrize("call", [
    "__not_none__()", "__not_none__(None, None)",
    "__not_none__(None, option=True)",
])
def test_takes_one_value_and_no_keywords(call):
    with pytest.raises(AkanError, match="takes one value and no keywords"):
        loads(f'clean: {call}\n')


def test_copying_inside_a_serializer_chain_obeys_the_size_ceiling():
    with pytest.raises(AkanError, match="rendered-size ceiling"):
        loads('foo: {text: "a long value"}\n'
              'body: foo.__not_none__().__as_json__()\n', max_size=5)


def test_copies_template_parts_without_rendering_them():
    data = loads('foo: yt"parts {values}"\nvalues: [None, {gone: None}]\n'
                 'clean: foo.__not_none__()\n')
    assert isinstance(data["clean"], Template)
    assert data["clean"].values == ([{}],)
    assert data["foo"].values == ([None, {"gone": None}],)
