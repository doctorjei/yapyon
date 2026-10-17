"""SPEC §13.1 and §5.1.2: calls, and the built-ins they reach.

One call path, so these are about the *path*: shape before arguments,
arguments inside-out, borrows that wait for their whole subtree, the
containment rule, and deferral at every level — which is trap 9's lesson,
that a new route into the fixpoint must be able to reach every outcome it
defines and not only success.
"""

import json

import pytest

from yapyon import AkanError, loads
from yapyon.typespec import TypeSpecError, check, parse_type, show


def akan(doc, needle=""):
    with pytest.raises(AkanError) as e:
        loads(doc)
    assert needle in str(e.value), f"wrong message: {e.value}"
    return e.value


CFG = 'cfg:\n  name: "gw"\n  port: 8080\n'


# --------------------------------------------------------------------------- #
# Shape: name, arity, keywords
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("hole,needle", [
    ("__AS_JSON__()", "takes one argument (Any), not 0"),
    ("__AS_JSON__(cfg, cfg)", "takes one argument (Any), not 2"),
    ("cfg.__AS_YAML__(lexemes=False)", "has no keyword argument lexemes; it "
                                       "takes none"),
    ("cfg.__AS_JSON__(indent=2)", "no keyword argument indent; it takes "
                                  "lexemes"),
    ("cfg.__AS_JSON__(lexemes=True, lexemes=False)", "lexemes is repeated"),
    ("cfg.__AS_XML__()", "there is no built-in named __AS_XML__()"),
    ("f(cfg)", "f() is not a built-in, and no contract was given"),
])
def test_a_call_s_shape_is_checked(hole, needle):
    akan(CFG + f'u: y"{{{hole}}}"\n', needle)


def test_the_shape_is_checked_before_the_arguments():
    # the unknown name is the mistake, even though `nope` is unbound too
    akan('u: y"{__AS_XML__(nope)}"\n', "no built-in named __AS_XML__()")


# --------------------------------------------------------------------------- #
# Keyword arguments take anything an argument can
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", ["True", "False", "opts.keep"])
def test_lexemes_takes_a_bool_from_a_literal_or_a_reference(value):
    doc = CFG + f'opts:\n  keep: False\nu: y"{{cfg.__AS_JSON__(lexemes={value})}}"\n'
    assert json.loads(loads(doc)["u"]) == {"name": "gw", "port": 8080}


@pytest.mark.parametrize("value,found", [("1", "int"), ('"no"', "str"),
                                         ("cfg", "dict")])
def test_lexemes_must_be_a_bool(value, found):
    akan(CFG + f'u: y"{{cfg.__AS_JSON__(lexemes={value})}}"\n',
         f"__AS_JSON__()'s lexemes takes bool, not {found}")


# --------------------------------------------------------------------------- #
# Arguments: literals, keys, nested calls, chains
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("arg,expected", [
    ('"x"', '"x"'), ("5", "5"), ("-1.5", "-1.5"), ("True", "true"),
    ("None", "null"), ("0xff", "255"),
])
def test_a_literal_argument_is_a_value(arg, expected):
    assert loads(f'u: y"{{__AS_JSON__({arg})}}"\n')["u"] == expected


def test_a_key_is_an_argument():
    assert loads('me: y"{__AS_JSON__(__KEY__)}"\n')["me"] == '"me"'


def test_calls_nest_inside_out():
    d = loads(CFG + 'u: y"{__AS_JSON__(__AS_JSON__(cfg))}"\n')
    assert json.loads(json.loads(d["u"])) == {"name": "gw", "port": 8080}


def test_a_chain_applies_its_links_in_order():
    import yaml
    d = loads(CFG + 'u: y"{cfg.__AS_JSON__().__AS_YAML__()}"\n')
    text = yaml.safe_load(d["u"])               # the JSON text, as a YAML string
    assert json.loads(text) == {"name": "gw", "port": 8080}


def test_a_chain_into_toml_is_a_type_error_at_the_second_link():
    akan(CFG + 'u: y"{cfg.__AS_JSON__().__AS_TOML__()}"\n',
         "__AS_TOML__() takes dict[str, Any] | multimap[str, Any], not str")


def test_a_call_result_splices_by_the_matrix():
    akan(CFG + 'u: yb"{cfg.__AS_JSON__()}"\n', "no implicit encode")
    t = loads(CFG + 'u: yt"<{cfg.__AS_JSON__()}>"\n')["u"]
    assert json.loads(t.values[0]) == {"name": "gw", "port": 8080}


# --------------------------------------------------------------------------- #
# Borrows wait for their whole subtree, at every level (trap 9)
# --------------------------------------------------------------------------- #
def test_a_borrow_waits_for_a_pending_hole_inside_it():
    d = loads('cfg:\n  url: y"https://{host}/"\nhost: "h"\n'
              'u: y"{cfg.__AS_JSON__()}"\n')
    assert json.loads(d["u"]) == {"url": "https://h/"}


def test_a_nested_call_waits_too():
    d = loads('cfg:\n  url: y"{host}"\nhost: "h"\n'
              'u: y"{__AS_JSON__(__AS_JSON__(cfg))}"\n')
    assert json.loads(json.loads(d["u"])) == {"url": "h"}


