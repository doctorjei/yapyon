"""Independent acceptance cases for merge/source 0.6.0.dev0.

Expected data, the kind matrix, occurrence pairings, and continuation witnesses
are authored here, not obtained from the implementation's merge/equality code.
Only the source-no-evaluation test patches private evaluation entry points.
"""

from pathlib import Path
import re

import pytest

import yapyon
from yapyon import AkanError, Hole, OrderedMultimap, Template, merge, parse


FIXTURES = Path(__file__).parent / "fixtures" / "deferred-layer-case"


def _mm(*pairs):
    """Build expected data using the public container, not a merge oracle."""
    result = OrderedMultimap()
    for key, value in pairs:
        result.insert(key, value)
    return result


def _assert_value(actual, expected):
    """Do not let Python's True == 1 == 1.0 mask a wrong result."""
    if isinstance(expected, OrderedMultimap):
        assert isinstance(actual, OrderedMultimap)
        actual_pairs = [(entry.key, entry.value) for entry in actual]
        expected_pairs = [(entry.key, entry.value) for entry in expected]
        assert len(actual_pairs) == len(expected_pairs)
        for (ak, av), (ek, ev) in zip(actual_pairs, expected_pairs):
            assert ak == ek
            _assert_value(av, ev)
    elif isinstance(expected, Template):
        assert isinstance(actual, Template)
        assert len(actual.parts) == len(expected.parts)
        for ap, ep in zip(actual.parts, expected.parts):
            if isinstance(ep, Hole):
                assert isinstance(ap, Hole)
                assert (ap.ref, ap.lexeme) == (ep.ref, ep.lexeme)
                _assert_value(ap.value, ep.value)
            else:
                assert type(ap) is str and ap == ep
    elif isinstance(expected, dict):
        assert isinstance(actual, dict)
        assert actual.keys() == expected.keys()
        for key, value in expected.items():
            _assert_value(actual[key], value)
    elif isinstance(expected, list):
        assert type(actual) is list
        assert len(actual) == len(expected)
        for av, ev in zip(actual, expected):
            _assert_value(av, ev)
    else:
        assert type(actual) is type(expected)
        assert actual == expected


def _reload(tree):
    saved = tree.to_source()
    assert saved.endswith("\n")
    restored = parse(saved, source="saved.yap")
    assert restored.to_source() == saved
    return restored


def _assert_saved_value(tree, expected, **options):
    restored = _reload(tree)
    _assert_value(tree.resolve(**options), expected)
    _assert_value(restored.resolve(**options), expected)


def _expanded(tree, **options):
    # This is explicitly data output, unlike to_source. Its public handles let
    # representation assertions avoid depending on the private merge AST.
    return parse(yapyon.expand_record(tree.to_source(), **options))


# The rows/columns below are independent policy fixtures. L/R select an entire
# authored operand; D/S/M name the three explicitly specified combined results.
KINDS = ("none", "atom", "dict0", "dict1", "list0", "list1",
         "multi0", "multi1", "template")
LOWER = (
    ("None", None),
    ('"lower"', "lower"),
    ("{}", {}),
    ("{base: 1, shared: {a: 1}}", {"base": 1, "shared": {"a": 1}}),
    ("[]", []),
    ('[1, "keep", 1]', [1, "keep", 1]),
    ("{+}", _mm()),
    ("{+ a: 1, a: 2, a: 1}", _mm(("a", 1), ("a", 2), ("a", 1))),
    ('yt"lower"', Template(["lower"])),
)
HIGHER = (
    ("None", None),
    ('"higher"', "higher"),
    ("{}", {}),
    ("{shared: {b: 2}, over: 2}", {"shared": {"b": 2}, "over": 2}),
    ("[]", []),
    ("[1, 2, 1, 1]", [1, 2, 1, 1]),
    ("{+}", _mm()),
    ("{+ a: 1, b: 3, a: 1, a: 1}",
     _mm(("a", 1), ("b", 3), ("a", 1), ("a", 1))),
    ('yt"higher"', Template(["higher"])),
)
MATRIX = (
    "R R R R R R R R R",
    "R R R R R R R R R",
    "L R R R R R R R R",
    "L R L D R R R R R",
    "L R R R R R R R R",
    "L R R R L S R R R",
    "L R R R R R R R R",
    "L R R R R R L M R",
    "R R R R R R R R R",
)
COMBINED = {
    "D": {"base": 1, "shared": {"a": 1, "b": 2}, "over": 2},
    "S": [1, "keep", 1, 2, 1],
    "M": _mm(("a", 1), ("a", 2), ("a", 1), ("b", 3), ("a", 1)),
}
MATRIX_CASES = [pytest.param(i, j, MATRIX[i].split()[j],
                            id=f"{left}-{right}")
                for i, left in enumerate(KINDS) for j, right in enumerate(KINDS)]


@pytest.mark.parametrize("route", ["root-api", "field-api", "pipe"])
@pytest.mark.parametrize("i,j,choice", MATRIX_CASES)
def test_every_ordinary_kind_matrix_cell_including_empty_collections(route, i, j, choice):
    left_text, left_value = LOWER[i]
    right_text, right_value = HIGHER[j]
    expected = {"L": left_value, "R": right_value, **COMBINED}[choice]
    if route == "root-api":
        tree = merge(parse(left_text), parse(right_text))
    elif route == "field-api":
        tree = parse("field: " + left_text)
        tree["field"].merge(parse(right_text))
        expected = {"field": expected}
    else:
        tree = parse(f"{left_text} | {right_text}")
    _assert_saved_value(tree, expected)


@pytest.mark.parametrize("literal,value", [
    ('""', ""), ('b""', b""), ("0", 0), ("0.0", 0.0),
    ("False", False), ("True", True), ('yt""', Template([""])),
])
@pytest.mark.parametrize("other,other_value", [
    ("None", None), ("{}", {}), ("[]", []), ("{+}", _mm()),
])
def test_atomic_values_are_not_unset_none_or_truthiness(literal, value, other, other_value):
    _assert_saved_value(merge(parse(literal), parse(other)), other_value)
    _assert_saved_value(merge(parse(other), parse(literal)), value)


@pytest.mark.parametrize("i,j,choice", MATRIX_CASES)
def test_explicit_field_replacement_bypasses_every_matrix_cell(i, j, choice):
    tree = merge(parse("field: " + LOWER[i][0]), parse("field:= " + HIGHER[j][0]))
    _assert_saved_value(tree, {"field": HIGHER[j][1]})


