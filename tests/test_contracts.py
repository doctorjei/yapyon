"""SPEC §13.2–§13.6: contracts, declared functions, borrows, and results.

The running example is §13.2's own, persona-grata's dialect negotiation:
`match_first(keys, items)` returns the first key that `items` has.
"""

import pytest

from yapyon import (AkanError, Contract, expand_record, loads, loads_contract,
                    lookup, tier_of)

MATCH = '''
match_first:
  params:
    keys: "list[str]"
    items: "dict[str, dict[str, str]]"
  returns: "str"
  impl:
    python:
      symbol: "match_first"
    c:
      from: "persona_grata"
      symbol: "pg_match_first"
'''

DOC = '''
supported: ["responses", "chat"]
mind:
  dialects:
    chat:
      api_uri: "https://x/chat"
    responses:
      api_uri: "https://x/responses"
protocol: y"{match_first(supported, mind.dialects)}"
uri: y"{mind.dialects[protocol].api_uri}"
'''


def match_first(keys, items):
    return next(k for k in keys if k in items)


def load(doc=DOC, contract=MATCH, **provide):
    provide = provide or {"match_first": match_first}
    return loads(doc, contract=loads_contract(contract), provide=provide)


def akan(fn, needle=""):
    with pytest.raises(AkanError) as e:
        fn()
    assert needle in str(e.value), f"wrong message: {e.value}"
    return e.value


# --------------------------------------------------------------------------- #
# The happy path, both call spellings
# --------------------------------------------------------------------------- #
def test_a_declared_function_is_called():
    d = load()
    assert d["protocol"] == "responses"
    assert d["uri"] == "https://x/responses"


def test_the_receiver_form_is_the_same_call():
    doc = DOC.replace("match_first(supported, mind.dialects)",
                      "supported.match_first(mind.dialects)")
    assert load(doc)["protocol"] == "responses"


def test_a_contract_is_given_to_the_loader_and_reads_as_a_record():
    c = loads_contract(MATCH)
    assert isinstance(c, Contract) and "match_first" in c
    assert [name for name, _ in c["match_first"].params] == ["keys", "items"]


def test_other_languages_are_ignored_whatever_their_names():
    c = loads_contract(MATCH.replace("    c:\n", "    zig:\n      anything: 1\n"
                                     "    c:\n"))
    assert c["match_first"].symbol == "match_first"


def test_from_imports_the_code():
    contract = '''
gcd:
  params: {a: "int", b: "int"}
  returns: "int"
  impl:
    python: {from: "math", symbol: "gcd"}
join:
  params: {a: "str", b: "str"}
  returns: "str"
  impl:
    python: {from: "os.path", symbol: "join"}
'''
    d = loads('n: y"{gcd(12, 18)}"\np: y"{join("a", "b")}"\n',
              contract=loads_contract(contract))
    assert d == {"n": "6", "p": "a/b"}


# --------------------------------------------------------------------------- #
# Reading a contract: every key checked, at every level
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,needle", [
    ("f:\n  params: {}\n  returns: \"str\"\n", "impl is required"),
    ("f:\n  returns: \"str\"\n  impl: {python: {symbol: \"f\"}}\n",
     "params is required"),
    ("f:\n  params: {}\n  returns: \"str\"\n  impl: {python: {symbol: \"f\"}}\n"
     "  doc: \"x\"\n", "'doc' is not a contract key"),
    ("f:\n  params: {}\n  returns: \"str\"\n"
     "  impl: {python: {symbol: \"f\", module: \"m\"}}\n",
     "'module' is not an impl key"),
    ("f:\n  params: {}\n  returns: \"str\"\n  impl: {c: {symbol: \"f\"}}\n",
     "no impl.python entry"),
    ("f:\n  params: {}\n  returns: \"str\"\n  impl: {python: {from: \"m\"}}\n",
     "impl.python.symbol is required"),
    ("f:\n  params: {x: \"list\"}\n  returns: \"str\"\n"
     "  impl: {python: {symbol: \"f\"}}\n", "a bare list is akan"),
    ("f:\n  params: {x: 1}\n  returns: \"str\"\n"
     "  impl: {python: {symbol: \"f\"}}\n", "is a string"),
    ("f:\n  params: {}\n  returns: \"dict[int, str]\"\n"
     "  impl: {python: {symbol: \"f\"}}\n", "key type must be str"),
    ("__f__:\n  params: {}\n", "cannot be a key"),
    ('f: y"{x}"\n', "a record's leaves must all be literals"),
])
def test_a_malformed_contract_is_akan_when_loaded(text, needle):
    akan(lambda: loads_contract(text), needle)


def test_a_contract_akan_points_at_the_line():
    e = akan(lambda: loads_contract("f:\n  params: {}\n  returns: \"str\"\n"
                                    "  impl: {python: {symbol: \"f\"}}\n"
                                    "  doc: \"x\"\n"))
    assert e.line == 5


