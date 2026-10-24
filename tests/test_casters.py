"""SPEC §5.1.5: the casters `__str__`, `__int__`, `__float__`, `__bool__`,
and the getter `__get__`.

Rulings (operator, 2026-10-24; `workbook/designs/casters.md`): Python's
names, yapyon's own parsing; a value a cast cannot take is akan, `None`
included unless `?.` skips the call; text must be the whole number — C's
habit of dropping what follows is refused; leading zeros in text are
fine; a float truncates to an int; bools are 1 and 0 both ways.
"""

import pytest

from yapyon import AkanError, loads


def cast(expr, **values):
    """The value of `out: (expr)` beside the given keys."""
    lines = [f"{key}: {value}" for key, value in values.items()]
    return loads("\n".join(lines + [f"out: ({expr})"]) + "\n")["out"]


# --------------------------------------------------------------------------- #
# __int__
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,value", [
    ('"42"', 42), ('"-7"', -7), ('"+3"', 3), ('"03"', 3), ('"007"', 7),
    ('"0"', 0), ('"-0"', 0),
])
def test_int_reads_whole_decimal_text(text, value):
    assert cast("x.__int__()", x=text) == value


@pytest.mark.parametrize("text", [
    '"3.0"', '"3.0asdfasdf"', '"42abc"', '" 42"', '"42 "', '"4_2"',
    '"0x1f"', '""', '"-"', '"٤٢"', '"1e3"',
])
def test_int_refuses_anything_else_in_text(text):
    with pytest.raises(AkanError, match="cannot read"):
        cast("x.__int__()", x=text)


@pytest.mark.parametrize("value,result", [
    ("3.7", 3), ("-3.7", -3), ("3.0", 3), ("True", 1), ("False", 0),
    ("0xff", 255),
])
def test_int_converts_values(value, result):
    assert cast("x.__int__()", x=value) == result


def test_int_reads_long_text_exactly():
    digits = "9" * 5000                  # past CPython's own 4,300-digit limit
    assert cast("x.__int__()", x=f'"{digits}"') == 10 ** 5000 - 1


# --------------------------------------------------------------------------- #
# __float__
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,value", [
    ('"2.5"', 2.5), ('"-2.5"', -2.5), ('"3"', 3.0), ('".5"', 0.5),
    ('"3."', 3.0), ('"2.5e+3"', 2500.0), ('"1E-2"', 0.01), ('"03.5"', 3.5),
])
def test_float_reads_decimal_text(text, value):
    assert cast("x.__float__()", x=text) == value


@pytest.mark.parametrize("text", [
    '"inf"', '"nan"', '"2.5f"', '" 2.5"', '"2_5.0"', '"0x1p3"', '"1e999"',
    '"2,5"', '""',
])
def test_float_refuses_anything_else_in_text(text):
    with pytest.raises(AkanError, match="cannot read"):
        cast("x.__float__()", x=text)


@pytest.mark.parametrize("value,result", [
    ("3", 3.0), ("True", 1.0), ("2.25", 2.25),
])
def test_float_converts_values(value, result):
    out = cast("x.__float__()", x=value)
    assert out == result and isinstance(out, float)


def test_an_int_too_large_for_a_float_is_akan():
    with pytest.raises(AkanError, match="outside the float range"):
        cast("x.__float__()", x="1" + "0" * 400)


# --------------------------------------------------------------------------- #
# __bool__
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,value", [
    ('"true"', True), ('"TRUE"', True), ('"Yes"', True), ('"on"', True),
    ('"1"', True), ('"false"', False), ('"NO"', False), ('"Off"', False),
    ('"0"', False),
])
def test_bool_reads_its_words(text, value):
    assert cast("x.__bool__()", x=text) is value


@pytest.mark.parametrize("text", ['"y"', '"n"', '"maybe"', '""', '"2"',
                                  '" yes"', '"ｙｅｓ"'])
def test_bool_refuses_other_text(text):
    with pytest.raises(AkanError, match="cannot read"):
        cast("x.__bool__()", x=text)


@pytest.mark.parametrize("value,result", [
    ("1", True), ("0", False), ("1.0", True), ("0.0", False),
    ("True", True),
])
def test_bool_takes_one_and_zero(value, result):
    assert cast("x.__bool__()", x=value) is result