@pytest.mark.parametrize("left,right,expected,lexemes", [
    ("[]", "[]", [], []),
    ("[]", "[1, 0o1]", [1, 1], ["1", "0o1"]),
    ("[0x1, 0b1]", "[]", [1, 1], ["0x1", "0b1"]),
    ("[0x1]", "[1, 0o1]", [1, 1], ["1", "0o1"]),
    ("[0x1, 0b1]", "[1]", [1, 1], ["1", "0b1"]),
    ("[0x1, 0b1]", "[1, 0o1, 0z1]", [1, 1, 1], ["1", "0o1", "0z1"]),
    ("[0x1, 0b1, 0o1]", "[1, 0z1]", [1, 1, 1], ["1", "0z1", "0o1"]),
    ('[0x1, "keep", 0b1]', '[1, "new", 0o1, "later", 0z1]',
     [1, "keep", 1, "new", "later", 1],
     ["1", '"keep"', "0o1", '"new"', '"later"', "0z1"]),
])
def test_list_maximum_counts_stable_positions_and_occurrence_representations(
        left, right, expected, lexemes):
    tree = merge(parse(left), parse(right))
    _assert_saved_value(tree, expected)
    assert [item.lexeme for item in _expanded(tree).root] == lexemes


@pytest.mark.parametrize("left,right,expected,lexemes", [
    ("{+}", "{+}", _mm(), []),
    ("{+}", "{+ a: 1, a: 0o1}", _mm(("a", 1), ("a", 1)), ["1", "0o1"]),
    ("{+ a: 0x1, a: 0b1}", "{+}", _mm(("a", 1), ("a", 1)), ["0x1", "0b1"]),
    ("{+ a: 0x1}", "{+ a: 1, a: 0o1}", _mm(("a", 1), ("a", 1)), ["1", "0o1"]),
    ("{+ a: 0x1, a: 0b1}", "{+ a: 1}", _mm(("a", 1), ("a", 1)), ["1", "0b1"]),
    ("{+ a: 0x1, a: 0b1}", "{+ a: 1, a: 0o1, a: 0z1}",
     _mm(("a", 1), ("a", 1), ("a", 1)), ["1", "0o1", "0z1"]),
    ("{+ a: 0x1, a: 0b1, a: 0o1}", "{+ a: 1, a: 0z1}",
     _mm(("a", 1), ("a", 1), ("a", 1)), ["1", "0z1", "0o1"]),
    ("{+ a: 0x1, a: 2, a: 0b1}", "{+ a: 1, b: 3, a: 0o1, a: 0z1}",
     _mm(("a", 1), ("a", 2), ("a", 1), ("b", 3), ("a", 1)),
     ["1", "2", "0o1", "3", "0z1"]),
])
def test_multimap_counts_pair_in_order_without_broadcast_or_new_append_targets(
        left, right, expected, lexemes):
    tree = merge(parse(left), parse(right))
    _assert_saved_value(tree, expected)
    expanded = yapyon.expand_record(tree.to_source())
    assert re.findall(r"\b[a-z]+\s*:\s*([^,}\s]+)", expanded) == lexemes


@pytest.mark.parametrize("text,expected", [
    ("[True] | [1] | [1.0]", [True, 1, 1.0]),
    ("[[True]] | [[1]] | [[1.0]]", [[True], [1], [1.0]]),
    ("[{x: [True]}] | [{x: [1]}] | [{x: [1.0]}]",
     [{"x": [True]}, {"x": [1]}, {"x": [1.0]}]),
    ("[{+ x: [True]}] | [{+ x: [1]}] | [{+ x: [1.0]}]",
     [_mm(("x", [True])), _mm(("x", [1])), _mm(("x", [1.0]))]),
    ("{+ a: True} | {+ a: 1} | {+ a: 1.0}",
     _mm(("a", True), ("a", 1), ("a", 1.0))),
    ("[[1, 2]] | [[2, 1]]", [[1, 2], [2, 1]]),
    ("[{+ a: 1, b: 2}] | [{+ b: 2, a: 1}]",
     [_mm(("a", 1), ("b", 2)), _mm(("b", 2), ("a", 1))]),
    ("[{a: 1}] | [{+ a: 1}]", [{"a": 1}, _mm(("a", 1))]),
    ("[{a: 1}] | [{b: 2}]", [{"a": 1}, {"b": 2}]),
    ("{+ a: {x: 1}} | {+ a: {y: 2}}", _mm(("a", {"x": 1}), ("a", {"y": 2}))),
    ('["é"] | ["é"]', ["é", "é"]),
    ('["hi"] | [b"hi"]', ["hi", b"hi"]),
    ('[b"hi"] | [b64"aGk="]', [b"hi"]),
])
def test_duplicate_equality_is_typed_recursive_and_content_based(text, expected):
    _assert_saved_value(parse(text), expected)


@pytest.mark.parametrize("left,right,winning", [
    ("0.0", "-0.0", "-0.0"),
    ("-0.0", "0.0", "0.0"),
    ("0x1", "0b1", "0b1"),
    ('b"hi"', 'b64"aGk="', 'b64"aGk="'),
    ('"hi"', 'r"hi"', 'r"hi"'),
])
def test_equal_scalar_data_takes_the_higher_whole_spelling(left, right, winning):
    tree = parse(f"[{left}] | [{right}]")
    assert len(tree.resolve()) == 1
    assert _expanded(tree)[0].lexeme == winning


@pytest.mark.parametrize("separator", [":", ":="])
def test_whole_dictionary_list_item_ignores_key_order_kind_and_operation_history(separator):
    tree = parse('[{a: 0x1, b: 2}] | [{"b": 2, "a"' + separator + ' 1}]')
    _assert_saved_value(tree, [{"b": 2, "a": 1}])
    expanded = _expanded(tree)
    assert expanded[0].keys() == ["b", "a"]
    assert expanded[0]["a"].key_lexeme() == '"a"'
    assert expanded[0]["a"].lexeme == "1"
    result = tree.resolve()
    with pytest.raises(AkanError):
        yapyon.lookup(result, result[0], "a")  # winning quoted key is not promoted
    wrapped = {"item": result[0]}
    assert yapyon.lookup(wrapped, result[0], 'item["a"]') == 1


def test_matching_one_dictionary_occurrence_does_not_replace_other_repeated_metadata():
    tree = parse('[{a: 1, b: 2}, {b: 2, a: 1}] | [{"b": 2, "a": 1}]')
    _assert_saved_value(tree, [{"b": 2, "a": 1}, {"b": 2, "a": 1}])
    record = _expanded(tree)
    assert record[0].keys() == ["b", "a"]
    assert record[0]["a"].key_lexeme() == '"a"'
    assert record[1].keys() == ["b", "a"]
    assert record[1]["a"].key_lexeme() == "a"


