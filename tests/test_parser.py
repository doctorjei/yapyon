"""Parser tests — one test per spec rule, named after the rule.

When a test and the implementation disagree, check SPEC.md before changing
either.
"""

from pathlib import Path

import pytest

from yapyon.lexer import AkanError
from yapyon.parser import Mapping, MultiMap, Scalar, Sequence, YString, parse

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "gateway.ypy"


def akan(text, needle=""):
    with pytest.raises(AkanError) as e:
        parse(text)
    assert needle in str(e.value), f"wrong message: {e.value}"


# --------------------------------------------------------------------------- #
# SPEC §8 — document ::= block_value EOF
# --------------------------------------------------------------------------- #
def test_any_value_is_a_document():
    node = parse('"just a string"\n')
    assert isinstance(node, Scalar) and node.value == "just a string"


def test_empty_document_is_akan():
    akan("# only a comment\n", "empty document")


def test_one_document_per_file():
    akan('"a"\n"b"\n', "one document per file")


# --------------------------------------------------------------------------- #
# SPEC §8 — block_map
# --------------------------------------------------------------------------- #
def test_block_map_keeps_pairs_in_source_order():
    node = parse('b: 1\na: 2\nc: 3\n')
    assert [p.key for p in node.pairs] == ["b", "a", "c"]
    assert node.by_key["a"].value == 2


def test_nested_block_map():
    node = parse('server:\n  host: "h"\n  port: 8080\n')
    inner = node.by_key["server"]
    assert isinstance(inner, Mapping)
    assert [p.key for p in inner.pairs] == ["host", "port"]
    assert inner.by_key["port"].value == 8080


def test_key_without_a_value_is_akan_at_the_key():
    with pytest.raises(AkanError) as e:
        parse("a:\nb: 1\n")
    assert "has no value" in str(e.value)
    assert (e.value.line, e.value.col) == (1, 0)     # the key, not the next line


def test_two_values_on_one_line_is_akan():
    akan("a: 1 2\n", "after the value of 'a'")


# --------------------------------------------------------------------------- #
# SPEC §8 — block_seq
# --------------------------------------------------------------------------- #
def test_block_seq():
    node = parse('- "a"\n- "b"\n')
    assert isinstance(node, Sequence)
    assert [i.value for i in node.items] == ["a", "b"]


def test_nested_dash_frames_nest_sequences():
    node = parse('- - "x"\n')
    assert isinstance(node.items[0], Sequence)
    assert node.items[0].items[0].value == "x"


def test_dash_item_may_hold_a_mapping():
    node = parse('servers:\n  - name: "w1"\n    port: 1\n  - name: "w2"\n')
    servers = node.by_key["servers"]
    assert len(servers.items) == 2
    assert servers.items[0].by_key["name"].value == "w1"
    assert servers.items[1].by_key["name"].value == "w2"


def test_a_block_may_not_mix_pairs_and_items():
    akan("a: 1\n- 2\n", "not both")
    akan("- 1\nb: 2\n", "not both")


# --------------------------------------------------------------------------- #
# SPEC §8 — bare markers are layout, not meaning
# --------------------------------------------------------------------------- #
def test_bare_dash_body_at_the_frame_anchor():
    node = parse("-\n  a: 1\n")
    assert node.items[0].by_key["a"].value == 1


def test_bare_dash_body_deeper_than_the_anchor():
    # the extra INDENT/DEDENT pair is layout; same document
    node = parse("-\n      a: 1\n")
    assert node.items[0].by_key["a"].value == 1


def test_bare_dash_is_the_same_document_as_an_inline_dash():
    inline = [i.value for i in parse("- 1\n- 2\n").items]
    bare = [i.value for i in parse("-\n  1\n- 2\n").items]
    assert inline == bare == [1, 2]


def test_empty_sequence_item_is_akan():
    # no implicit null: layout must not smuggle None back in
    akan("-\n", "sequence item has no value (write None)")


def test_empty_multimap_entry_is_akan():
    akan("+\n", "multimap entry has no value (write None)")


