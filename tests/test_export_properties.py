"""Deterministic generated data checks against the independent record reader."""

import random

import pytest

import yapyon


def _sample(seed):
    rng = random.Random(seed)
    texts = ["", "plain", "é界", "é", "\x00\x7f", "line\nnext\n",
             "\\n\n\t\"quoted", "\n\n", "space\n \nend", "\"\"\"\nend",
             "combining" + "\u0301" * 150, "😀\ufe0f", "x" * 105]
    keys = ["name", "model/id", "ｎａｍｅ", "é", "True", "with\nnewline", "x\"y"]

    def value(depth):
        kind = rng.randrange(6 if depth == 0 else 9)
        if kind == 0:
            return rng.choice((None, True, False))
        if kind == 1:
            return rng.randrange(-10 ** 15, 10 ** 15)
        if kind == 2:
            return rng.choice((0.0, -0.0, 1e300, 5e-324, 1.234567890123))
        if kind == 3:
            return rng.choice(texts)
        if kind == 4:
            return bytes(rng.randrange(256) for _ in range(rng.randrange(15)))
        if kind == 5:
            return rng.choice(([], {}))
        if kind == 6:
            return [value(depth - 1) for _ in range(rng.randrange(5))]
        if kind == 7:
            return {key: value(depth - 1) for key in rng.sample(keys, rng.randrange(5))}
        out = yapyon.OrderedMultimap()
        for _ in range(rng.randrange(5)):
            out.insert(rng.choice(keys), value(depth - 1))
        return out

    return value(4)


def _same_data(actual, expected):
    pending, seen = [(actual, expected)], set()
    while pending:
        left, right = pending.pop()
        if isinstance(right, dict):
            assert isinstance(left, dict)
            assert list(left) == list(right)
            pending.extend(zip(left.values(), right.values()))
        elif isinstance(right, list):
            assert isinstance(left, list)
            assert len(left) == len(right)
            pending.extend(zip(left, right))
        elif isinstance(right, yapyon.OrderedMultimap):
            assert isinstance(left, yapyon.OrderedMultimap)
            assert [entry.key for entry in left] == [entry.key for entry in right]
            pending.extend((a.value, b.value) for a, b in zip(left, right))
        else:
            assert type(left) is type(right)
            assert left == right
            continue
        assert id(left) not in seen
        seen.add(id(left))


@pytest.mark.parametrize("seed", range(200))
def test_generated_values_round_trip_at_the_exact_independent_byte_budget(seed):
    value = _sample(seed)
    text = yapyon.dumps(value)
    _same_data(yapyon.loads_record(text), value)
    size = len(text.encode("utf-8"))
    assert yapyon.dumps(value, max_size=size) == text
    with pytest.raises(ValueError, match="max_size"):
        yapyon.dumps(value, max_size=size - 1)