def test_a_matched_multimap_pair_takes_the_whole_higher_dictionary_representation():
    tree = parse('{+ a: {named: 1, other: 2}} | {+ a: {"other": 2, "named": 1}}')
    _assert_saved_value(tree, _mm(("a", {"other": 2, "named": 1})))
    for candidate in (tree, _reload(tree)):
        entries = list(candidate.resolve())
        assert len(entries) == 1
        value = entries[0].value
        assert list(value) == ["other", "named"]
        wrapped = {"item": value}
        assert yapyon.lookup(wrapped, value, 'item["named"]') == 1
        with pytest.raises(AkanError):
            yapyon.lookup(wrapped, value, "item.named")


def test_direct_dictionary_merge_instead_keeps_first_key_metadata_and_equal_values():
    tree = merge(parse('"name": 1\nｘ: {a: 1}\nkeep: 9'),
                 parse('name:= 2\nx: {b: 2}\nnew: 9'))
    restored = _reload(tree)
    for candidate in (tree, restored):
        _assert_value(candidate.resolve(), {"name": 2, "x": {"a": 1, "b": 2},
                                            "keep": 9, "new": 9})
        assert candidate.keys() == ["name", "x", "keep", "new"]
        assert candidate["name"].key_lexeme() == '"name"'
        assert candidate["x"].key_lexeme() == "ｘ"
        candidate.merge(parse('out: (name)'))
        with pytest.raises(AkanError):
            candidate.resolve()


@pytest.mark.parametrize("left,right,expected", [
    ('yt"Hello Ada"', 'yt"Hello {__str__(\'Ada\')}"',
     [Template(["Hello Ada"]), Template(["Hello ", Hole("__str__('Ada')", "Ada"), ""])]),
    ('yt"{n}"', 'yt"{__ROOT__.n}"',
     [Template(["", Hole("n", 1, "1"), ""]),
      Template(["", Hole("__ROOT__.n", 1, "1"), ""])]),
])
def test_templates_compare_delivered_structure_and_reference_text_not_rendered_text(
        left, right, expected):
    tree = parse(f"n: 1\nitems: [{left}] | [{right}]")
    for candidate in (tree, _reload(tree)):
        _assert_value(candidate.resolve()["items"], expected)


@pytest.mark.parametrize("left_value,right_value,expected_count", [
    ("1", "1", 1),                    # only diagnostic locations differ
    ("0x1", "1", 2),                  # delivered hole lexemes differ
    ("[True]", "[1]", 2),              # same empty lexeme, typed nested values differ
    ("{x: True}", "{x: 1.0}", 2),
])
def test_templates_keep_hole_lexemes_and_typed_values_but_ignore_locations(
        left_value, right_value, expected_count):
    tree = merge(parse(f"left: {{n: {left_value}, t: yt\"{{n}}\"}}", source="left.yap"),
                 parse(f"right: {{n: {right_value}, t: yt\"{{n}}\"}}", source="right.yap"),
                 parse("items: [(left.t)] | [(right.t)]"))
    for candidate in (tree, _reload(tree)):
        result = candidate.resolve()["items"]
        assert len(result) == expected_count
        assert all(isinstance(value, Template) for value in result)
        assert all(value.holes[0].ref == "n" for value in result)


@pytest.mark.parametrize("text,expected", [
    ("True == 1", True), ("1 == 1.0", True), ("True != 1.0", False),
    ("[True] == [1]", True),
])
def test_expression_equality_keeps_its_independent_numeric_semantics(text, expected):
    assert yapyon.loads(text) is expected


# Separator spellings and expression grouping are tested as source, not lexer
# token snapshots. This keeps the tests independent of private token names.
@pytest.mark.parametrize("key", ["field", '"field"', "'field'",
                                 'y"field"', 'ry"field"'])
@pytest.mark.parametrize("separator", [":=", ": =", " :\t=", " : = "])
def test_replacement_separator_accepts_all_key_forms_and_token_whitespace(key, separator):
    tree = merge(parse("field: {old: 1}"), parse(f"{key}{separator} {{new: 2}}"))
    _assert_saved_value(tree, {"field": {"new": 2}})


@pytest.mark.parametrize("key", ["field", '"field"', "'field'",
                                 'y"field"', 'ry"field"'])
@pytest.mark.parametrize("separator", [":=", " : = ", ":\n =\n "])
def test_replacement_with_labels_and_flow_newlines_replaces_with_a_fresh_slot(key, separator):
    tree = merge(parse("field<old>: {inherited: 1}"),
                 parse("{" + key + " < new > " + separator + "{}}"))
    restored = _reload(tree)
    for candidate in (tree, restored):
        slots = candidate.slots()
        labels = [("old",), ("new",)] if key.startswith(("y", "ry")) else [("new",)]
        assert [slot.label for slot in slots] == labels
        for slot in slots:
            slot.fill(parse("42"))
        _assert_value(candidate.resolve(), {"field": 42})


@pytest.mark.parametrize("rhs,expected", [
    ("None", None), ("{}", {}), ("[]", []), ("{+}", _mm()),
    ("{new: 2} | {more: 3}", {"new": 2, "more": 3}),
    ('({new: 2} | "reset") | {last: 4}', {"last": 4}),
])
def test_replacement_intent_survives_a_save_before_it_has_an_earlier_value(rhs, expected):
    patch = parse("field:= " + rhs)
    saved_patch = _reload(patch)
    for candidate in (patch, saved_patch):
        applied = merge(parse("field: {inherited: 1}"), candidate)
        _assert_saved_value(applied, {"field": expected})
    # Replacing is not deletion, and a later ordinary contribution still applies.
    out = merge(parse("field: {inherited: 1}"), saved_patch, parse("field: {after: 5}"))
    if isinstance(expected, dict):
        _assert_value(out.resolve(), {"field": {**expected, "after": 5}})
    else:
        _assert_value(out.resolve(), {"field": {"after": 5}})


@pytest.mark.parametrize("text", [
    "field: =", "field::= 1", "field:== 1", "field: = = 1", "field = 1",
    "= 1", "| {}", "{} |", "{} || {}", "{} | | {}",
    "field:\n = 1", "{+ field<label>:= {}}", "{x<label>:= 1 for x in []}",
    'r"field":= 1', 'r"field"<chosen>:= {}',
    'y"{left | right}"', 'left: {}\nright: {}\nout: left',
])
def test_malformed_separators_pipes_labels_and_unchanged_reference_grammar_are_located(text):
    with pytest.raises(AkanError) as err:
        parse(text, source="invalid.yap")
    assert err.value.source == "invalid.yap"
    assert err.value.line >= 1 and err.value.col >= 0


@pytest.mark.parametrize("text", [
    '{data: {old: 1}} | {data: "reset"} | {data: {new: 2}}',
    'data: {old: 1}\n|\ndata: "reset"\n|\ndata: {new: 2}',
    '{data: {old: 1}} | {data: "reset"}\n|\ndata: {new: 2}',
    'data: {old: 1}\n| {data: "reset"} | {data: {new: 2}}',
    'data: {old: 1}\n| {data: "reset"}\n|\n{data: {new: 2}}',
])
def test_inline_block_and_mixed_chains_share_left_association(text):
    _assert_saved_value(parse(text), {"data": {"new": 2}})