# --------------------------------------------------------------------------- #
# SPEC §7.1 — multimaps
# --------------------------------------------------------------------------- #
def test_multimap_keeps_repeated_keys_in_order():
    node = parse('changes:\n  + registry:\n      set: [1]\n'
                 '  + file:\n      delete: [2]\n'
                 '  + registry:\n      remove: [3]\n')
    mm = node.by_key["changes"]
    assert isinstance(mm, MultiMap)
    assert [e.key for e in mm.entries] == ["registry", "file", "registry"]
    assert mm.entries[2].value.by_key["remove"].items[0].value == 3


def test_multimap_entry_holds_exactly_one_pair():
    akan("+ a: 1\n  b: 2\n", "holds one key: value pair")


def test_multimap_entry_must_be_a_pair_not_a_bare_value():
    akan("+ 1\n", "not a bare value")


def test_multimaps_nest():
    node = parse("+ a:\n    + b: 1\n")
    inner = node.entries[0].value
    assert isinstance(inner, MultiMap)
    assert inner.entries[0].key == "b"


def test_a_block_is_a_mapping_a_sequence_or_a_multimap_never_a_mix():
    akan("+ a: 1\nb: 2\n", "not both")
    akan("+ a: 1\n- 2\n", "not both")
    akan("- 1\n+ a: 2\n", "not both")
    akan("a: 1\n+ b: 2\n", "not both")


def test_frames_interleave():
    node = parse('- + k: "v"\n')
    assert isinstance(node, Sequence)
    assert isinstance(node.items[0], MultiMap)
    assert node.items[0].entries[0].key == "k"


def test_multimap_keys_may_repeat_where_a_mapping_would_akan():
    akan("a: 1\na: 2\n", "duplicate key")            # mapping: akan (§7)
    node = parse("+ a: 1\n+ a: 2\n")                 # multimap: the point
    assert [e.value.value for e in node.entries] == [1, 2]


def test_multimap_has_no_flow_spelling():
    akan("x: {+ a: 1}\n", "only at the start of a line's content")


# --------------------------------------------------------------------------- #
# SPEC §8 — flow_list / flow_map
# --------------------------------------------------------------------------- #
def test_flow_list():
    node = parse("x: [1, 2, 3]\n")
    assert [i.value for i in node.by_key["x"].items] == [1, 2, 3]


def test_flow_map():
    node = parse("x: {burst: 100, sustained: 25}\n")
    assert node.by_key["x"].by_key["burst"].value == 100


def test_empty_flow_containers():
    node = parse("a: []\nb: {}\n")
    assert node.by_key["a"].items == [] and node.by_key["b"].pairs == []


def test_trailing_comma_is_permitted():
    assert len(parse("x: [1, 2,]\n").by_key["x"].items) == 2
    assert len(parse("x: {a: 1,}\n").by_key["x"].pairs) == 1


def test_commas_are_mandatory_in_flow():
    akan("x: [1 2]\n", "commas are mandatory")
    akan("x: {a: 1 b: 2}\n", "commas are mandatory")


def test_flow_containers_nest():
    node = parse("x: [{a: 1}, [2, 3]]\n")
    inner = node.by_key["x"].items
    assert inner[0].by_key["a"].value == 1
    assert [i.value for i in inner[1].items] == [2, 3]


# --------------------------------------------------------------------------- #
# SPEC §1 law 1 — no plain scalars
# --------------------------------------------------------------------------- #
def test_bare_word_in_value_position_is_akan():
    akan('x: hello\n', "no plain scalars")


def test_norway_problem_names_both_fixes():
    akan("country: no\n", 'write False for the value or "no" for the string')
    akan("x: TRUE\n", "write True for the value")


def test_no_inf_or_nan_spelling():
    akan("x: inf\n", "no inf/nan spelling")


def test_bare_word_inside_a_flow_list_is_akan():
    akan("x: [1, two]\n", "no plain scalars")


