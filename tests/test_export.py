"""Host-value record export: types, exact keys, graph ownership, and streams."""

import io
import math

import pytest

import yapyon
from yapyon._keys import KeyMap


@pytest.mark.parametrize("value", [
    None, True, False, 0, -123, 1.5, -0.0, 1e300, 5e-324,
    "", "hello", "café ガイド", "line\nnext\n", "\x00\r\t\x7f",
    b"", b"\x00\xff\n\"\\", [], {}, [None, False, 0, "", [], {}],
    {"name": "example", "nested": [1, {"port": 8080}]},
])
def test_every_supported_root_round_trips(value):
    text = yapyon.dumps(value)
    assert text.endswith("\n")
    loaded = yapyon.loads_record(text)
    assert loaded == value
    if isinstance(value, float):
        assert math.copysign(1, loaded) == math.copysign(1, value)


def test_typed_values_stay_distinct():
    result = yapyon.loads_record(yapyon.dumps([True, 1, 1.0, False, 0, 0.0]))
    assert [type(value) for value in result] == [bool, int, float] * 2


def test_plain_host_keys_preserve_exact_text_and_choose_exact_names():
    value = {"name": "example", "model/id": "m1", "ｎａｍｅ": "wide",
             "é": "decomposed", "True": "keyword", "class": 1}
    text = yapyon.dumps(value)
    assert 'name: "example"\n' in text
    assert '"ｎａｍｅ": "wide"\n' in text
    loaded = yapyon.loads_record(text)
    assert list(loaded.items()) == list(value.items())
    assert loaded._is_named("name")
    assert not loaded._is_named("ｎａｍｅ")
    assert not loaded._is_named("é")
    assert not loaded._is_named("True")
    assert loaded._is_named("class")


def test_loaded_non_name_provenance_survives_export():
    value = yapyon.loads_record('name: 1\n"quoted": 2\n')
    loaded = yapyon.loads_record(yapyon.dumps(value))
    assert loaded == value
    assert loaded._is_named("name")
    assert not loaded._is_named("quoted")


@pytest.mark.parametrize("key", ["ｎａｍｅ", "not-a-name", "True"])
def test_inconsistent_named_provenance_is_refused(key):
    value = KeyMap()
    value._put(key, 1, True)
    with pytest.raises(ValueError, match="provenance"):
        yapyon.dumps(value)


def test_multimap_order_repetition_and_key_kind_survive():
    value = yapyon.loads_record('+ same: 1\n+ "same": 2\n+ other: None\n')
    text = yapyon.dumps(value)
    loaded = yapyon.loads_record(text)
    assert loaded == value
    assert [(entry.key, entry._named) for entry in loaded] == [
        ("same", True), ("same", False), ("other", True)]


def test_empty_multimap_round_trips():
    value = yapyon.OrderedMultimap()
    assert yapyon.dumps(value) == "{+}\n"
    assert yapyon.loads_record(yapyon.dumps(value)) == value


def test_shared_input_becomes_independent_occurrences():
    shared = [{"value": [1, 2]}]
    value = {"first": shared, "second": shared}
    loaded = yapyon.loads_record(yapyon.dumps(value))
    assert loaded == value
    assert loaded["first"] is not loaded["second"]
    loaded["first"][0]["value"].append(3)
    assert loaded["second"][0]["value"] == [1, 2]
    assert shared == [{"value": [1, 2]}]


@pytest.mark.parametrize("kind", ["list", "dict", "multimap"])
def test_actual_cycles_have_paths_and_no_fake_coordinates(kind):
    value = [] if kind == "list" else {} if kind == "dict" else yapyon.OrderedMultimap()
    if kind == "list":
        value.append(value)
    elif kind == "dict":
        value["self"] = value
    else:
        value.insert("self", value)
    with pytest.raises(yapyon.AkanError, match="cycle.*ancestor.*root") as caught:
        yapyon.dumps(value)
    assert caught.value.line is None
    assert caught.value.col is None
    assert caught.value.source is None
    assert caught.value.where.startswith("root[")


@pytest.mark.parametrize("value", [(), {1}, bytearray(b"x"), memoryview(b"x"), object()])
def test_unsupported_host_kinds_are_type_errors(value):
    with pytest.raises(TypeError, match="root.*supported record data"):
        yapyon.dumps(value)


def test_template_and_unresolved_tree_are_not_implicitly_exported():
    template = yapyon.loads('yt"hello"')
    for value in (template, yapyon.parse('a: 1')):
        with pytest.raises(TypeError):
            yapyon.dumps(value)


