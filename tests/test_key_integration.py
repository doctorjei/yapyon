"""Computed keys through contracts and persona_grata's consumer boundaries."""

import json
import pickle
import tomllib

import pytest

from yapyon import AkanError, loads, loads_contract, loads_record, lookup, parse


RUNTIME = '''runtime<>:
  agent_path<>: {}
  secret_backend<>: {}
agent<>: {}
'''
AGENT = '''harness:
  name: "base_harness"
  path: y"{runtime.agent_path}/harness"
'''


def test_runtime_child_slots_are_filled_after_the_outer_slot():
    tree = parse(RUNTIME)
    tree["runtime"].fill(parse("{}"))
    tree["runtime"]["agent_path"].fill(parse('"/home/example/stable_dir"'))
    tree["runtime"]["secret_backend"].fill(parse("{}"))
    tree["agent"].fill(parse(AGENT))
    assert tree.slots() == []
    result = tree.resolve()
    assert result["runtime"] == {"agent_path": "/home/example/stable_dir", "secret_backend": {}}
    assert result["agent"]["harness"]["path"] == "/home/example/stable_dir/harness"


def test_concrete_runtime_fill_does_not_erase_abstract_overrides():
    tree = parse(RUNTIME)
    tree["runtime"].fill(parse('agent_path: "/actual"\nsecret_backend: {}'))
    assert tree["runtime"]["agent_path"].kind == "slot"
    tree["agent"].fill(parse(AGENT))
    with pytest.raises(AkanError, match="unfilled|never given"):
        tree.resolve()


@pytest.mark.parametrize("models", [[], ["one"], ["one", "two", "three", "four", "five"]])
def test_optional_model_selection_preserves_none(models):
    doc = (f'persona: {{mind: {{model_list: {json.dumps(models)}, context_size: None}}}}\n'
           'first: persona.mind.model_list.__get__(0)?.__str__()\n'
           'fifth: persona.mind.model_list.__get__(4)?.__str__()\n'
           'context: persona.mind.context_size?.__str__()')
    result = loads(doc)
    assert result["first"] == (models[0] if models else None)
    assert result["fifth"] == (models[4] if len(models) > 4 else None)
    assert result["context"] is None


def test_dynamic_provider_key_survives_native_toml_serialization():
    doc = '''persona: {name: "moonshot-ai", desc: "Example"}
config:
  model_provider: (persona.name)
  model_providers:
    y"{persona.name}":
      name: y"{persona.desc}"
      base_url: "https://example.invalid"
out: config.__as_toml__()
'''
    result = tomllib.loads(loads(doc)["out"])
    assert result["model_provider"] == "moonshot-ai"
    assert result["model_providers"] == {"moonshot-ai": {
        "name": "Example", "base_url": "https://example.invalid"}}


MODEL_CONTRACT = '''GEN_MODEL_TABLE:
  params: {provider: "str", models: "list[str]"}
  returns: "dict[str, dict[str, str]]"
  impl: {python: {symbol: "models"}}
'''


@pytest.mark.parametrize("models", [[], ["m-1", "m/2"]])
def test_contract_mapping_results_are_data_not_interpolated_text(models):
    contract = loads_contract(MODEL_CONTRACT)
    doc = (f'names: {json.dumps(models)}\n'
           'table: GEN_MODEL_TABLE("example", names)\n'
           'out: table.__as_toml__()')
    def build(provider, names):
        return {name: {"provider": provider, "remote_model_id": name} for name in names}
    result = loads(doc, contract=contract, provide={"models": build})
    assert result["table"] == build("example", models)
    assert tomllib.loads(result["out"]) == build("example", models)


def test_contract_results_preserve_loaded_non_name_metadata():
    contract = loads_contract('MAKE: {params: {}, returns: "dict[str, int]", '
                              'impl: {python: {symbol: "make"}}}')
    result = loads('data: MAKE()\nx: (data["name"])', contract=contract,
                   provide={"make": lambda: loads_record('"name": 1')})
    assert result["x"] == 1
    with pytest.raises(AkanError):
        lookup(result, result, "data.name")


def test_key_binding_verification_does_not_reexecute_a_subscript_call():
    contract = loads_contract('INDEX: {params: {}, returns: "int", '
                              'impl: {python: {symbol: "index"}}}')
    calls = []
    def index():
        calls.append(1)
        return 0
    assert loads('models: ["x"]\ny"{models[INDEX()]}": 1',
                 contract=contract, provide={"index": index}) == {"models": ["x"], "x": 1}
    assert len(calls) == 1


def test_external_dict_names_fold_but_loaded_quoted_keys_do_not():
    data = {"ｎａｍｅ": 1}
    assert lookup(data, data, "name") == 1
    quoted = loads_record('"ｎａｍｅ": 1')
    with pytest.raises(AkanError):
        lookup(quoted, quoted, "name")
    assert lookup(quoted, quoted, '__ROOT__["ｎａｍｅ"]') == 1


def test_external_dict_fold_collisions_are_not_silently_discarded():
    data = {"name": 1, "ｎａｍｅ": 2}
    with pytest.raises(AkanError, match="duplicate key"):
        lookup(data, data, "name")


@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
def test_pickle_preserves_loaded_key_kinds(protocol):
    data = pickle.loads(pickle.dumps(loads_record('"name": 1'), protocol=protocol))
    assert data == {"name": 1}
    with pytest.raises(AkanError):
        lookup(data, data, "name")
