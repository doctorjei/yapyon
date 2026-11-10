"""Reference-only cancellation, construction locality, and surviving contributions."""

import itertools

import pytest

import yapyon
from yapyon import AkanError, loads, parse
from yapyon.lexer import RefError, parse_ref


EXAMPLE = '''\
foo:
  bar:
    baz: "zot"
fot:
  pik:
    qik: "alpha"
    tok: "beta"
|
fot:
  pik:
    qik: (foo.bar.zot!)
    tok: (foo.bar.baz!)
'''


def test_operator_nested_merge_and_source():
    tree = parse(EXAMPLE)
    before = tree.to_source()
    wanted = {"foo": {"bar": {"baz": "zot"}},
              "fot": {"pik": {"qik": "alpha", "tok": "zot"}}}
    assert tree.resolve() == wanted
    assert loads(before) == wanted
    assert tree.to_source() == before


@pytest.mark.parametrize("value", ["None", "False", "0", '""', "[]", "{}", "{+}"])
def test_present_values_do_not_cancel(value):
    result = loads(f"foo: {{x: {value}}}\nout: (foo.x!)")
    assert "out" in result
    assert result["out"] == result["foo"]["x"]


def test_local_items_fields_and_empty_containers():
    assert loads('''foo: {}
items: [1, (foo.missing!), 3]
rows:
  - {keep: 1, drop: (foo.missing!)}
  - {}
  - {drop: (foo.missing!)}
''') == {"foo": {}, "items": [1, 3], "rows": [{"keep": 1}, {}, {}]}


@pytest.mark.parametrize("expression", [
    "__str__(foo.missing!)", "__str__(__int__(foo.missing!))",
    "foo.missing! is None", "not foo.missing!", "True and foo.missing!",
    "foo.missing! or True", "7 if foo.missing! else 8",
    'y"before {foo.missing!} after"', 'yb"{foo.missing!}"',
    'yt"{foo.missing!}"', "(foo.missing!.__str__())",
])
def test_cancel_larger_computation(expression):
    assert loads(f'foo: {{}}\nout: {expression}\nkeep: "yes"') == {"foo": {}, "keep": "yes"}


@pytest.mark.parametrize("expression", [
    "(absent!)", "(foo.absent!)", "(foo.absent.deep!)",
    "(xs[2]!)", "(xs[-2]!)", "($HOME!)",
])
def test_structured_absence(expression):
    assert loads(f"foo: {{}}\nxs: [1]\nout: {expression}", env={}) == {"foo": {}, "xs": [1]}


@pytest.mark.parametrize("expression", [
    "(foo.x!)", "(xs.nope!)", "(foo[0]!)", "(xs[bad]!)",
    '__int__("no")!', "(__int__(foo.absent)!)",
])
def test_guard_does_not_suppress_ordinary_errors(expression):
    with pytest.raises(AkanError):
        loads(f'foo: 7\nxs: []\nbad: True\nout: {expression}')


def test_selector_requires_its_own_guard():
    with pytest.raises(AkanError, match="selector"):
        loads('foo: {}\nout: (foo[selector]!)')
    assert loads('foo: {}\nout: (foo[selector!]!)') == {"foo": {}}


def test_guarded_function_none_and_multimap_view_are_present():
    result = loads('mm: {+}\na: (__env__("HOME")!)\nb: (mm.x!)', env={})
    assert result["a"] is None
    assert result["b"] == []


def test_root_cancellation_has_no_document_value():
    with pytest.raises(AkanError, match="no document value") as exc:
        loads('($HOME!)', env={}, source="root.yp")
    assert exc.value.source == "root.yp"
    assert (exc.value.line, exc.value.col) == (1, 0)


@pytest.mark.parametrize("separator", [":", ":="])
@pytest.mark.parametrize("lower", ['"alpha"', "None", "{}", "[]", "{+}"])
def test_missing_higher_preserves_lower(separator, lower):
    text = f'foo: {{}}\nx: {lower}\n|\nx{separator} (foo.missing!)'
    wanted = loads(f'foo: {{}}\nx: {lower}')
    assert loads(text) == wanted
    assert loads(parse(text).to_source()) == wanted


@pytest.mark.parametrize("order", list(itertools.permutations([
    "foo: (later)", 'later: {present: "yes"}', "out: (foo.absent!)",
])))
def test_forward_reference_order(order):
    assert loads("\n".join(order)) == {"foo": {"present": "yes"}, "later": {"present": "yes"}}


def test_list_index_waits_for_cancellation():
    for lines in itertools.permutations(["foo: {}", "xs: [(foo.x!), 2]", "out: (xs[0])"]):
        assert loads("\n".join(lines))["out"] == 2


def test_canceled_shadow_reveals_outer_name():
    text = 'foo: {}\nx: 7\ninner: {x: (foo.absent!), out: (x)}'
    assert loads(text)["inner"] == {"out": 7}


def test_guard_does_not_hide_cycles():
    with pytest.raises(AkanError, match="cycle"):
        loads("a: (b!)\nb: (a!)")


def test_discarded_lower_does_not_execute():
    assert loads('foo: {}\nx: (missing)\n|\nx: 7') == {"foo": {}, "x": 7}
    assert loads('foo: {}\nx: (missing!)\n|\nx: 7') == {"foo": {}, "x": 7}


def test_source_preserves_conditional_replacement_and_continuation():
    tree = parse('foo: {}\nx: 1')
    tree.merge(parse('x:= (foo.missing!)'))
    saved = tree.to_source()
    assert loads(saved) == tree.resolve() == {"foo": {}, "x": 1}
    tree.merge(parse('foo: {missing: [2]}'))
    restored = parse(saved)
    restored.merge(parse('foo: {missing: [2]}'))
    assert restored.resolve() == tree.resolve() == {"foo": {"missing": [2]}, "x": [2]}


@pytest.mark.parametrize("text", ["(foo)!", "(foo.x)!", "(1)!", '"x"!', "[1]!", "foo!!",
                                 "({x: 1}).x!", "({x: 1}).x!.__str__()",
                                 "([1]).__get__(0)!"])
def test_guard_is_reference_only(text):
    with pytest.raises(AkanError):
        loads("out: " + text)


@pytest.mark.parametrize("reference", ["foo!", "foo.bar!", "foo[selector!]!", "$HOME!", "f(x!)", "x!.__str__()", "f()!"])
def test_guard_reference_grammar(reference):
    assert parse_ref(reference)
    assert parse_ref(reference) == parse_ref(reference)


@pytest.mark.parametrize("reference", ["foo!!", "foo!r", "1!", '"x"!', "(foo)!", "foo!=bar"])
def test_invalid_guard_reference_grammar(reference):
    with pytest.raises(RefError):
        parse_ref(reference)


def test_inequality_is_not_a_guard():
    assert loads("foo: 1\nout: foo!=2") == {"foo": 1, "out": True}


@pytest.mark.parametrize("expression", ["False and foo.x!", "True or foo.x!", "7 if True else foo.x!"])
def test_lazy_unselected_guard_does_not_cancel(expression):
    assert "out" in loads("foo: {}\nout: " + expression)


def test_guarded_syntax_is_not_record_or_yamlplus():
    for text in ["x: (foo!)", 'x: y"{foo!}"']:
        assert not yapyon.is_record(text)
        assert not yapyon.is_yamlplus(text)
        with pytest.raises(AkanError):
            yapyon.loads_record(text)
