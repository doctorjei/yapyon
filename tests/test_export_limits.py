"""Independent byte, container-depth, decimal, and non-evaluating export checks."""

import sys

import pytest

import yapyon
from yapyon import emitter
from yapyon.parser import Mapping, Pair, Scalar, Sequence


@pytest.mark.parametrize("value", [
    None, 1, -1, 1.5, "", "ASCII", "é界", "\x00\x01\x7f", b"\x00\xff\"\\",
    "first\nsecond\n", "\n", "\n\n", "\\n\n\t\"end", "one\r\ntwo",
    [], {}, [1, 2, 3], [[1, 2], []], {"a": "界", "b": [1, 2]},
    {"deep": {"key": "line\ntext\n"}}, [{"x": ["one\ntwo", "last"]}],
    ["x" * 90, "y" * 90], {"x" * 90: [1, 2, 3, 4, 5]},
])
def test_exact_utf8_output_budget_includes_every_byte(value):
    text = yapyon.dumps(value)
    size = len(text.encode("utf-8"))
    assert yapyon.dumps(value, max_size=size) == text
    with pytest.raises(ValueError, match="max_size"):
        yapyon.dumps(value, max_size=size - 1)
    assert yapyon.loads_record(text) == value


@pytest.mark.parametrize("value", [
    "literal\\n\nsecond", "quote\"inside\nsecond", "control\x00\nsecond",
    "carriage\r\nnext", "tab\t\nnext", "\\\n", "\"\nlast",
])
def test_canonical_block_strings_escape_data_before_reloading(value):
    text = yapyon.dumps(value)
    assert text.startswith('"""\n')
    assert yapyon.loads_record(text) == value
    node = Scalar(0, 0, "str", value)
    assert emitter.emit(node) == text


def test_depth_counts_only_containers_and_root_container_is_one():
    assert yapyon.dumps("scalar", max_depth=1) == '"scalar"\n'
    assert yapyon.dumps([1], max_depth=1) == "[1]\n"
    assert yapyon.dumps({"a": []}, max_depth=2) == "a: []\n"
    with pytest.raises(ValueError, match="depth 2.*max_depth of 1"):
        yapyon.dumps({"a": []}, max_depth=1)


def test_default_depth_ceiling_precedes_host_recursion_failure():
    value = 0
    for _ in range(129):
        value = [value]
    with pytest.raises(ValueError, match="max_depth of 128"):
        yapyon.dumps(value)


def test_explicit_high_depth_does_not_depend_on_host_recursion_limit():
    depth, value = 1200, 0
    for _ in range(depth):
        value = [value]
    text = yapyon.dumps(value, max_depth=depth)
    assert text == "- " * depth + "0\n"
    assert yapyon.dumps(value, max_depth=depth, max_size=len(text)) == text
    with pytest.raises(ValueError, match="max_size"):
        yapyon.dumps(value, max_depth=depth, max_size=len(text) - 1)


def test_deep_dictionary_rendering_is_iterative_and_byte_bounded():
    depth, value = 600, 0
    for _ in range(depth):
        value = {"x": value}
    expected = "".join("  " * i + ("x: 0\n" if i == depth - 1 else "x:\n")
                       for i in range(depth))
    assert yapyon.dumps(value, max_depth=depth, max_size=len(expected)) == expected
    with pytest.raises(ValueError, match="max_size"):
        yapyon.dumps(value, max_depth=depth, max_size=len(expected) - 1)


def test_aliased_exponential_input_stops_during_adaptation(monkeypatch):
    import yapyon.export as export
    value = [0]
    for _ in range(60):
        value = [value, value]
    visits = []
    original = export._scalar

    def scalar(*args):
        visits.append(1)
        return original(*args)

    monkeypatch.setattr(export, "_scalar", scalar)
    with pytest.raises(ValueError, match="max_size"):
        yapyon.dumps(value, max_size=512)
    assert len(visits) < 512


def test_escape_expansion_is_bounded_before_a_complete_string_is_created(monkeypatch):
    checks = []
    original = emitter._Limit.check

    def check(self, size):
        checks.append(size)
        return original(self, size)

    monkeypatch.setattr(emitter._Limit, "check", check)
    with pytest.raises(ValueError, match="max_size"):
        yapyon.dumps("\x00" * 10000, max_size=10002)
    assert max(checks) <= 10002 + 4096


def test_block_indentation_is_counted_while_materializing_lines():
    value = {"a": {"b": "x\n" * 5000}}
    with pytest.raises(ValueError, match="max_size"):
        yapyon.dumps(value, max_size=10020)


@pytest.mark.parametrize("digits", [4300, 4301, 17200])
def test_decimal_digits_and_warning_boundary(digits):
    value = 10 ** (digits - 1)
    messages = []
    text = yapyon.dumps(value, warn=messages.append)
    assert text == "1" + "0" * (digits - 1) + "\n"
    assert len(messages) == (digits > 4300)
    if messages:
        assert "root" in messages[0] and str(digits) in messages[0]


def test_decimal_refusal_and_configurable_ceiling():
    value = 10 ** 17200
    with pytest.raises(ValueError, match="max_digits"):
        yapyon.dumps(value)
    assert len(yapyon.dumps(value, max_digits=17201)) == 17202


def test_decimal_output_ignores_the_hosts_minimum_conversion_limit():
    previous = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(640)
        assert yapyon.dumps(10 ** 999) == "1" + "0" * 999 + "\n"
        assert yapyon.dumps(10 ** 4999) == "1" + "0" * 4999 + "\n"
    finally:
        sys.set_int_max_str_digits(previous)


def test_warning_callback_failure_propagates_without_a_write():
    failure = RuntimeError("callback")
    writes = []

    def warn(message):
        raise failure

    class Sink:
        def write(self, text):
            writes.append(text)

    with pytest.raises(RuntimeError) as caught:
        yapyon.dump(10 ** 4300, Sink(), warn=warn)
    assert caught.value is failure
    assert writes == []


def test_immediate_cycle_is_reported_before_descending_past_depth_ceiling():
    value = []
    value.append(value)
    with pytest.raises(yapyon.AkanError, match="cycle"):
        yapyon.dumps(value, max_depth=1)


def test_export_never_reaches_resolution_environment_or_function_paths(monkeypatch):
    import yapyon.environment as environment
    import yapyon.resolver as resolver
    import yapyon.contract as contract

    def forbidden(*args, **kwargs):
        raise AssertionError("evaluation during export")

    monkeypatch.setattr(resolver, "resolve", forbidden)
    monkeypatch.setattr(environment, "environment", forbidden)
    monkeypatch.setattr(contract, "result_node", forbidden)
    text = yapyon.dumps({"plain": 'y"{$HOME}"', "number": 1})
    assert 'plain: "y\\"{$HOME}\\""' in text


def test_flat_layout_helper_handles_deep_trees_without_host_recursion():
    node = Scalar(0, 0, "int", 1)
    for _ in range(1200):
        node = Sequence(0, 0, [node])
    assert emitter.flat(node)
    assert not emitter.flat(Sequence(0, 0, [node, Mapping(0, 0, [Pair(0, 0, "a", node)])]))
