"""Resolved constructs and assembled trees produce conforming YamlPlus (§14.9)."""

import io
from pathlib import Path
import subprocess
import sys

import pytest

import yapyon
from yapyon import AkanError, yamlplus


PROGRAM = ('name: "gateway"\n'
           'cfg:\n'
           '  greeting: y"hi {name}"\n'
           '  port: "15".__int__()\n'
           '  choices: [x.__str__() for x in [1, 2]]\n'
           '  selected: 1 if True else 2\n'
           '  copied: (name)\n'
           '  yes: None\n'
           '  payload: hex"6869"\n')


@pytest.mark.parametrize("call", ["cfg.__as_yamlplus__()", "__as_yamlplus__(cfg)"])
def test_serializer_resolves_constructs_and_emits_profile_data(call):
    warnings = []
    value = yapyon.loads(PROGRAM + f'out: y"{{{call}}}"\n', warn=warnings.append)
    output = value["out"]
    assert yapyon.is_yamlplus(output)
    assert yamlplus.loads(output) == value["cfg"]
    assert '"yes": None\n' in output
    assert 'payload: b64"aGk="\n' in output
    assert any("quoting" in warning and "non-name" in warning for warning in warnings)
    assert not any("hora:" in warning for warning in warnings)


def test_expand_yamlplus_uses_the_existing_full_document_pipeline():
    warnings, notices = [], []
    output = yapyon.expand_yamlplus(PROGRAM, env={}, warn=warnings.append, info=notices.append)
    assert yamlplus.loads(output) == yapyon.loads(PROGRAM, env={})
    assert yapyon.is_yamlplus(output)
    assert len(notices) == 2
    assert all(message.startswith("hora:") for message in notices)
    assert all("hora:" not in message for message in warnings)


@pytest.mark.parametrize("source", ["42\n", '"hello"\n', "None\n", "[]\n", "{}\n",
                                    "[1, 2, True, None]\n", 'b"hi"\n', "-0.0\n"])
def test_expansion_supports_every_profile_root_shape(source):
    output = yapyon.expand_yamlplus(source, env={})
    assert yapyon.is_yamlplus(output)
    assert yamlplus.loads(output) == yapyon.loads(source, env={})


def test_profile_output_canonicalizes_unshared_literals_without_mutating_other_writers():
    source = ('cfg:\n  text: r"hello"\n  number: 0q12\n'
              '  "exact": 3.10\n  ｎａｍｅ: "value"\n'
              'before: y"{cfg.__as_yapyon__()}"\n'
              'profile: y"{cfg.__as_yamlplus__()}"\n'
              'after: y"{cfg.__as_yapyon__()}"\n')
    value = yapyon.loads(source)
    assert value["before"] == value["after"]
    assert 'r"hello"' in value["before"] and "0q12" in value["before"]
    assert 'text: "hello"\n' in value["profile"]
    assert "number: 6\n" in value["profile"]
    assert 'name: "value"\n' in value["profile"]
    assert yamlplus.loads(value["profile"]) == value["cfg"]
    loaded = yamlplus.loads(value["profile"])
    with pytest.raises(AkanError):
        yapyon.lookup(loaded, loaded, "exact")


def test_profile_output_consumes_replacement_intent_as_finished_data():
    output = yapyon.expand_yamlplus('cfg: {value:= 1}\n')
    assert ":=" not in output
    assert yamlplus.loads(output) == {"cfg": {"value": 1}}


def test_serializer_waits_for_later_references():
    value = yapyon.loads('out: y"{cfg.__as_yamlplus__()}"\n'
                         'cfg: {value: y"{base}"}\nbase: "ready"\n')
    assert value["out"] == 'value: "ready"\n'


def test_profile_serializers_reach_the_existing_cycle_diagnostic():
    with pytest.raises(AkanError, match="cycle"):
        yapyon.loads('a: {value: y"{__ROOT__.b.__as_yamlplus__()}"}\n'
                     'b: {value: y"{__ROOT__.a.__as_yamlplus__()}"}\n')


@pytest.mark.parametrize("source", ['cfg: {+}\n', 'cfg: {nested: {+}}\n',
                                    'cfg:\n  + key: 1\n  + key: 2\n'])
def test_multimap_exclusion_is_not_approximated_with_a_wrapper(source):
    with pytest.raises(AkanError, match="multimap") as caught:
        yapyon.loads(source + 'out: y"{cfg.__as_yamlplus__()}"\n', source="input.yap")
    assert caught.value.source == "input.yap"
    assert caught.value.line >= 1
    with pytest.raises(AkanError, match="multimap"):
        yapyon.expand_yamlplus(source)


def test_templates_are_not_joined_by_profile_output():
    source = 'name: "x"\ncfg: {text: yt"{name}"}\n'
    with pytest.raises(AkanError, match="yeeted yt"):
        yapyon.loads(source + 'out: y"{cfg.__as_yamlplus__()}"\n')
    with pytest.raises(AkanError, match="yeeted yt"):
        yapyon.expand_yamlplus(source)
    with pytest.raises(AkanError, match="yeeted yt"):
        yapyon.parse(source).to_yamlplus()


def test_template_outside_serializer_target_is_untouched():
    value = yapyon.loads('name: "x"\ntext: yt"{name}"\ncfg: {value: 1}\n'
                         'out: y"{cfg.__as_yamlplus__()}"\n')
    assert value["out"] == "value: 1\n"
    assert isinstance(value["text"], yapyon.Template)