@pytest.mark.parametrize("grouped,expected", [
    (False, {"data": {"new": 2}}),
    (True, {"data": {"old": 1, "new": 2}}),
])
def test_right_grouping_is_preserved_by_api_composition_and_saving(grouped, expected):
    first = parse("data: {old: 1}")
    middle = parse('data: "reset"')
    last = parse("data: {new: 2}")
    tree = merge(first, merge(middle, last)) if grouped else merge(first, middle, last)
    _assert_saved_value(tree, expected)


@pytest.mark.parametrize("text,expected", [
    ('{data: {old: 1}} | ({data: "reset"} | {data: {new: 2}})',
     {"data": {"old": 1, "new": 2}}),
    ('outer: {data: {old: 1}} | ({data: "reset"} | {data: {new: 2}})',
     {"outer": {"data": {"old": 1, "new": 2}}}),
    ('outer:\n  old: 1\n  |\n  "reset"\n  |\n  {new: 2}', {"outer": {"new": 2}}),
    ("True or False | False", False),
    ("True or (False | False)", True),
    ("False | True and False", False),
    ("1 == 1 | False", False),
    ("({a: 1} | {b: 2}).a", 1),
    ("([1] | [2])[0]", 1),
    ('(["a"] | ["b"]).__get__(-1)', "b"),
    ("left: {a: 1}\nright: {b: 2}\nout: (left | right)",
     {"left": {"a": 1}, "right": {"b": 2}, "out": {"a": 1, "b": 2}}),
    ('text: "| :="\nitems: ["a|b", ":=", "="] # | {}\n',
     {"text": "| :=", "items": ["a|b", ":=", "="]}),
    ('items:\n  - [1] | [2]\n  - []\nmm:\n  + a:= [1] | [2]\n  + a: 3',
     {"items": [[1, 2], []], "mm": _mm(("a", [1, 2]), ("a", 3))}),
])
def test_nested_grouping_precedence_postfix_and_existing_layout(text, expected):
    _assert_saved_value(parse(text), expected)


@pytest.mark.parametrize("kind,body,expected", [
    ("dict-flow", '{item: {side: "left", bound: (item)} for item in left if item != "skip-left"}'
     ' | {item: {side: "right", bound: (item)} for item in right if item != "skip-right"}',
     {"a": {"side": "left", "bound": "a"}, "common": {"side": "right", "bound": "common"},
      "b": {"side": "right", "bound": "b"}}),
    ("dict-block", '\n  item: {side: "left", bound: (item)}\n  for item in left\n'
     '  if item != "skip-left"\n  |\n  item: {side: "right", bound: (item)}\n'
     '  for item in right\n  if item != "skip-right"',
     {"a": {"side": "left", "bound": "a"}, "common": {"side": "right", "bound": "common"},
      "b": {"side": "right", "bound": "b"}}),
    ("dict-mixed", '\n  item: {side: "left", bound: (item)}\n  for item in left\n'
     '  if item != "skip-left"\n  | {item: {side: "right", bound: (item)} '
     'for item in right if item != "skip-right"}',
     {"a": {"side": "left", "bound": "a"}, "common": {"side": "right", "bound": "common"},
      "b": {"side": "right", "bound": "b"}}),
    ("list-flow", '[item for item in left if item != "skip-left"]'
     ' | [item for item in right if item != "skip-right"]', ["a", "common", "b"]),
    ("list-block", '\n  - item\n  for item in left\n  if item != "skip-left"\n'
     '  |\n  - item\n  for item in right\n  if item != "skip-right"', ["a", "common", "b"]),
    ("multimap-flow", '{+ "same": item for item in left if item != "skip-left"}'
     ' | {+ "same": item for item in right if item != "skip-right"}',
     _mm(("same", "a"), ("same", "common"), ("same", "b"))),
    ("multimap-block", '\n  + "same": item\n  for item in left\n  if item != "skip-left"\n'
     '  |\n  + "same": item\n  for item in right\n  if item != "skip-right"',
     _mm(("same", "a"), ("same", "common"), ("same", "b"))),
])
def test_two_comprehensions_have_independent_heads_filters_and_lexical_frames(kind, body, expected):
    tree = parse('item: "outer"\nleft: ["a", "common", "skip-left"]\n'
                 'right: ["common", "b", "skip-right"]\nrows: ' + body + '\nafter: (item)')
    for candidate in (tree, _reload(tree)):
        result = candidate.resolve()
        _assert_value(result["rows"], expected)
        assert result["after"] == "outer"


def test_independently_authored_override_does_not_inherit_a_comprehension_binding():
    tree = parse('item: "outer"\ninput: ["a"]\nrows: '
                 '{item: {bound: (item), kept: 1} for item in input}'
                 ' | {"a": {outside: (item)}}')
    _assert_saved_value(tree, {"item": "outer", "input": ["a"],
                               "rows": {"a": {"bound": "a", "kept": 1, "outside": "outer"}}})


@pytest.mark.parametrize("body", [
    '{item:= {new: 2} for item in input}',
    '\n  item : = {new: 2}\n  for item in input',
])
def test_generated_dictionary_separator_preserves_replacement_intent(body):
    tree = merge(parse('input: ["a"]\nrows: {"a": {old: 1}}'), parse("rows: " + body))
    _assert_saved_value(tree, {"input": ["a"], "rows": {"a": {"new": 2}}})


@pytest.mark.parametrize("text", [
    'name:= 1\nname: 2',
    'name: 1\nｎａｍｅ:= 2',
    'y"name":= 1\ny"name": 2',
    'input: ["a", "a"]\nrows: {item:= 1 for item in input}',
])
def test_replacement_does_not_legalize_same_contribution_duplicate_keys(text):
    with pytest.raises(AkanError, match="duplicate key"):
        # Some duplicates are statically known; others wait until resolve.
        parse(text).resolve()


@pytest.mark.parametrize("lower,upper,expected", [
    ('rows: {item: {bad: (missing)} for item in ["a"]}',
     'rows: {"a":= {ok: True}}', {"rows": {"a": {"ok": True}}}),
    ('rows: {y"key": {bad: (missing)}}',
     'rows:= {good: 1}', {"rows": {"good": 1}}),
    ('rows: {old: (missing)}', 'rows: "reset"', {"rows": "reset"}),
])
def test_discarded_dictionary_bodies_do_not_run(lower, upper, expected):
    _assert_saved_value(merge(parse(lower), parse(upper)), expected)