@pytest.mark.parametrize("value", ["2", "-1", "0.5"])
def test_bool_refuses_other_numbers(value):
    with pytest.raises(AkanError, match="takes 0 or 1"):
        cast("x.__bool__()", x=value)


# --------------------------------------------------------------------------- #
# __str__
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value,result", [
    ("42", "42"), ("0xff", "255"), ("3.10", "3.1"), ("True", "True"),
    ('"s"', "s"),
])
def test_str_writes_values_as_splicing_does(value, result):
    assert cast("x.__str__()", x=value) == result


def test_str_refuses_bytes():
    with pytest.raises(AkanError, match="named encoding"):
        cast("x.__str__()", x="b'hi'")


# --------------------------------------------------------------------------- #
# Every cast
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["__str__", "__int__", "__float__",
                                  "__bool__"])
def test_none_is_akan_without_a_safe_call(name):
    with pytest.raises(AkanError, match=r"cannot take None.*\?\."):
        cast(f"x.{name}()", x="None")


@pytest.mark.parametrize("name", ["__str__", "__int__", "__float__",
                                  "__bool__"])
def test_containers_are_akan(name):
    with pytest.raises(AkanError, match="single value"):
        cast(f"x.{name}()", x="[1]")


def test_a_cast_takes_one_argument_and_no_keywords():
    with pytest.raises(AkanError, match="takes one value"):
        cast('__int__("1", "2")')
    with pytest.raises(AkanError, match="takes one value"):
        cast('__int__("1", base=2)')


def test_the_call_form_and_a_literal_argument():
    assert cast('__int__("12")') == 12 and cast("__str__(3.5)") == "3.5"


def test_casts_splice_like_any_value():
    assert loads('n: "8080"\nu: y"port {n.__int__()}"\n')["u"] == "port 8080"


# --------------------------------------------------------------------------- #
# __get__
# --------------------------------------------------------------------------- #
def test_get_on_a_list_or_its_default():
    xs = '["a", "b"]'
    assert cast("xs.__get__(0)", xs=xs) == "a"
    assert cast("xs.__get__(-1)", xs=xs) == "b"
    assert cast("xs.__get__(2)", xs=xs) is None
    assert cast('xs.__get__(2, "none-yet")', xs=xs) == "none-yet"
    assert cast('xs.__get__(2, default="d")', xs=xs) == "d"


def test_get_on_a_mapping_like_dict_get():
    m = '{model: "m", ctx: 8}'
    assert cast('m.__get__("model")', m=m) == "m"
    assert cast('m.__get__("missing", 8192)', m=m) == 8192
    assert cast('m.__get__("ｍｏｄｅｌ")', m=m) == "m"


def test_get_on_a_multimap_is_the_list_view():
    text = ('mm:\n  + k: 1\n  + j: 2\n  + k: 3\n'
            'a: (mm.__get__("k"))\nb: (mm.__get__("z", "d"))\n')
    out = loads(text)
    assert out["a"] == [1, 3] and out["b"] == []


def test_get_returns_a_separate_value():
    out = loads('xs: [[1]]\nfirst: (xs.__get__(0))\n')
    assert out["first"] == [1] and out["first"] is not out["xs"][0]


def test_get_index_and_key_types():
    with pytest.raises(AkanError, match="takes an int index"):
        cast('xs.__get__("0")', xs="[1]")
    with pytest.raises(AkanError, match="takes a str key"):
        cast("m.__get__(0)", m="{a: 1}")
    with pytest.raises(AkanError, match="mapping, list, or multimap"):
        cast("s.__get__(0)", s='"text"')


def test_get_arity():
    with pytest.raises(AkanError, match="takes a container"):
        cast("xs.__get__()", xs="[1]")
    with pytest.raises(AkanError, match="given by position and again"):
        cast("xs.__get__(0, 1, default=2)", xs="[1]")
    with pytest.raises(AkanError, match="no keyword argument"):
        cast("xs.__get__(0, fallback=2)", xs="[1]")


def test_get_on_none_is_akan_without_a_safe_call():
    with pytest.raises(AkanError, match="cannot take None"):
        cast("x.__get__(0)", x="None")


def test_the_motivating_case():
    text = ('persona:\n  mind:\n    model_list: ["kimi-k3.1-pro"]\n'
            'fable: (persona.mind.model_list.__get__(0).__str__())\n')
    assert loads(text)["fable"] == "kimi-k3.1-pro"