def test_filled_and_merged_tree_output_resolves_a_private_copy():
    tree = yapyon.parse('name: "service"\ncfg<base>: {port: 5}\n')
    tree["cfg"].fill(yapyon.parse('greeting: y"hi {name}"\nenabled: True\n'))
    tree.merge(yapyon.parse('cfg: {port: 6}\n'))
    before = tree.to_source()
    output = tree.to_yamlplus(env={})
    assert tree.to_source() == before
    assert yamlplus.loads(output) == tree.resolve(env={})
    assert yamlplus.loads(output)["cfg"] == {"greeting": "hi service", "enabled": True, "port": 6}


def test_unfilled_slots_remain_a_resolution_error():
    tree = yapyon.parse("cfg<base>: {}\n")
    with pytest.raises(AkanError):
        tree.to_yamlplus()
    assert "<base>" in tree.to_source()


def test_environment_access_is_not_a_second_pipeline_or_an_ambient_guess():
    source = 'home: y"{$HOME}"\n'
    output = yapyon.expand_yamlplus(source, env={"HOME": "chosen"})
    assert yamlplus.loads(output) == {"home": "chosen"}
    with pytest.raises(AkanError):
        yapyon.expand_yamlplus(source, env=None)


@pytest.mark.parametrize("route", ["expand", "tree", "serializer"])
def test_profile_output_does_not_evaluate_calls_again_or_visit_unselected_branches(route):
    contract = yapyon.loads_contract('F:\n  params: {n: "int"}\n  returns: "int"\n'
                                    '  impl: {python: {symbol: "F"}}\n')
    calls = []

    def function(n):
        calls.append(n)
        return n

    source = 'cfg: {value: F(1) if True else F(2)}\n'
    options = dict(contract=contract, provide={"F": function}, env={})
    if route == "expand":
        output = yapyon.expand_yamlplus(source, **options)
        assert yamlplus.loads(output) == {"cfg": {"value": 1}}
    elif route == "tree":
        tree = yapyon.parse(source)
        before = tree.to_source()
        output = tree.to_yamlplus(**options)
        assert yamlplus.loads(output) == {"cfg": {"value": 1}}
        assert tree.to_source() == before
    else:
        output = yapyon.loads(source + 'out: y"{cfg.__as_yamlplus__()}"\n', **options)["out"]
        assert yamlplus.loads(output) == {"value": 1}
    assert calls == [1]


def test_expansion_and_tree_callback_failures_propagate():
    def fail(message):
        raise RuntimeError("consumer failed")

    for work in (yapyon.expand_yamlplus, lambda text, **kw: yapyon.parse(text).to_yamlplus(**kw)):
        with pytest.raises(RuntimeError, match="consumer failed"):
            work("yes: None\n", warn=fail)
        with pytest.raises(RuntimeError, match="consumer failed"):
            work("missing: None\n", info=fail)
        with pytest.raises(TypeError, match="info"):
            work("missing: None\n", info=1)


def test_existing_record_expansion_and_profile_reading_are_retained():
    assert yapyon.expand_record("value: 0q12\n") == "value: 0q12\n"
    assert yamlplus.loads('value: None\npayload: b"hi"\n') == {"value": None, "payload": b"hi"}
    assert yapyon.is_yamlplus('value: None\n')
    assert yamlplus.normalize("yes: 1 # keep\n") == '"yes": 1 # keep\n'


def test_completed_host_output_is_validated_before_stream_write(monkeypatch):
    monkeypatch.setattr(yamlplus, "_emit_prepared", lambda *args: "value: null\n")
    stream = io.StringIO("original")
    with pytest.raises(AkanError):
        yamlplus.dump({"value": None}, stream)
    assert stream.getvalue() == "original"


def test_cli_expands_to_profile_and_separates_optional_information():
    args = [sys.executable, "-m", "yapyon", "expand", "--yamlplus", "--no-env"]
    quiet = subprocess.run(args, input="yes: None\n", text=True, capture_output=True)
    verbose = subprocess.run(args + ["--info"], input="yes: None\n", text=True, capture_output=True)
    assert quiet.returncode == verbose.returncode == 0
    assert quiet.stdout == verbose.stdout == '"yes": None\n'
    assert "shiran:" in quiet.stderr and "hora:" not in quiet.stderr
    assert "hora:" in verbose.stderr
    assert yapyon.is_yamlplus(verbose.stdout)


def test_yamlplus_output_does_not_require_pyyaml_or_the_standalone_package():
    source = Path(yapyon.__file__).resolve().parents[1]
    program = f'''
import sys
sys.path.insert(0, {str(source)!r})
class NoExternalYaml:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ("yaml", "yamlplus") or fullname.startswith(("yaml.", "yamlplus.")):
            raise AssertionError("unexpected external YAML runtime")
sys.meta_path.insert(0, NoExternalYaml())
import yapyon
text = yapyon.expand_yamlplus('name: "x"\\nvalue: y"{{name}}"\\n')
assert yapyon.is_yamlplus(text)
assert yapyon.yamlplus.loads(text) == {{"name": "x", "value": "x"}}
value = yapyon.loads('cfg: {{a: 1}}\\nout: y"{{cfg.__as_yamlplus__()}}"\\n')
assert value["out"] == "a: 1\\n"
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c", program],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