@pytest.mark.parametrize("text", [
    '[{bad: (missing)}] | [{bad: 1}]',
    '{+ a: (missing)} | {+ a: 1}',
    'value: {bad: (missing)}\nout: (value) | {bad:= 1}',
    'rows: {bad: (missing)} | None',
])
def test_required_comparisons_copies_and_none_do_not_hide_missing_values(text):
    tree = parse(text, source="missing.yap")
    for candidate in (tree, _reload(tree)):
        with pytest.raises(AkanError):
            candidate.resolve()


@pytest.mark.parametrize("text,expected", [
    ('data: {y"{later}": {a: 1}} | {"x": {b: 2}}\nlater: (last)\nlast: "x"',
     {"data": {"x": {"a": 1, "b": 2}}, "later": "x", "last": "x"}),
    ('out: (later) | [2]\nlater: (last)\nlast: [1]',
     {"out": [1, 2], "later": [1], "last": [1]}),
    ('data: {"x": {b: 2}} | {y"{later}": {a: 1}}\nlast: "x"\nlater: (last)',
     {"data": {"x": {"b": 2, "a": 1}}, "last": "x", "later": "x"}),
])
def test_late_keys_and_forward_operand_values_use_the_existing_fixpoint(text, expected):
    _assert_saved_value(parse(text), expected)


@pytest.mark.parametrize("name,expected_rows", [
    ('"x"', {"x": {"a": 1, "b": 2}}),
    ('"y"', {"y": {"a": 1}, "x": {"b": 2}}),
])
def test_saved_computed_key_layers_continue_under_later_edits_without_key_promotion(name, expected_rows):
    tree = merge(parse('name: "x"\nrows: {y"{name}": {a: 1}}'),
                 parse('rows: {x: {b: 2}}'))
    restored = _reload(tree)
    for candidate in (tree, restored):
        candidate["name"].replace(parse(name))
        result = candidate.resolve()
        _assert_value(result["rows"], expected_rows)
        assert yapyon.lookup(result, result, 'rows["x"]') == expected_rows["x"]
        if name == '"x"':
            with pytest.raises(AkanError):
                yapyon.lookup(result, result, "rows.x")
        else:
            _assert_value(yapyon.lookup(result, result, "rows.x"), {"b": 2})


@pytest.mark.parametrize("text", [
    'a: (b) | {}\nb: (a) | {}',
    'a: [(b)] | []\nb: [(a)] | []',
    'a: {x: (b)} | {}\nb: {x: (a)} | {}',
])
def test_cycles_through_merge_comparison_and_copy_are_still_located_akan(text):
    tree = parse(text, source="cycle.yap")
    for candidate, source in ((tree, "cycle.yap"), (_reload(tree), "saved.yap")):
        with pytest.raises(AkanError, match="cycle|circular") as err:
            candidate.resolve()
        assert err.value.source == source


@pytest.fixture
def make_contract():
    return yapyon.loads_contract('MAKE:\n  params: {}\n  returns: "Any"\n'
                                 '  impl: {python: {symbol: "make"}}')


@pytest.mark.parametrize("origin", ["call", "copy"])
@pytest.mark.parametrize("runtime,other,expected", [
    (None, "None", None),
    (42, "None", None),
    ({}, "None", {}),
    ({"a": 1}, "None", {"a": 1}),
    ([], "None", []),
    ([1], "None", [1]),
    (_mm(), "None", _mm()),
    (_mm(("a", 1)), "None", _mm(("a", 1))),
    ({"a": 1}, "{b: 2}", {"a": 1, "b": 2}),
    ([1, 1], "[1, 2]", [1, 1, 2]),
    (_mm(("a", 1)), "{+ a: 1, a: 2}", _mm(("a", 1), ("a", 2))),
    ({"a": 1}, "[]", []),
])
def test_runtime_call_and_copy_kinds_join_the_same_matrix(origin, runtime, other, expected, make_contract):
    literal = {type(None): "None", int: "42"}.get(type(runtime))
    if isinstance(runtime, dict):
        literal = "{a: 1}" if runtime else "{}"
    elif isinstance(runtime, list):
        literal = "[1, 1]" if runtime == [1, 1] else "[1]" if runtime else "[]"
    elif isinstance(runtime, OrderedMultimap):
        literal = "{+ a: 1}" if len(runtime) else "{+}"
    calls = []

    def make():
        calls.append("called")
        return runtime

    text = "value: MAKE()" if origin == "call" else f"provided: {literal}\nvalue: (provided)"
    tree = merge(parse(text), parse("value: " + other))
    restored = _reload(tree)
    assert calls == []
    for candidate in (tree, restored):
        result = candidate.resolve(contract=make_contract, provide={"make": make})
        _assert_value(result["value"], expected)
    assert bool(calls) is (origin == "call")


@pytest.mark.parametrize("runtime,lower,expected", [
    ({"b": 2}, "{a: 1}", {"a": 1, "b": 2}),
    ([2, 2], "[1, 2]", [1, 2, 2]),
    (_mm(("a", 2)), "{+ a: 1}", _mm(("a", 1), ("a", 2))),
    (None, "{a: 1}", {"a": 1}),
    (None, "[1]", [1]),
])
def test_incoming_call_results_are_not_classified_by_their_parse_node(
        runtime, lower, expected, make_contract):
    tree = merge(parse("value: " + lower), parse("value: MAKE()"))
    _assert_saved_value(tree, {"value": expected}, contract=make_contract,
                        provide={"make": lambda: runtime})


@pytest.mark.parametrize("kind", ["list", "multimap"])
@pytest.mark.parametrize("runtime,expected_values", [
    (True, [True, 1]), (1, [1]), (1.0, [1.0, 1]),
])
def test_collection_duplicates_wait_for_runtime_values_and_compare_their_kinds(
        kind, runtime, expected_values, make_contract):
    text = '[MAKE()] | [1]' if kind == "list" else '{+ a: MAKE()} | {+ a: 1}'
    expected = expected_values if kind == "list" else _mm(*[("a", value) for value in expected_values])
    calls = []

    def make():
        calls.append("called")
        return runtime

    tree = parse(text)
    restored = _reload(tree)
    assert not calls
    for candidate in (tree, restored):
        _assert_value(candidate.resolve(contract=make_contract, provide={"make": make}), expected)
    assert calls


@pytest.mark.parametrize("home,expected", [
    ("fixed", ["fixed"]), ("changed", ["changed", "fixed"]),
])
def test_saved_pending_comparisons_read_the_later_environment_after_runtime_fill(home, expected):
    tree = parse('items: [y"{$HOME}"] | ["fixed"]\npart<runtime>: {}')
    restored = _reload(tree)
    for candidate in (tree, restored):
        candidate["part"].fill(parse("None"))
        _assert_value(candidate.resolve(env={"HOME": home}, env_allow={"HOME"}),
                      {"items": expected, "part": None})