@pytest.mark.parametrize("key", [1, False, None, b"x"])
def test_non_string_keys_are_type_errors(key):
    with pytest.raises(TypeError, match="key must be a string"):
        yapyon.dumps({key: 1})


@pytest.mark.parametrize("key", ["", "__bad__", "__", "@private", "bad\ud800"])
def test_invalid_key_text_is_a_value_error(key):
    with pytest.raises(ValueError):
        yapyon.dumps({key: 1})


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), "\udfff"])
def test_nonfinite_or_surrogate_values_are_value_errors(value):
    with pytest.raises(ValueError):
        yapyon.dumps({"nested": [value]})


def test_nested_error_identifies_the_occurrence():
    with pytest.raises(TypeError, match=r"root\['servers'\]\[1\]\['port'\]"):
        yapyon.dumps({"servers": [{"port": 1}, {"port": object()}]})


def test_multimap_error_identifies_entry_ordinal():
    value = yapyon.OrderedMultimap()
    value.insert("same", 1)
    value.insert("same", object())
    with pytest.raises(TypeError, match=r"entry 1: 'same'"):
        yapyon.dumps(value)


@pytest.mark.parametrize("option", ["max_digits", "max_depth", "max_size"])
@pytest.mark.parametrize("invalid", [True, False, None, 1.5, "10"])
def test_limit_options_require_integers_not_bools(option, invalid):
    with pytest.raises(TypeError, match=option):
        yapyon.dumps(object(), **{option: invalid})


@pytest.mark.parametrize("options", [
    {"max_digits": 4299}, {"max_depth": 0}, {"max_size": 0}, {"max_depth": -1},
])
def test_option_ranges_are_checked_before_input(options):
    with pytest.raises(ValueError):
        yapyon.dumps(object(), **options)


def test_warn_requires_callable_or_none():
    with pytest.raises(TypeError, match="warn"):
        yapyon.dumps(1, warn=True)


def test_export_does_not_use_arbitrary_conversion_hooks():
    class Unsupported:
        def __str__(self):
            raise AssertionError("implicit conversion")

        def __repr__(self):
            raise AssertionError("implicit conversion")

    class Text(str):
        def __str__(self):
            raise AssertionError("implicit conversion")

    class Number(int):
        def __str__(self):
            raise AssertionError("implicit conversion")

        def __int__(self):
            raise AssertionError("implicit conversion")

    class Dictionary(dict):
        def items(self):
            raise AssertionError("custom adapter")

    with pytest.raises(TypeError):
        yapyon.dumps(Unsupported())
    assert yapyon.loads_record(yapyon.dumps(Dictionary({Text("key"): Number(3)}))) == {"key": 3}


class Sink:
    def __init__(self, result=None):
        self.calls, self.result = [], result

    def write(self, text):
        self.calls.append(text)
        return self.result


def test_dump_prepares_then_writes_once_without_close_or_flush():
    sink = Sink()
    value = {"port": 8080}
    assert yapyon.dump(value, sink) is None
    assert sink.calls == [yapyon.dumps(value)]


def test_dump_accepts_a_character_count():
    fp = io.StringIO()
    assert yapyon.dump("café", fp) is None
    assert fp.getvalue() == yapyon.dumps("café")
    assert not fp.closed


@pytest.mark.parametrize("value,options,error", [
    (object(), {}, TypeError), ({"": 1}, {}, ValueError),
    ([1], {"max_depth": False}, TypeError), ("large", {"max_size": 1}, ValueError),
])
def test_invalid_data_or_options_cause_zero_writes(value, options, error):
    sink = Sink()
    with pytest.raises(error):
        yapyon.dump(value, sink, **options)
    assert sink.calls == []


@pytest.mark.parametrize("fp", [None, "file.yap", object(), type("Bad", (), {"write": 1})()])
def test_dump_requires_a_text_write_protocol(fp):
    with pytest.raises(TypeError, match="write"):
        yapyon.dump(1, fp)


@pytest.mark.parametrize("count", [0, -1, 999])
def test_dump_reports_short_or_inconsistent_counts_without_retry(count):
    sink = Sink(count)
    with pytest.raises(OSError, match="complete write"):
        yapyon.dump(1, sink)
    assert len(sink.calls) == 1


def test_native_stream_failure_propagates_unchanged():
    failure = PermissionError("blocked")

    class Broken:
        def write(self, text):
            raise failure

    with pytest.raises(PermissionError) as caught:
        yapyon.dump(1, Broken())
    assert caught.value is failure
