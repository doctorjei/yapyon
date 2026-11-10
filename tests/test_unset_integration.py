"""Cancellation through deferred construction, public APIs, and source programs."""

import itertools

import pytest

import yapyon
from yapyon import AkanError, loads, parse


@pytest.mark.parametrize("expression,wanted", [
    ("[row.v! for row in rows]", [1, 3]),
    ("[{value: (row.v!)} for row in rows]", [{"value": 1}, {}, {"value": 3}]),
    ("[row for row in rows if row.ok!]", [{"v": 1, "key": "one", "ok": True}]),
    ('{row.key!: row.v for row in rows}', {"one": 1, "three": 3}),
])
def test_comprehension_item_cancellation(expression, wanted):
    text = 'rows: [{v: 1, key: "one", ok: True}, {}, {v: 3, key: "three", ok: False}]\n'
    tree = parse(text + "out: " + expression)
    assert tree.resolve()["out"] == wanted
    assert loads(tree.to_source())["out"] == wanted


def test_comprehension_iterable_cancels_receiving_field():
    assert loads('foo: {}\nout: [x for x in foo.missing!]') == {"foo": {}}


@pytest.mark.parametrize("expression", [
    '{k: v for k, v in foo.missing!} | {a: 1}',
    '{a: 1} | {k: v for k, v in foo.missing!}',
])
def test_comprehension_operand_cancellation_reaches_its_receiving_field(expression):
    text = 'foo: {}\nout: ' + expression + '\nkeep: 1'
    assert loads(text) == {"foo": {}, "keep": 1}
    assert loads(parse(text).to_source()) == {"foo": {}, "keep": 1}


def test_comprehension_key_cancels_only_generated_pair():
    text = 'rows: [{k: "a", v: 1}, {v: 2}]\nout: {row.k!: row.v for row in rows}'
    assert loads(text)["out"] == {"a": 1}


def test_comprehension_body_cancellation_preserves_lower_contribution():
    text = 'rows: [{k: "a"}]\nout: {"a": 7}\n|\nout: {row.k: row.v! for row in rows}'
    assert loads(text)["out"] == {"a": 7}
    assert loads(parse(text).to_source())["out"] == {"a": 7}


@pytest.mark.parametrize("separator", [":", ":="])
@pytest.mark.parametrize("higher", ["(foo.x!)", 'y"{foo.x!}"', "7 if foo.x! else 8"])
def test_multiple_fallback_layers(separator, higher):
    text = f'foo: {{}}\nx: 1\n|\nx{separator} {higher}\n|\nx{separator} (foo.y!)'
    assert loads(text)["x"] == 1
    assert loads(parse(text).to_source())["x"] == 1


@pytest.mark.parametrize("fields", list(itertools.permutations([
    'foo: {}', 'out: (mm.k[0])', 'mm:\n  + k: (foo.x!)\n  + k: 2',
])))
def test_multimap_view_waits_for_entry_cancellation(fields):
    result = loads("\n".join(fields))
    assert result["out"] == 2
    assert [(entry._key, entry.value) for entry in result["mm"]] == [("k", 2)]


@pytest.mark.parametrize("fields", list(itertools.permutations([
    'foo: {}', 'out: (box["gone"]!)', 'box: {y"{foo.x!}": 1}',
])))
def test_computed_key_cancels_whole_pair(fields):
    assert loads("\n".join(fields)) == {"foo": {}, "box": {}}


def test_computed_key_cancellation_does_not_evaluate_value():
    assert loads('foo: {}\nbox: {y"{foo.x!}": (missing)}') == {"foo": {}, "box": {}}


@pytest.mark.parametrize("separator", [":", ":="])
def test_discarded_lower_body_keeps_ordinary_key_identity(separator):
    text = f'foo: {{}}\nx: (foo.missing!)\nz: 0\n|\n"x"{separator} 2'
    result = loads(text)
    assert list(result) == ["foo", "x", "z"]
    assert yapyon.lookup(result, result, "x") == 2


def test_evaluated_canceled_lower_key_has_no_provenance_or_position():
    text = 'foo: {}\nx: (foo.missing!)\nz: 0\n|\n"x": {}'
    result = loads(text)
    assert list(result) == ["foo", "z", "x"]
    assert yapyon.lookup(result, result, '__ROOT__["x"]') == {}
    with pytest.raises(AkanError):
        yapyon.lookup(result, result, "x")