def test_inline_bodies_use_final_scope_but_a_copy_is_finished_data():
    tree = parse('original: {name: "first", value: y"{name}"}\n'
                 'inline: {name: "new"} | {value: y"{name}"}\n'
                 'copied: (original) | {name: "new"}')
    _assert_saved_value(tree, {
        "original": {"name": "first", "value": "first"},
        "inline": {"name": "new", "value": "new"},
        "copied": {"name": "new", "value": "first"},
    })


def test_a_known_dominating_value_discards_a_call_without_invoking_it(make_contract):
    def forbidden():
        pytest.fail("discarded call was evaluated")

    for upper in ('value: "done"', 'value:= None', 'value:= {}'):
        tree = merge(parse("value: MAKE()"), parse(upper))
        for candidate in (tree, _reload(tree)):
            candidate.resolve(contract=make_contract, provide={"make": forbidden})


@pytest.mark.parametrize("filler,later,expected", [
    ("None", "None", None), ("42", "None", None),
    ("{}", "None", {}), ("{value: 1}", "None", {"value": 1}),
    ("[]", "None", []), ("[1]", "None", [1]),
    ("{+}", "None", _mm()), ("{+ a: 1}", "None", _mm(("a", 1))),
    ("[1]", "[2]", [1, 2]), ("[1, 1]", "[1, 2]", [1, 1, 2]),
    ("[1]", "[]", [1]), ("[]", "[2]", [2]),
    ("{value: 1}", "[2]", [2]), ("42", "[2]", [2]),
    ("{+ a: 1}", "{+ a: 1, a: 2}", _mm(("a", 1), ("a", 2))),
    ("{+ a: 1}", "{+}", _mm(("a", 1))),
    ("{+}", "{+ a: 2}", _mm(("a", 2))),
    ("[1]", "{+ a: 2}", _mm(("a", 2))),
])
def test_named_slot_pending_kind_matches_merging_after_the_equivalent_fill(filler, later, expected):
    pending = parse("part<base>: {}", source="slot.yap")
    handle = pending["part"]
    pending["part"].merge(parse(later))
    assert pending["part"].label == ("base",)
    assert len(pending.slots()) == 1
    with pytest.raises(AkanError, match="unfilled"):
        pending.resolve()
    restored = _reload(pending)
    before_fill = parse("part<base>: {}")
    before_fill["part"].fill(parse(filler))
    before_fill["part"].merge(parse(later))
    for candidate in (pending, restored):
        candidate["part"].fill(parse(filler))
        _assert_value(candidate.resolve(), {"part": expected})
    _assert_value(before_fill.resolve(), {"part": expected})
    assert not pending.slots()
    # A saved source operation does not invalidate the live logical location.
    handle.replace(parse("99"))
    assert handle.value == 99


@pytest.mark.parametrize("filler,expected", [
    ("None", None), ("42", 42), ('""', ""), ("False", False),
    ("[]", []), ("[1, 1]", [1, 1]), ("{}", {}),
    ("{+ a: 1, a: 1}", _mm(("a", 1), ("a", 1))),
])
@pytest.mark.parametrize("separator", [":", ":="])
def test_literal_empty_slot_overrides_are_identity_for_every_filler_kind(filler, expected, separator):
    tree = parse("part<base>" + separator + " {}")
    for candidate in (tree, _reload(tree)):
        candidate["part"].fill(parse(filler))
        _assert_value(candidate.resolve(), {"part": expected})


def test_unmaterialized_comprehension_overrides_are_not_mistaken_for_literal_empty_overrides():
    tree = parse('input: ["x"]\npart<base>: {item: {value: (item)} for item in input}')
    for candidate in (tree, _reload(tree)):
        candidate["part"].fill(parse("{}"))
        _assert_value(candidate.resolve(), {"input": ["x"], "part": {"x": {"value": "x"}}})


@pytest.mark.parametrize("over,expected", [
    ("part:= None", None), ("part:= []", []), ("part:= {}", {}),
    ("part:= {+}", _mm()), ('part: "done"', "done"), ("part: False", False),
])
def test_dominating_replacement_or_atomic_value_removes_the_unneeded_slot(over, expected):
    tree = merge(parse("part<base>: {bad: (missing)}"), parse(over))
    assert tree.slots() == []
    _assert_saved_value(tree, {"part": expected})


@pytest.mark.parametrize("filler,premerged_expected", [
    ("config: {old: 1}", {"old": 1, "new": 2}),
    ("config: [1]", {"new": 2}),
    ("config: None", {"new": 2}),
])
def test_sequential_and_premerged_slot_histories_remain_distinct_after_save(filler, premerged_expected):
    first, last = parse('config: "reset"'), parse("config: {new: 2}")
    sequential = parse("part<base>: {}")
    sequential["part"].merge(first)
    sequential["part"].merge(last)
    premerged = parse("part<base>: {}")
    premerged["part"].merge(merge(first, last))
    for tree, expected in ((sequential, {"new": 2}), (premerged, premerged_expected)):
        for candidate in (tree, _reload(tree)):
            candidate["part"].fill(parse(filler))
            _assert_value(candidate.resolve(), {"part": {"config": expected}})


@pytest.mark.parametrize("text,expected", [
    ('part<base>: {config: "reset"} | {config: {new: 2}}', {"old": 1, "new": 2}),
    ('part<base>:\n  config: "reset"\n  |\n  config: {new: 2}', {"old": 1, "new": 2}),
    ('part<base>: {config: "reset"}\n|\npart: {config: {new: 2}}', {"new": 2}),
])
def test_labeled_complete_rhs_is_one_contribution_not_sequential_slot_operations(text, expected):
    tree = parse(text)
    for candidate in (tree, _reload(tree)):
        candidate["part"].fill(parse("config: {old: 1}"))
        _assert_value(candidate.resolve(), {"part": {"config": expected}})


@pytest.mark.parametrize("lower_label,upper_label,expected", [
    ("", "next", {"lower": 1, "upper": 2, "filler": 3}),
    ("", "", {"lower": 1, "upper": 2, "filler": 3}),
    ("old", "next", {"upper": 2, "filler": 3}),
    ("old", "", {"upper": 2, "filler": 3}),
])
def test_slot_choice_precedes_application_of_its_retained_overrides(lower_label, upper_label, expected):
    tree = merge(parse(f"part<{lower_label}>: {{lower: 1}}"),
                 parse(f"part<{upper_label}>: {{upper: 2}}"))
    for candidate in (tree, _reload(tree)):
        assert candidate["part"].abstract is (not upper_label)
        candidate["part"].fill(parse("filler: 3"))
        _assert_value(candidate.resolve(), {"part": expected})