# --------------------------------------------------------------------------- #
# Calls: name, arity, keywords (§13.5)
# --------------------------------------------------------------------------- #
def test_no_contract_given():
    akan(lambda: loads(DOC), "no contract was given to the loader")


def test_a_name_the_contract_does_not_declare():
    akan(lambda: load(DOC.replace("match_first(", "nope(")),
         "the contract does not declare it")


def test_the_wrong_number_of_arguments():
    akan(lambda: load(DOC.replace("match_first(supported, mind.dialects)",
                                  "match_first(supported)")),
         "match_first() takes 2 arguments (keys, items), not 1")


# --------------------------------------------------------------------------- #
# Keyword arguments name parameters (§13.1, v0.4)
# --------------------------------------------------------------------------- #
def with_call(spelling):
    return DOC.replace("match_first(supported, mind.dialects)", spelling)


@pytest.mark.parametrize("spelling", [
    "match_first(supported, items=mind.dialects)",
    "match_first(keys=supported, items=mind.dialects)",
    "match_first(items=mind.dialects, keys=supported)",
    "supported.match_first(items=mind.dialects)",
    "match_first(supported, items=mind.dialects,)",
    "match_first(ｋｅｙｓ=supported, items=mind.dialects)",
])
def test_keywords_fill_parameters_by_name(spelling):
    assert load(with_call(spelling))["protocol"] == "responses"


def test_the_function_receives_declared_order_whatever_the_spelling():
    seen = []

    def spy(keys, items):
        seen.append((list(keys), list(items)))
        return "chat"
    load(with_call("match_first(items=mind.dialects, keys=supported)"),
         match_first=spy)
    assert seen == [(["responses", "chat"], ["chat", "responses"])]


def test_a_binding_s_own_parameter_names_do_not_matter():
    # the contract's names are the keywords; the code receives positions
    d = load(with_call("match_first(items=mind.dialects, keys=supported)"),
             match_first=lambda a, b: match_first(a, b))
    assert d["protocol"] == "responses"


@pytest.mark.parametrize("spelling,needle", [
    ("match_first(supported, bogus=mind.dialects)",
     "match_first() has no parameter bogus; it takes keys, items"),
    ("match_first(supported, keys=supported)",
     "match_first()'s parameter keys is given by position and again by "
     "keyword"),
    ("match_first(supported)",
     "match_first() takes 2 arguments (keys, items), not 1"),
    ("match_first(items=mind.dialects)",
     "match_first() is missing parameter keys (it takes keys, items)"),
    ("match_first(supported, mind.dialects, items=mind.dialects)",
     "match_first()'s parameter items is given by position and again by "
     "keyword"),
    ("match_first(supported, mind.dialects, supported, items=mind.dialects)",
     "match_first() takes 2 arguments (keys, items), not 3 by position"),
    ("match_first(keys=supported, keys=supported)",
     "keyword argument keys is repeated"),
])
def test_a_keyword_that_fills_nothing_or_too_much_is_akan(spelling, needle):
    e = akan(lambda: load(with_call(spelling)), needle)
    assert (e.line, e.col) == (9, 10)


def test_a_keyword_argument_is_type_checked_where_it_is_written():
    doc = with_call("match_first(supported, items=mind.dialects)").replace(
        '      api_uri: "https://x/chat"', "      api_uri: 5")
    e = akan(lambda: load(doc), "match_first()'s parameter items takes")
    assert (e.line, e.col) == (6, 15)


def test_a_keyword_argument_waits_like_any_argument():
    doc = with_call("match_first(supported, items=later)") + \
        'later: {chat: {api_uri: y"{mind.dialects.chat.api_uri}"}}\n'
    assert load(doc)["protocol"] == "chat"


def test_two_calls_waiting_through_keywords_are_a_cycle():
    contract = MATCH + '''
echo:
  params:
    text: "str"
  returns: "str"
  impl:
    python: {symbol: "echo"}
'''
    doc = 'a: y"{echo(text=b)}"\nb: y"{echo(text=a)}"\n'
    akan(lambda: loads(doc, contract=loads_contract(contract),
                       provide={"echo": lambda t: t,
                                "match_first": match_first}),
         "they form a cycle")


def test_provide_without_contract_is_a_mistake():
    with pytest.raises(TypeError):
        loads(DOC, provide={"match_first": match_first})


# --------------------------------------------------------------------------- #
# Arguments: checked deep, at the offending value (§13.3)
# --------------------------------------------------------------------------- #
def test_a_mismatch_inside_a_borrow_is_reported_where_it_is_written():
    doc = DOC.replace('      api_uri: "https://x/chat"', "      api_uri: 5")
    e = akan(lambda: load(doc),
             "match_first()'s parameter items takes dict[str, dict[str, str]]; "
             "here it wants str, not int")
    assert (e.line, e.col) == (6, 15)


