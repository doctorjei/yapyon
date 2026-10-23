"""SPEC §15.6: diagnostics name the document each value was written in,
however the tree was assembled. Every parsed node records its source."""

import pytest

from yapyon import AkanError
from yapyon.parser import Mapping, Pair, children, parse
from yapyon.resolver import resolve


def walk(node):
    yield node
    for child in children(node):
        yield from walk(child)


def test_every_parsed_node_knows_its_document():
    tree = parse('a:\n  b: [1, y"{c}"]\n  s<x>: {d: 2}\nc: "k"\n',
                 source="one.yap")
    assert {node.source for node in walk(tree)} == {"one.yap"}


def test_without_a_source_nothing_is_recorded():
    assert parse("a: 1\n").source is None


def test_a_grafted_value_is_reported_in_its_own_document():
    base = parse('a: 1\n', source="base.yap")
    extra = parse('b: y"{missing}"\n', source="extra.yap")
    joined = Mapping(1, 0, base.pairs + extra.pairs)
    with pytest.raises(AkanError, match=r"^akan: extra\.yap:1:3: "):
        resolve(joined, source="whole.yap")


def test_y_strings_and_copies_keep_their_spelling():
    tree = parse("a: 1\nb: ry'{a}\\n'\nc: ( a )\n")
    assert tree.by_key["b"].lexeme == "ry'{a}\\n'"
    assert tree.by_key["c"].lexeme == "( a )"