def test_historical_fill_obligation_still_refuses_saving_and_has_a_continuation_witness():
    tree = parse("part<base>: {other: 42}", source="user.yap")
    tree["part"].fill(parse('name: "x"\ny"need_{name}"<>: {}', source="base.yap"))
    with pytest.raises(AkanError, match="undecided abstract-slot obligation") as err:
        tree.to_source()
    assert err.value.source == "user.yap"
    assert (err.value.line, err.value.col) == (1, 4)
    # An ordinary abstract slot would falsely let this later contribution repair
    # what the original completed fill's own overrides failed to provide.
    naive = parse('part: {name: "x", y"need_{name}"<>: {}, other: 42}')
    later = parse("part: {need_x: {done: True}}")
    tree.merge(later)
    naive.merge(later)
    with pytest.raises(AkanError, match="overrides must give that key a value") as err:
        tree.resolve()
    assert err.value.source == "user.yap"
    _assert_value(naive.resolve(), {"part": {"name": "x", "need_x": {"done": True}, "other": 42}})


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("same,expected", [
    (True, [{"part": {"value": 1}}]),
    (False, [{"part": {"value": 1}}, {"part": {"value": 2}}]),
])
def test_retained_collection_slots_have_stable_fill_handles_not_guessed_effective_indices(
        reverse, same, expected):
    tree = merge(parse("[{part<one>: {}}]", source="one.yap"),
                 parse("[{part<two>: {}}]", source="two.yap"))
    restored = _reload(tree)
    for candidate in (tree, restored):
        handles = candidate.slots()
        assert [handle.label for handle in handles] == [("one",), ("two",)]
        assert [handle.key for handle in handles] == ["part", "part"]
        with pytest.raises((KeyError, TypeError, IndexError)):
            candidate[0]
        with pytest.raises(TypeError):
            len(candidate)
        selected = list(reversed(handles)) if reverse else handles
        for handle in selected:
            value = 1 if same or handle.label == ("one",) else 2
            handle.fill(parse(f"value: {value}"))
        _assert_value(candidate.resolve(), expected)


def test_merge_fill_and_edits_take_independent_copies_and_keep_live_locations():
    base = parse("items: [{part<chosen>: {}}]\nkeep: 1")
    over = parse("items: [{part<other>: {}}]")
    left, right = merge(base, over), merge(base, over)
    left_slots = left.slots()
    for slot in left_slots:
        slot.fill(parse("value: 1"))
    assert len(base.slots()) == 1 and len(over.slots()) == 1
    assert len(right.slots()) == 2
    keep = left["keep"]
    snapshot = (keep.where, keep.lexeme, list(left.warnings))
    saved = left.to_source()
    assert (keep.where, keep.lexeme, left.warnings) == snapshot
    assert saved == left.to_source()
    left["items"].replace(parse("[]"))
    keep.replace(parse("2"))
    assert keep.value == 2
    keep.remove()
    with pytest.raises(KeyError):
        keep.value
    _assert_value(left.resolve(), {"items": []})
    assert base["keep"].value == 1 and right["keep"].value == 1


@pytest.mark.parametrize("context", ["root", "sequence"])
def test_unattached_slots_still_refuse_without_inventing_a_source_wrapper(context):
    slot = parse("part<base>: {}")["part"]
    tree = parse("{}" if context == "root" else "[0]")
    (tree.root if context == "root" else tree[0]).replace(slot)
    with pytest.raises(AkanError, match="attached to a dictionary key"):
        tree.to_source()


@pytest.mark.parametrize("models,expected", [
    (None, {"m1": {"provider": "example", "remote_model_id": "m1"},
            "m2": {"provider": "example", "remote_model_id": "m2"},
            "extra": {"provider": "provider", "remote_model_id": "remote-extra"}}),
    ('["m1", "extra"]', {"m1": {"provider": "example", "remote_model_id": "m1"},
                          "extra": {"provider": "provider", "remote_model_id": "remote-extra"}}),
    ('["changed"]', {"changed": {"provider": "example", "remote_model_id": "changed"},
                     "extra": {"provider": "provider", "remote_model_id": "remote-extra"}}),
])
def test_four_file_pg_workflow_saves_unfilled_runtime_and_continues_with_changed_models(models, expected):
    base = yapyon.parse_file(FIXTURES / "base.tmpl")
    codex = yapyon.parse_file(FIXTURES / "codex.tmpl")
    custom = yapyon.parse_file(FIXTURES / "custom.tmpl")
    codex["harness"].fill(base)
    custom["harness"].fill(codex)
    custom["harness"].merge(parse("runtime<runtime>: {}", source="runtime.tmpl"))
    runtime = custom.slots()[0]
    before = (runtime.label, runtime.where, runtime.key, list(custom.warnings))
    restored = _reload(custom)
    assert (runtime.label, runtime.where, runtime.key, custom.warnings) == before
    assert [slot.label for slot in restored.slots()] == [("runtime",)]
    assert "for model_id in persona.mind.model_list" in custom.to_source()
    assert not codex.slots() and base.resolve() == {"harness": {}}
    agents = []
    for component in (custom, restored):
        agent = yapyon.parse_file(FIXTURES / "agent.yap")
        agent["harness"].fill(component)
        if models is not None:
            agent["persona"]["mind"]["model_list"].replace(parse(models))
        assert [slot.label for slot in agent.slots()] == [("runtime",)]
        with pytest.raises(AkanError, match="unfilled"):
            agent.resolve()
        agent.slots()[0].fill(parse("ready: True"))
        result = agent.resolve()
        _assert_value(result["harness"]["config_store"]["models"], expected)
        assert result["harness"]["runtime"] == {"ready": True}
        agents.append(result)
    _assert_value(agents[0], agents[1])
    # Filling a component's copied-in runtime does not fill the saved component.
    assert [slot.label for slot in custom.slots()] == [("runtime",)]


