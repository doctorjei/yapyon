"""GRAMMAR §G5 v0.3: calls, arguments, literals, and whitespace in a hole —
what `parse_ref` builds, beyond the yes/no the grammar checker compares.

Also GRAMMAR §G4.7's PEP 701 rule, which lives in the scanner rather than in
`parse_ref`: a literal does not end inside a hole. That is trap 7's
territory (the `\\"` scanning bug), so it is tested here at the token level,
in every y-family prefix and in combination with escapes.
"""

import pytest

from yapyon import AkanError, loads
from yapyon.lexer import Call, Literal, Ref, RefError, parse_ref, tokenize


def akan(ref, needle=""):
    with pytest.raises(RefError) as e:
        parse_ref(ref)
    assert needle in str(e.value), f"wrong message: {e.value}"


def call(ref) -> Call:
    parsed = parse_ref(ref)
    assert parsed.call is not None
    return parsed.call


# --------------------------------------------------------------------------- #
# The shape of a call
# --------------------------------------------------------------------------- #
def test_the_receiver_becomes_the_first_argument():
    c = call("a.b.f(x)")
    assert c.name == "f" and c.receiver
    assert [a.steps for a in c.args] == [[("key", "a"), ("key", "b")],
                                         [("key", "x")]]


def test_a_chain_nests_inside_out():
    # {f(x).g(y)} is g(f(x), y): inside-out, left to right (SPEC §13.1)
    c = call("f(x).g(y)")
    assert c.name == "g"
    inner, y = c.args
    assert inner.call.name == "f" and y.steps == [("key", "y")]


def test_keyword_arguments_keep_their_order_after_positionals():
    c = call("__as_json__(cfg, lexemes=False)")
    assert [a.steps for a in c.args] == [[("key", "cfg")]]
    assert [(k, v.value) for k, v in c.kwargs] == [("lexemes", False)]


def test_a_keyword_takes_anything_an_argument_can():
    c = call("cfg.__as_json__(lexemes=opts.keep)")
    (key, value), = c.kwargs
    assert key == "lexemes" and value.steps == [("key", "opts"), ("key", "keep")]


def test_a_declared_name_takes_keywords_too():
    # §13.1 (v0.4): keyword arguments are no longer built-ins' alone
    c = call("f(x, v=z)")
    assert [a.steps for a in c.args] == [[("key", "x")]]
    assert [(k, v.steps) for k, v in c.kwargs] == [("v", [("key", "z")])]
    assert call("f(ｖ=z)").kwargs[0][0] == "v"


def test_names_are_folded_like_any_name():
    assert call("ｆ(x)").name == "f"


@pytest.mark.parametrize("ref,needle", [
    ("__as_json__(lexemes=False, x)", "positional argument cannot follow"),
    ("f(x,,)", "two commas in a row"),
    ("f(,)", "expected a name"),
    ("f(x", "expected ','"),
    ("f(x).name", "nothing follows a call but another call"),
    ("f(x)[0]", "nothing follows a call but another call"),
    ("True(x)", "cannot be"),
    ("a.__KEY__()", "not a function"),
    ("__ROOT__.f()", "contains this hole"),
    ("__PARENT__.__PARENT__.f()", "contains this hole"),
    ("f(__ROOT__)", "contains this hole"),
    ("f(__PARENT__.__PARENT__)", "contains this hole"),
    ("__as_json__", "reserved name"),
])
def test_malformed_calls_are_akan(ref, needle):
    akan(ref, needle)


@pytest.mark.parametrize("trailing,plain", [
    ("f(x,)", "f(x)"),
    ("f(x, y ,)", "f(x, y)"),
    ("__as_json__(x, lexemes=False,)", "__as_json__(x, lexemes=False)"),
])
def test_a_trailing_comma_is_allowed(trailing, plain):
    # operator, 2026-10-17: as in Python
    assert parse_ref(trailing) == parse_ref(plain)


def test_an_anchor_with_a_step_is_an_argument():
    assert call("f(__PARENT__.blk)").args[0].parents == 1
    assert call("f(__PARENT__.__KEY__)").args[0].key


# --------------------------------------------------------------------------- #
# Literal arguments are Python literals, lexed by the document lexer
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,value,lexeme", [
    ("1", 1, "1"),
    ("-1", -1, "-1"),
    ("- 1", -1, "-1"),           # the sign is its own token, as in Python
    ("+1.5", 1.5, "+1.5"),
    ("0x1F", 31, "0x1F"),
    ("1_000", 1000, "1_000"),
    ("-.5", -0.5, "-.5"),
    ("True", True, "True"),
    ("None", None, "None"),
    ('"s"', "s", '"s"'),
    ("'a\\'b'", "a'b", "'a\\'b'"),
    ('"\\x41"', "A", '"\\x41"'),
    ('r"\\d"', "\\d", 'r"\\d"'),
    ('b"\\x00"', b"\x00", 'b"\\x00"'),
    ('b64"aGk="', b"hi", 'b64"aGk="'),
    ('"#x"', "#x", '"#x"'),
])
def test_literal_arguments(text, value, lexeme):
    (arg,) = call(f"f({text})").args
    assert isinstance(arg, Literal)
    assert arg.value == value and type(arg.value) is type(value)
    assert arg.lexeme == lexeme