def test_bool_is_not_int_and_int_widens_to_float():
    contract = '''
f:
  params: {x: "float", n: "int"}
  returns: "str"
  impl:
    python: {symbol: "f"}
'''
    seen = []

    def f(x, n):
        seen.append((x, n))
        return "ok"
    assert loads('u: y"{f(3, 4)}"\n', contract=loads_contract(contract),
                 provide={"f": f})["u"] == "ok"
    assert seen == [(3.0, 4)] and type(seen[0][0]) is float
    akan(lambda: loads('u: y"{f(3, True)}"\n', contract=loads_contract(contract),
                       provide={"f": f}),
         "parameter n takes int, not bool")


def test_an_exact_match_beats_widening_and_the_first_declared_wins():
    contract = '''
f:
  params: {x: "float | int", xs: "list[float] | list[int]"}
  returns: "str"
  impl:
    python: {symbol: "f"}
'''
    got = []

    def f(x, xs):
        got.append((x, list(xs)))
        return ""
    loads('xs: [1, 2]\nu: y"{f(3, xs)}"\n', contract=loads_contract(contract),
          provide={"f": f})
    assert got == [(3, [1, 2])] and type(got[0][0]) is int
    assert all(type(v) is int for v in got[0][1])


def test_ints_widen_inside_containers_too():
    contract = 'f:\n  params: {xs: "list[float]"}\n  returns: "str"\n' \
               '  impl: {python: {symbol: "f"}}\n'
    got = []
    loads('xs: [1, 2.5]\nu: y"{f(xs)}"\n', contract=loads_contract(contract),
          provide={"f": lambda xs: got.append(list(xs)) or ""})
    assert got == [[1.0, 2.5]] and type(got[0][0]) is float


def test_an_int_outside_the_float_range_is_akan():
    contract = 'f:\n  params: {x: "float"}\n  returns: "str"\n' \
               '  impl: {python: {symbol: "f"}}\n'
    akan(lambda: loads(f'u: y"{{f(0x1{"0" * 300})}}"\n',
                       contract=loads_contract(contract),
                       provide={"f": lambda x: ""}),
         "outside the float range")


# --------------------------------------------------------------------------- #
# Borrows: read-only, downward, identity kept (§13.1)
# --------------------------------------------------------------------------- #
SPY = '''
spy:
  params: {a: "Any", b: "Any"}
  returns: "str"
  impl:
    python: {symbol: "spy"}
'''


def test_a_borrow_is_read_only_ordered_and_keeps_its_identity():
    got = {}

    def spy(a, b):
        got["same"] = a is b
        got["keys"] = list(a)
        got["nested"] = a["inner"]["x"]
        with pytest.raises(TypeError):
            a["new"] = 1
        with pytest.raises(TypeError):
            a.anything = 1
        return "ok"
    loads('blk:\n  z: 1\n  a: 2\n  inner:\n    x: "deep"\n'
          'u: y"{spy(blk, blk)}"\n', contract=loads_contract(SPY),
          provide={"spy": spy})
    assert got == {"same": True, "keys": ["z", "a", "inner"], "nested": "deep"}


def test_a_borrowed_list_and_multimap():
    got = {}

    def spy(a, b):
        got["list"] = list(a)
        got["mm"] = list(b)
        return ""
    loads('xs: [1, [2, 3]]\nmm:\n  + k: 1\n  + k: 2\nu: y"{spy(xs, mm)}"\n',
          contract=loads_contract(SPY), provide={"spy": spy})
    assert got["list"][0] == 1 and list(got["list"][1]) == [2, 3]
    assert got["mm"] == [("k", 1), ("k", 2)]


def test_a_borrow_waits_for_its_subtree():
    got = []
    loads('blk:\n  url: y"{host}"\nhost: "h"\nu: y"{spy(blk, 1)}"\n',
          contract=loads_contract(SPY),
          provide={"spy": lambda a, b: got.append(a["url"]) or ""})
    assert got == ["h"]


def test_an_argument_may_not_contain_the_call_site():
    akan(lambda: loads('blk:\n  u: y"{spy(blk, 1)}"\n',
                       contract=loads_contract(SPY),
                       provide={"spy": lambda a, b: ""}),
         "contains this hole")


def test_a_template_is_never_an_argument():
    akan(lambda: loads('w: "x"\nt: yt"{w}"\nu: y"{spy(t, 1)}"\n',
                       contract=loads_contract(SPY),
                       provide={"spy": lambda a, b: ""}),
         "takes Any, not a template")