def test_source_save_performs_no_resolution_lookup_call_iteration_render_or_environment_read(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("source preparation evaluated unfinished data")

    for target in (
        "yapyon.tree.resolve", "yapyon.tree.environment", "yapyon.resolver.resolve",
        "yapyon.resolver.Resolver.resolve", "yapyon.resolver.Resolver._lookup",
        "yapyon.resolver.Resolver._call", "yapyon.resolver.Resolver._env",
        "yapyon._expressions.evaluate", "yapyon._expressions._comprehend",
        "yapyon.environment.Environment.get", "yapyon.Template.render",
        "yapyon.emitter.emit", "yapyon.assembly.collection_merge",
        "yapyon.assembly._fingerprint",
    ):
        monkeypatch.setattr(target, forbidden)
    tree = merge(
        parse('name: "x"\ninput: ["a"]\n'
              'rows: {item: {value: (item)} for item in input}\n'
              'data: {y"{name}": (name)}\nitems: [(name)]\n'
              'home: y"{$HOME}"\ncall: MAKE()\ncast: __int__("3")\n'
              'encoded: name.__as_json__()\ntemplate: yt"{name}"\npart<base>: {}',
              source="original.yap"),
        parse('rows: {"extra": 1}\ndata: {x: 2}\nitems: ["x", "x"]\npart: None'),
    )
    handle = tree["part"]
    before = (handle.label, handle.where, handle.key, list(tree.warnings))
    saved = tree.to_source()
    assert "|" in saved and "for item in input" in saved
    assert "MAKE()" in saved and '{$HOME}' in saved and 'yt"{name}"' in saved
    assert parse(saved).to_source() == saved
    assert (handle.label, handle.where, handle.key, tree.warnings) == before


def test_reloaded_pending_layers_use_saved_locations_without_mutating_original_errors():
    tree = merge(parse('# header\n\ndata: {y"{missing}": 1}', source="old.yap"),
                 parse("data: {x: 2}", source="over.yap"))
    key = tree["data"].keys()[0]
    handle = tree["data"][key]
    before = (handle.where, handle.lexeme, list(tree.warnings))
    restored = _reload(tree)
    assert (handle.where, handle.lexeme, tree.warnings) == before
    for candidate, source in ((tree, "old.yap"), (restored, "saved.yap")):
        with pytest.raises(AkanError) as err:
            candidate.resolve()
        assert err.value.source == source
    handle.replace(parse("3"))
    assert handle.value == 3


@pytest.mark.parametrize("text,record,tier", [
    ("field:= {a: [1, 1]}", True, 1),
    ("{field:\n =\n []}", True, 1),
    ("{+ a:= 1, a: 1}", True, 1),
    ('text: "| :=" # | {}', True, 1),
    ("{} | {}", False, 2),
    ("field: [1] | [2]", False, 2),
    ("True or ({} | {})", False, 2),
    ('field: yt"literal"', False, 3),
    ("part<base>:= {}", False, 3),
])
def test_replacement_is_record_but_explicit_pipe_is_syntactically_at_least_ledger(text, record, tier):
    assert yapyon.is_record(text) is record
    assert yapyon.tier_of(text) == tier
    tree = parse(text)
    restored = _reload(tree)
    assert yapyon.tier_of(tree.to_source()) == tier
    if record:
        _assert_value(yapyon.loads_record(text), tree.resolve())
        normalized = yapyon.emit(tree)
        assert ":=" in normalized
        _assert_value(yapyon.loads_record(normalized), restored.resolve())
    else:
        with pytest.raises(AkanError):
            yapyon.loads_record(text)
        with pytest.raises(AkanError):
            yapyon.emit(tree)


def test_literal_api_record_emission_does_not_confuse_structural_merging_with_authored_pipes():
    tree = merge(parse("data: {a: 1}\nitems: [1, 1]"),
                 parse("data: {b: 2}\nitems: [1, 2]"))
    _assert_value(yapyon.loads_record(yapyon.emit(tree)),
                  {"data": {"a": 1, "b": 2}, "items": [1, 1, 2]})
    authored = parse("{data: {a: 1}} | {data: {b: 2}}")
    with pytest.raises(AkanError, match="record"):
        yapyon.emit(authored)
    assert "|" in authored.to_source()


def test_adding_a_key_to_an_explicit_pipe_edits_the_stored_program():
    tree = parse('{a: 1} | {a: 2}')
    tree.merge(parse('3'), at=('new',))
    _assert_saved_value(tree, {'a': 2, 'new': 3})


def test_editing_a_grouped_literal_collection_materializes_the_edited_location():
    tree = parse('([1] | [2])')
    tree[0].replace(parse('9'))
    _assert_saved_value(tree, [9, 2])


@pytest.mark.parametrize('text', [
    '({x<base>: {}} | {}).x',
    '[{x<base>: {}}][0].x',
    '[{x<base>: {}} for item in [1]][0].x',
])
def test_expression_wrappers_do_not_hide_authored_slots(text):
    tree = parse(text)
    for candidate in (tree, _reload(tree)):
        slots = candidate.slots()
        assert len(slots) == 1 and slots[0].label == ('base',)
        slots[0].fill(parse('42'))
        assert candidate.resolve() == 42


def test_record_normalization_keeps_field_operations_but_finished_data_consumes_them():
    text = 'data:= {field:= 0x1}\ncopy: (data)\nencoded: data.__as_yapyon__()'
    result = yapyon.loads(text)
    assert ':=' not in result['encoded']
    assert '0x1' in result['encoded']
    expanded = yapyon.expand_record(text)
    assert ':=' not in expanded
    assert ':=' in yapyon.emit(parse('data:= {field:= 0x1}'))
    copied = parse(expanded)['copy']
    applied = merge(parse('old: 2'), copied)
    assert applied.resolve() == {'old': 2, 'field': 1}


@pytest.mark.parametrize('text', [
    '[' + ', '.join(['""'] * 40) + '] | [' + ', '.join(['""'] * 40) + ']',
    '{+ ' + ', '.join(['a: ""'] * 40) + '} | {+ ' + ', '.join(['a: ""'] * 40) + '}',
])
def test_comparison_work_is_bounded_even_when_rendered_contents_are_empty(text):
    tree = parse(text)
    assert tree.to_source() == _reload(tree).to_source()
    with pytest.raises(AkanError, match='merge comparison.*work ceiling'):
        tree.resolve(max_size=32)
    assert len(tree.resolve(max_size=256)) == 40


def test_dictionary_projection_work_is_charged_before_materialization():
    tree = parse('{a: 1} | {b: 2}', source='work.yap')
    with pytest.raises(AkanError, match='ceiling') as error:
        tree.resolve(max_size=1)
    assert error.value.source == 'work.yap'
    assert tree.resolve(max_size=256) == {'a': 1, 'b': 2}


@pytest.mark.parametrize('loader', [yapyon.loads, lambda text, **options: parse(text).resolve(**options)],
                         ids=['loads', 'tree'])
def test_long_pipe_programs_meet_the_work_ceiling_not_host_recursion(loader):
    text = ' | '.join('{key' + str(index) + ': 0}' for index in range(300))
    with pytest.raises(AkanError, match='work ceiling'):
        loader(text, max_size=1)


def test_merge_dependencies_participate_in_the_existing_depth_ceiling():
    tree = parse('out: (base) | [2]\nbase: [1]', source='depth.yap')
    with pytest.raises(AkanError, match='depth ceiling') as error:
        tree.resolve(max_depth=1)
    assert error.value.source == 'depth.yap'
    assert tree.resolve(max_depth=2) == {'out': [1, 2], 'base': [1]}