# --------------------------------------------------------------------------- #
# SPEC §7 — keys
# --------------------------------------------------------------------------- #
def test_duplicate_keys_are_akan_and_name_the_first():
    with pytest.raises(AkanError) as e:
        parse("a: 1\nb: 2\na: 3\n")
    assert "duplicate key 'a' (first defined on line 1)" in str(e.value)
    assert (e.value.line, e.value.col) == (3, 0)


def test_duplicate_keys_in_a_flow_map_are_akan():
    akan("x: {a: 1, a: 2}\n", "duplicate key 'a'")


def test_duplicate_keys_are_scoped_to_one_mapping():
    node = parse('a:\n  name: "x"\nb:\n  name: "y"\n')
    assert node.by_key["a"].by_key["name"].value == "x"
    assert node.by_key["b"].by_key["name"].value == "y"


def test_quoted_keys_are_akan():
    akan('"a": 1\n', "quoted keys are reserved")
    akan('x: {"a": 1}\n', "quoted keys are reserved")


def test_numeric_keys_are_akan():
    akan("1: 2\n", "numeric keys are akan")


def test_keywords_are_not_keys():
    akan("True: 1\n", "'True' is a keyword, not a key")


# --------------------------------------------------------------------------- #
# SPEC §3 / §5.4 — what the resolver will need off a scalar
# --------------------------------------------------------------------------- #
def test_numeric_scalars_keep_their_source_lexeme():
    node = parse("version: 3.10\nmask: 0xFF\nbig: 1_000\n")
    assert node.by_key["version"].value == 3.1
    assert node.by_key["version"].lexeme == "3.10"      # splices as written
    assert node.by_key["mask"].lexeme == "0xFF"
    assert node.by_key["big"].lexeme == "1_000"


def test_keyword_scalars_keep_their_lexeme():
    node = parse("a: True\nb: None\n")
    assert (node.by_key["a"].type, node.by_key["a"].lexeme) == ("bool", "True")
    assert (node.by_key["b"].type, node.by_key["b"].lexeme) == ("none", "None")


def test_bytes_scalars_keep_the_spelling_that_made_them():
    # The splice matrix (§5.5) admits b64-bytes into text and akans b-bytes.
    node = parse('a: b"hi"\nb: b64"aGk="\n')
    assert node.by_key["a"].value == node.by_key["b"].value == b"hi"
    assert node.by_key["a"].prefix == "b"
    assert node.by_key["b"].prefix == "b64"


def test_y_family_literals_stay_unresolved():
    node = parse('a: y"{host}/api"\nb: yt"Hello {user}"\nc: ry"^{n}\\d+"\n')
    a = node.by_key["a"]
    assert isinstance(a, YString) and a.type == "str"
    assert a.parts == [("hole", "host"), ("text", "/api")]
    assert node.by_key["b"].type == "template"
    assert node.by_key["c"].parts == [("text", "^"), ("hole", "n"),
                                      ("text", "\\d+")]


def test_every_node_carries_its_position():
    node = parse('server:\n  host: "h"\n')
    assert (node.line, node.col) == (1, 0)
    pair = node.pairs[0]
    assert (pair.line, pair.col) == (1, 0)
    inner = node.by_key["server"]
    assert (inner.line, inner.col) == (2, 2)
    assert (inner.by_key["host"].line, inner.by_key["host"].col) == (2, 8)


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #
def test_the_example_document_parses():
    node = parse(EXAMPLE.read_text())
    assert isinstance(node, Mapping)
    assert node.by_key["name"].value == "api-gateway"
    assert node.by_key["paths"].by_key["logs"].parts == [
        ("hole", "root"), ("text", "/logs")]
    assert node.by_key["magic"].by_key["png"].value == b"\x89PNG\r\n\x1a\n"
    assert len(node.by_key["allowed"].items) == 2
    changes = node.by_key["changes"]
    assert [e.key for e in changes.entries] == ["registry", "file", "registry"]
    assert node.by_key["retries"].items[0].by_key["attempts"].value == 3