# --------------------------------------------------------------------------- #
# Results (§13.4)
# --------------------------------------------------------------------------- #
def make(returns, value):
    contract = f'f:\n  params: {{}}\n  returns: "{returns}"\n' \
               f'  impl: {{python: {{symbol: "f"}}}}\n'
    return lambda doc='u: y"{f()}"\n': loads(doc, contract=loads_contract(contract),
                                             provide={"f": lambda: value})


@pytest.mark.parametrize("returns,value,spliced", [
    ("str", "x", "x"), ("int", 255, "255"), ("float", 1, "1.0"),
    ("bool", True, "True"), ("None", None, "None"), ("bytes", b"hi", "b'hi'"),
    ("int | None", None, "None"),
])
def test_a_result_splices_by_value(returns, value, spliced):
    assert make(returns, value)()["u"] == spliced


def test_a_container_result_reaches_a_serializer():
    import json
    run = make("dict[str, list[int]]", {"ｎａｍｅ": [1, 2]})
    out = run('u: y"{__AS_JSON__(f())}"\n')["u"]
    assert json.loads(out) == {"name": [1, 2]}            # keys folded


@pytest.mark.parametrize("returns,value,needle", [
    ("str", 5, "returned int, but its contract declares str"),
    ("list[int]", [1, "x"], "returned str inside its result"),
    ("int", True, "returned bool"),
    ("dict[str, int]", {"a-b": 1}, "'a-b', which is not a name"),
    ("dict[str, int]", {"__x__": 1}, "'__x__', which is not a name"),
    ("dict[str, int]", {"name": 1, "ｎａｍｅ": 2}, "two keys that fold"),
    ("float", float("inf"), "no infinity or NaN"),
    ("float", float("nan"), "no infinity or NaN"),
    pytest.param("float", 10 ** 400, "outside the float range",
                 id="int-past-float"),
    pytest.param("int", 10 ** 17300, "past this implementation's ceiling",
                 id="int-17300-digits"),     # repr() would hit the host limit
])
def test_a_bad_result_is_akan_naming_the_function(returns, value, needle):
    akan(make(returns, value), needle)


def test_returning_a_borrow_is_akan():
    akan(lambda: loads('blk: {a: 1}\nu: y"{__AS_JSON__(spy(blk, 1))}"\n',
                       contract=loads_contract(SPY.replace('"str"', '"Any"')),
                       provide={"spy": lambda a, b: a}),
         "returned a node of the document")


def test_a_failing_function_is_akan_not_a_traceback():
    def boom():
        raise ValueError("no dialect in common")
    contract = 'f:\n  params: {}\n  returns: "str"\n' \
               '  impl: {python: {symbol: "f"}}\n'
    akan(lambda: loads('u: y"{f()}"\n', contract=loads_contract(contract),
                       provide={"f": boom}),
         "f() failed: ValueError: no dialect in common")


@pytest.mark.parametrize("impl,needle", [
    ('{symbol: "f"}', "provide= has no 'f'"),
    ('{from: "no_such_module_xyz", symbol: "f"}', "cannot load 'f'"),
    ('{from: "math", symbol: "nope"}', "cannot load 'nope'"),
    ('{from: "math", symbol: "pi"}', "is not callable"),
])
def test_code_that_cannot_be_found_is_akan_at_the_call(impl, needle):
    contract = f'f:\n  params: {{}}\n  returns: "str"\n  impl: {{python: {impl}}}\n'
    akan(lambda: loads('u: y"{f()}"\n', contract=loads_contract(contract)),
         needle)


def test_unused_code_is_never_loaded():
    contract = 'f:\n  params: {}\n  returns: "str"\n' \
               '  impl: {python: {from: "no_such_module_xyz", symbol: "f"}}\n'
    assert loads('u: "plain"\n', contract=loads_contract(contract)) == \
        {"u": "plain"}


# --------------------------------------------------------------------------- #
# Tiers, and the other entry points
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("doc,tier", [
    ('a: 1\n', 1),
    ('a: {x: 1}\nu: y"{a.__AS_JSON__()}"\n', 2),
    ('u: y"{f()}"\n', 3),
    ('u: y"{__AS_JSON__(f())}"\n', 3),
    ('d: {k: 1}\nu: y"{d[f()]}"\n', 3),
    ('u: y"{a.__AS_JSON__(lexemes=f())}"\na: 1\n', 3),
])
def test_a_document_that_calls_a_declared_function_is_an_assembly(doc, tier):
    assert tier_of(doc) == tier


def test_expand_record_and_lookup_take_a_contract_too():
    c, p = loads_contract(MATCH), {"match_first": match_first}
    out = expand_record(DOC, contract=c, provide=p)
    assert 'protocol: "responses"' in out
    tree = load()
    assert lookup(tree, tree["mind"], "match_first(__ROOT__.supported, "
                                      "dialects)", contract=c, provide=p) \
        == "responses"