def test_field_cancellation_rechecks_names_after_shadow_removal():
    lines = ['foo: {}', 'x: 7', 'nested: {x: (foo.x!), out: (x)}']
    for fields in itertools.permutations(lines):
        assert loads("\n".join(fields))["nested"] == {"out": 7}


def test_public_lookup_never_exposes_control_exception():
    root = loads('foo: {}')
    with pytest.raises(AkanError, match="no lookup value"):
        yapyon.lookup(root, root, "foo.missing!")
    assert yapyon.lookup(root, root, "foo!") == {}


def test_environment_access_off_is_not_absence():
    with pytest.raises(AkanError):
        loads('out: ($HOME!)', env=None)


def test_callbacks_are_not_called_with_canceled_arguments():
    contract = yapyon.loads_contract('F:\n  params: {x: "int"}\n  returns: "int"\n'
                                    '  impl: {python: {symbol: "F"}}\n')
    calls = []

    def function(x):
        calls.append(x)
        return x

    text = 'foo: {}\nout: F(F(foo.x!))\nkeep: F(3)'
    assert loads(text, contract=contract, provide={"F": function}) == {"foo": {}, "keep": 3}
    assert calls == [3]


@pytest.mark.parametrize("route", ["expand", "tree", "yamlplus", "serializer"])
def test_expansion_and_serialization_have_no_unset_value(route):
    text = 'foo: {}\ncfg: {gone: (foo.x!), keep: None, items: [1, (foo.y!), 2]}'
    if route == "expand":
        result = yapyon.loads_record(yapyon.expand_record(text))
    elif route == "tree":
        result = parse(text).resolve()
    elif route == "yamlplus":
        result = yapyon.loads_record(yapyon.expand_yamlplus(text))
    else:
        result = yapyon.loads_record(loads(text + '\nout: y"{cfg.__as_yapyon__()}"')["out"])
        result = {"cfg": result}
    assert result["cfg"] == {"keep": None, "items": [1, 2]}


def test_filled_slot_preserves_fallback_and_unresolved_source():
    tree = parse('foo: {}\ncfg<base>: {x: (foo.missing!)}')
    tree["cfg"].fill(parse('x: 1'))
    saved = tree.to_source()
    assert tree.resolve() == loads(saved) == {"foo": {}, "cfg": {"x": 1}}
    assert tree.to_source() == saved


@pytest.mark.parametrize("whitespace", ["", " ", "\t", "\n"])
def test_whitespace_between_guard_tokens(whitespace):
    text = f'foo: {{}}\nout: (foo{whitespace}.{whitespace}x{whitespace}!{whitespace})'
    assert loads(text) == {"foo": {}}


@pytest.mark.parametrize("expression", ["(foo.present!)", 'y"{foo.present!}"'])
def test_present_higher_guard_can_discard_unfilled_lower_slot(expression):
    text = 'foo: {present: 7}\nx<base>: {}\n|\nx: ' + expression
    result = loads(text)
    assert result["x"] in (7, "7")
    assert loads(parse(text).to_source()) == result


def test_missing_higher_guard_leaves_unfilled_lower_slot():
    with pytest.raises(AkanError, match="unfilled"):
        loads('foo: {}\nx<base>: {}\n|\nx: (foo.missing!)')


def test_nested_guard_hash_matches_reference_identity():
    from yapyon.lexer import parse_ref

    a, b = parse_ref("foo[selector!]!"), parse_ref(" foo [ selector ! ] ! ")
    assert a == b
    assert hash(a) == hash(b)
    assert a != parse_ref("foo[selector]!")


@pytest.mark.parametrize("lower", ["7", "None", "{}", "{a: 1}", "[]", "[1]", "{+}", "{+ a: 1}"])
@pytest.mark.parametrize("higher", ["None", "False", "0", '""', "{}", "{b: 2}", "[]", "[2]", "{+ b: 2}"])
@pytest.mark.parametrize("separator", [":", ":="])
def test_present_guard_uses_unchanged_merge_matrix(lower, higher, separator):
    prefix = f"foo: {{v: {higher}}}\nx: {lower}\n|\nx{separator} "
    guarded = prefix + "(foo.v!)"
    expected = loads(prefix + "(foo.v)")
    assert loads(guarded) == expected
    assert loads(parse(guarded).to_source()) == expected


def test_inert_exclamation_and_comparison():
    assert loads('foo: 1\ntext: "!" # foo!\nout: foo != 2') == {"foo": 1, "text": "!", "out": True}
