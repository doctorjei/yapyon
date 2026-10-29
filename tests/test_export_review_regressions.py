"""Independent review regressions for faithful text and bounded preparation."""

import tracemalloc

import pytest

import yapyon
from yapyon import emitter


@pytest.mark.parametrize("value", [
    "  first\n  second", "  first\nsecond", "\n  first\nsecond",
    "   first\n second\n", " \tfirst\nsecond",
])
def test_block_anchor_does_not_consume_leading_data_spaces(value):
    text = yapyon.dumps(value)
    assert yapyon.loads_record(text) == value
    nested = {"outer": [[{"value": value}]]}
    assert yapyon.loads_record(yapyon.dumps(nested)) == nested


def test_multimap_budget_does_not_call_the_snapshot_iterator(monkeypatch):
    value = yapyon.OrderedMultimap()
    for _ in range(10000):
        value.insert("same", 0)

    def snapshot(*args):
        raise AssertionError("an unbounded entry snapshot was requested")

    monkeypatch.setattr(yapyon.OrderedMultimap, "__iter__", snapshot)
    with pytest.raises(ValueError, match="max_size"):
        yapyon.dumps(value, max_size=1)


@pytest.mark.parametrize("kind", ["str", "bytes", "key"])
def test_scalar_subclass_payload_is_bounded_before_normalization_copy(kind):
    class Text(str):
        pass

    class Binary(bytes):
        pass

    payload = Binary(b"x" * 5000000) if kind == "bytes" else Text("x" * 5000000)
    value = {payload: 1} if kind == "key" else payload
    tracing = tracemalloc.is_tracing()
    if not tracing:
        tracemalloc.start()
    baseline = tracemalloc.get_traced_memory()[0]
    tracemalloc.reset_peak()
    try:
        with pytest.raises(ValueError, match="max_size"):
            yapyon.dumps(value, max_size=1)
        peak = tracemalloc.get_traced_memory()[1] - baseline
    finally:
        if not tracing:
            tracemalloc.stop()
    assert peak < 100000


@pytest.mark.parametrize("options", [{}, {"max_digits": 100000, "max_size": 1}])
def test_giant_integer_is_rejected_before_exact_digit_counting(monkeypatch, options):
    import yapyon.export as export
    value = 1 << 200000

    def counting(*args):
        raise AssertionError("oversized integer reached expensive exact counting")

    monkeypatch.setattr(export, "decimal_digits", counting)
    with pytest.raises(ValueError, match="max_digits|max_size"):
        yapyon.dumps(value, **options)


def test_flow_probes_do_not_materialize_rejected_multiline_bodies(monkeypatch):
    value = "first\nsecond" * 1000
    for _ in range(20):
        value = [value]
    calls = []
    original = emitter._block_lines

    def block(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(emitter, "_block_lines", block)
    text = yapyon.dumps(value)
    assert yapyon.loads_record(text) == value
    assert len(calls) == 1


def test_speculative_flow_escape_work_stops_at_the_width_budget(monkeypatch):
    size = 1000000
    value = "x" * size
    for _ in range(20):
        value = [value]
    escaped = []
    original = emitter._escaped

    def pieces(*args, **kwargs):
        for text in original(*args, **kwargs):
            escaped.append(len(text))
            yield text

    monkeypatch.setattr(emitter, "_escaped", pieces)
    text = yapyon.dumps(value)
    assert len(text) == size + 2 * 20 + 3
    assert sum(escaped) < 2 * size