def test_a_keyword_argument_waits_too():
    # `keep` is still a y-string on the first pass; the call waits for it,
    # and then judges what it became -- the *string* "False", not a bool
    akan(CFG + 'keep: y"{flag}"\nflag: False\n'
         'u: y"{cfg.__AS_JSON__(lexemes=keep)}"\n',
         "lexemes takes bool, not str")


def test_two_calls_waiting_on_each_other_are_a_cycle():
    akan('a:\n  x: y"{b.__AS_JSON__()}"\nb:\n  y: y"{a.__AS_JSON__()}"\n',
         "references never resolve (they form a cycle)")


def test_a_cycle_through_a_nested_call_is_still_a_cycle():
    akan('a:\n  x: y"{__AS_JSON__(__AS_JSON__(b))}"\n'
         'b:\n  y: y"{__AS_JSON__(a)}"\n', "form a cycle")


# --------------------------------------------------------------------------- #
# No argument may contain the call site (§13.1)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("doc", [
    'blk:\n  a: 1\n  me: y"{blk.__AS_JSON__()}"\n',
    'blk:\n  a: 1\n  me: y"{__AS_JSON__(blk)}"\n',
    'top:\n  blk:\n    me: y"{top.__AS_YAML__()}"\n',
    'xs:\n  - y"{__ROOT__.xs.__AS_JSON__()}"\n',
    'blk:\n  me: y"{__AS_JSON__(__AS_JSON__(blk))}"\n',
])
def test_an_argument_containing_the_call_site_is_akan(doc):
    akan(doc, "contains this hole")


def test_a_sibling_block_is_not_the_call_site():
    d = loads('blk:\n  a: 1\nother:\n  me: y"{blk.__AS_JSON__()}"\n')
    assert json.loads(d["other"]["me"]) == {"a": 1}


# --------------------------------------------------------------------------- #
# Single values, and TOML's signature
# --------------------------------------------------------------------------- #
def test_a_single_value_is_written_plain_never_wrapped():
    assert loads('n: 5\nu: y"{n.__AS_JSON__()}"\n')["u"] == "5"
    assert loads('xs: [1, 2]\nu: y"{xs.__AS_JSON__()}"\n')["u"] == \
        json.dumps([1, 2], indent=2)


@pytest.mark.parametrize("target,found", [("n: 5", "int"), ("xs: [1]", "list"),
                                          ('n: "s"', "str")])
def test_toml_refuses_what_is_not_a_table_by_its_signature(target, found):
    akan(f'{target}\nu: y"{{{target.split(":")[0]}.__AS_TOML__()}}"\n',
         f"not {found} -- a TOML document is a table")


# --------------------------------------------------------------------------- #
# A yt anywhere in a serializer's argument: §5.1.2's one message
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", ["__AS_JSON__", "__AS_TOML__", "__AS_YAML__",
                                  "__AS_YAPYON__"])
def test_a_template_in_the_argument_is_yeeted(name):
    e = akan(f'w: "x"\ncfg:\n  deep:\n    t: yt"hi {{w}}"\nu: y"{{cfg.{name}()}}"\n',
             "yeeted yt; a record cannot hold a template's unjoined parts. "
             "Use a y-string to join them.")
    assert (e.line, e.col) == (4, 7)            # at the template itself


# --------------------------------------------------------------------------- #
# typespec: the §13.3 reader the built-ins and contracts share
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,canonical", [
    ("str", "str"), ("Any", "Any"), ("int|None", "int | None"),
    ("list[ str ]", "list[str]"), ("dict[str,int]", "dict[str, int]"),
    ("dict[str, Any] | multimap[str, Any]", "dict[str, Any] | multimap[str, Any]"),
    ("list[dict[str, list[int | float]]]", "list[dict[str, list[int | float]]]"),
    ("\tbool\t", "bool"),
])
def test_type_strings_read_as_python_annotations(text, canonical):
    assert show(parse_type(text)) == canonical


@pytest.mark.parametrize("text,needle", [
    ("list", "a bare list is akan"), ("dict", "a bare dict is akan"),
    ("dict[int, str]", "key type must be str"), ("set[int]", "not a type"),
    ("Str", "not a type"), ("int |", "ends where a type was expected"),
    ("list[int", "expected ']'"), ("int int", "unexpected"),
    ("template", "not a type"),
])
def test_malformed_type_strings(text, needle):
    with pytest.raises(TypeSpecError) as e:
        parse_type(text)
    assert needle in str(e.value)


def node_of(literal):
    from yapyon import parse
    return parse(f"a: {literal}\n").by_key["a"]


@pytest.mark.parametrize("literal,type_,ok", [
    ("1", "int", True), ("True", "int", False),        # bool is not int
    ("1", "float", True),                               # int widens to float
    ("1.5", "int", False), ("None", "int | None", True),
    ("[1, 2]", "list[int]", True), ('[1, "x"]', "list[int]", False),
    ('{a: [1, "x"]}', "dict[str, Any]", True),          # Any stops the check
    ('{a: [1, "x"]}', "dict[str, list[int]]", False),
    ("[]", "list[str] | list[int]", True),
])
def test_the_check_is_deep(literal, type_, ok):
    assert (check(node_of(literal), parse_type(type_)) is None) is ok


def test_a_mismatch_names_the_offending_node():
    node = node_of('{a: [1, "x"]}')
    miss = check(node, parse_type("dict[str, list[int]]"))
    assert miss.found == "str" and miss.node is node.by_key["a"].items[1]
