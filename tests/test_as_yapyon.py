"""`__AS_YAPYON__()` — SPEC §5.1.2.

The fourth serializer, and different from the other three in two ways that
are the whole of its design: it emits from the resolved **AST** (its output is
yapyon source, so §5.4's lexeme governs it), and it is the one encoding that
carries everything the data model has. Its only refusal of its own is `yt`.
"""

import pytest

from yapyon import AkanError, expand_record, is_record, loads, loads_record


def akan(src, needle):
    with pytest.raises(AkanError) as e:
        loads(src)
    assert needle in str(e.value)
    return str(e.value)


# The contract is a property, as for the emitter and `expand_record`: what the
# serializer writes, loaded as a record, is what the document meant there.
CORPUS = [
    'cfg:\n  a: 1\n  b: "two"\n',
    'cfg:\n  - 1\n  - "x"\n  - a: True\n',
    'cfg:\n  version: 3.10\n  port: +8080\n  off: -0\n',
    'cfg:\n  raw: b"\\x89PNG"\n  enc: b64"aGk="\n',
    'cfg:\n  unset: None\n  blank: ""\n  empty: []\n  none: {}\n',
    'cfg:\n  + k: 1\n  + k: 2\n  + j:\n      x: 1\n',
    'cfg:\n  text: "line one\\nline two\\n"\n',
    'cfg:\n  q: "say \\"hi\\""\n  u: "ｎａｍｅ"\n',
    'who: "there"\ncfg:\n  greet: y"hi {who}"\n  deep:\n    - y"{who}!"\n',
]


@pytest.mark.parametrize("src", CORPUS)
def test_as_yapyon_round_trips_through_a_record(src):
    d = loads(src + 'out: y"{cfg.__AS_YAPYON__()}"\n')
    assert loads_record(d["out"]) == d["cfg"]


@pytest.mark.parametrize("src", CORPUS)
def test_as_yapyon_writes_a_canonical_record(src):
    out = loads(src + 'out: y"{cfg.__AS_YAPYON__()}"\n')["out"]
    assert is_record(out)
    # canonical: normalizing it again changes nothing (SPEC §4.4)
    assert expand_record(out) == out


def test_as_yapyon_keeps_the_number_lexeme():
    # the reason it reads the AST: inside JSON `3.10` is the number 3.1, but
    # this output is yapyon source, where §5.4 says the lexeme survives
    d = loads('cfg:\n  v: 3.10\nj: y"{cfg.__AS_JSON__()}"\n'
              'y: y"{cfg.__AS_YAPYON__()}"\n')
    assert '3.1\n' in d["j"]
    assert d["y"] == "v: 3.10\n"


def test_as_yapyon_keeps_the_bytes_prefix():
    # a value-based writer would have to pick an encoding for bytes and
    # respell every b"..." as base64
    out = loads('cfg:\n  a: b"hi"\n  b: b64"aGk="\n'
                'out: y"{cfg.__AS_YAPYON__()}"\n')["out"]
    assert out == 'a: b"hi"\nb: b64"aGk="\n'


@pytest.mark.parametrize("src", [
    'cfg:\n  + k: 1\n  + k: 2\n',      # akan in JSON, TOML and YAML
    'cfg:\n  v: b"\\x00"\n',          # akan in all three
    'cfg:\n  v: None\n',               # akan in TOML
])
def test_as_yapyon_is_faithful_where_the_others_refuse(src):
    d = loads(src + 'out: y"{cfg.__AS_YAPYON__()}"\n')
    assert loads_record(d["out"]) == d["cfg"]


def test_as_yapyon_splices_into_text_like_any_serializer():
    d = loads('cfg:\n  a: 1\nout: y"head\\n{cfg.__AS_YAPYON__()}tail"\n')
    assert d["out"] == "head\na: 1\ntail"


def test_as_yapyon_encodes_a_list():
    out = loads('xs:\n  - 1\n  - 2\nout: y"{xs.__AS_YAPYON__()}"\n')["out"]
    assert out == "- 1\n- 2\n"
    assert loads_record(out) == [1, 2]


def test_as_yapyon_carries_another_serializers_output():
    d = loads('inner:\n  a: 1\ncfg:\n  j: y"{__ROOT__.inner.__AS_JSON__()}"\n'
              'out: y"{cfg.__AS_YAPYON__()}"\n')
    assert loads_record(d["out"]) == {"j": '{\n  "a": 1\n}'}


# --------------------------------------------------------------------------- #
# `yt` — the one thing with no record form (operator, 2026-10-12)
# --------------------------------------------------------------------------- #
def test_as_yapyon_refuses_a_template_in_its_target():
    # a record's leaves are literals; joining the parts would render what §6
    # leaves to the consumer, and make `yt` silently mean `y`
    akan('who: "x"\ncfg:\n  t: yt"hi {who}"\nout: y"{cfg.__AS_YAPYON__()}"\n',
         "`yt`")


def test_a_template_outside_the_target_is_untouched():
    d = loads('who: "x"\nt: yt"hi {who}"\ncfg:\n  a: 1\n'
              'out: y"{cfg.__AS_YAPYON__()}"\n')
    assert d["out"] == "a: 1\n"


# --------------------------------------------------------------------------- #
# The rules every serializer obeys, checked for this one (trap 9: a new path
# into the fixpoint must reach every outcome it defines)
# --------------------------------------------------------------------------- #
def test_as_yapyon_defers_to_a_resolvable_inner_ystring():
    # the inner y-string appears *after* the call, so it is unresolved on the
    # first visit and the encoding must wait rather than refuse
    d = loads('out: y"{cfg.__AS_YAPYON__()}"\ncfg:\n  p: y"{base}/1"\n'
              'base: "x"\n')
    assert d["out"] == 'p: "x/1"\n'


def test_mutually_referencing_as_yapyon_reports_a_cycle():
    with pytest.raises(AkanError) as e:
        loads('b1:\n  m: y"{__ROOT__.b2.__AS_YAPYON__()}"\n'
              'b2:\n  m: y"{__ROOT__.b1.__AS_YAPYON__()}"\n')
    assert "form a cycle" in str(e.value)


@pytest.mark.parametrize("ref", ["__ROOT__.__AS_YAPYON__()",
                                 "__PARENT__.__AS_YAPYON__()"])
def test_as_yapyon_on_a_bare_anchor_is_circular(ref):
    with pytest.raises(AkanError):
        loads(f'blk:\n  a: 1\n  me: y"{{{ref}}}"\n')


def test_as_yapyon_of_a_single_value_is_reserved():
    akan('n: 5\nu: y"{n.__AS_YAPYON__()}"\n', "is reserved")