@pytest.mark.parametrize("text,needle", [
    ("--1", "a sign applies only to a number"),
    ("-True", "a sign applies only to a number"),
    ("-x", "a sign applies only to a number"),
    ('y"s"', "not a literal"),
    ('f"s"', "no f-strings"),
    ('"""s"""', "single-line"),
    ('b64"aGl="', "non-canonical base64"),
    ('"\\q"', "unknown escape"),
])
def test_literal_arguments_that_are_akan(text, needle):
    akan(f"f({text})", needle)


def test_a_literal_is_never_the_whole_hole_or_a_receiver():
    akan("8080")
    akan('"x".f()')
    akan("1.f()")


# --------------------------------------------------------------------------- #
# Whitespace and comments
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spaced,plain", [
    (" a . b ", "a.b"),
    ("f( a , b )", "f(a,b)"),
    ("f (a)", "f(a)"),
    ("xs[ - 1 ]", "xs[-1]"),
    ("a .f( )", "a.f()"),
    ("a\n.b", "a.b"),
    ("a\t[ 'b' ]", "a['b']"),
    ("__as_json__(x , lexemes = False)", "__as_json__(x,lexemes=False)"),
])
def test_whitespace_between_tokens_means_nothing(spaced, plain):
    assert parse_ref(spaced) == parse_ref(plain)


def test_a_hole_has_no_comments():
    akan("a #c", "no comments")
    assert call('f("#x")').args[0].value == "#x"


def test_whitespace_inside_a_token_is_not_whitespace_between_them():
    akan("a b", "joined by '.'")
    akan("__PAR ENT__")


# --------------------------------------------------------------------------- #
# Shirans survive into calls
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ref", ['__str__(a["b"])', 'a["b"].__str__()',
                                 '__get__(xs, __int__(a["b"]))'])
def test_the_bracket_shiran_reaches_through_a_call(ref):
    # Key kind is known at resolution, not while parsing the call.
    assert parse_ref(ref).shirans == []
    warnings = []
    loads(f'a: {{b: 0}}\nxs: [1]\nu: y"{{{ref}}}"', warn=warnings.append)
    assert len(warnings) == 1


# --------------------------------------------------------------------------- #
# GRAMMAR §G4.7 / PEP 701: a literal does not end inside a hole
# --------------------------------------------------------------------------- #
def holes(doc):
    return [p for t in tokenize(doc) for k, p in t.parts if k == "hole"]


@pytest.mark.parametrize("doc,expected", [
    ('u: y"{f("x")}"\n', ['f("x")']),
    ('u: y"{f("x\\"y")}"\n', ['f("x\\"y")']),         # an escaped quote in it
    ("u: y'{f('x')}'\n", ["f('x')"]),
    ('u: yb"{f("x")}"\n', ['f("x")']),
    ('u: yt"{f("x")}"\n', ['f("x")']),
    ('u: ry"{f(r"\\d")}\\d"\n', ['f(r"\\d")']),
    ('u: y"{f("}")}{g(")")}"\n', ['f("}")', 'g(")")']),
    ('u: y"{f("{")}"\n', ['f("{")']),
    ('u: y"{f(")")}"\nv: "x"\n', ['f(")")']),
    ('u: y"""\n  {f(\n    "x")}\n  """\n', ['f(\n  "x")']),
])
def test_a_quote_inside_a_hole_does_not_end_the_literal(doc, expected):
    assert holes(doc) == expected


@pytest.mark.parametrize("doc,needle", [
    ('u: y"{f("x)}"\n', "unclosed hole"),
    ('u: y"{f("x")"\nv: "}"\n', "unclosed hole"),
    ('u: y"{f(\nx)}"\n', ""),
])
def test_an_unclosed_hole_does_not_swallow_the_document(doc, needle):
    with pytest.raises(AkanError) as e:
        tokenize(doc)
    assert needle in str(e.value)


def test_the_receiver_form_and_the_call_form_resolve_alike():
    assert loads('a:\n  x: 1\nu: y"{__as_json__(a)}"\n')["u"] == \
        loads('a:\n  x: 1\nu: y"{a.__as_json__()}"\n')["u"]


def test_a_hole_string_in_a_raw_literal_is_not_raw():
    # rawness belongs to each literal: in `ry"..."` the text is raw, while a
    # string inside a hole is its own token and raw only if it says so --
    # Python's rule for rf-strings since PEP 701
    with pytest.raises(AkanError) as e:
        tokenize('u: ry"{f("\\d")}"\n')
    assert "unknown escape" in str(e.value)
