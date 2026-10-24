"""SPEC §5.6, GRAMMAR §G4.8: a value ending in a call may stand bare.

Operator, 2026-10-24: the resolved value must not be owned somewhere else
in the tree — referencing is fine, moving is not. A call's result is owned
by nobody (for now), so it may land bare; a bare path names a value owned
elsewhere, so it is copied explicitly with parentheses.
"""

import pytest

from yapyon import AkanError, is_record, loads, tier_of


def test_a_bare_call_means_its_copy():
    doc = 'n: "03"\na: n.__int__()\nb: (n.__int__())\n'
    out = loads(doc)
    assert out["a"] == out["b"] == 3


def test_the_motivating_case():
    doc = ('persona:\n  mind:\n    model_list: []\n'
           'FABLE: persona.mind.model_list.__get__(0)?.__str__()\n')
    assert loads(doc)["FABLE"] is None


def test_bare_calls_stand_wherever_a_value_does():
    doc = 'n: "7"\nl: [n.__int__(), 5]\nm: {a: n.__int__()}\ns:\n  - n.__int__()\n'
    out = loads(doc)
    assert out["l"] == [7, 5] and out["m"] == {"a": 7} and out["s"] == [7]


def test_a_call_may_stand_alone():
    assert loads('a: __int__("12")\n')["a"] == 12


@pytest.mark.parametrize("text,hint", [
    ("x: foo.bar\n", '"foo.bar" for the text, or (foo.bar)'),
    ("x: foo[0]\n", "(foo[0]) for a copy"),
    ("x: example.com\n", '"example.com" for the text'),
    ("a: [1]\nx: a.__int__\n", '"a.__int__"'),
])
def test_a_bare_path_is_still_akan(text, hint):
    with pytest.raises(AkanError, match="bare word") as e:
        loads(text)
    assert hint in str(e.value)


def test_a_bare_word_with_no_reading_offers_only_text():
    with pytest.raises(AkanError) as e:
        loads("x: what?\n")
    assert '"what?" for the text' in str(e.value) and "copy" not in str(e.value)


def test_plain_bare_words_keep_their_message():
    with pytest.raises(AkanError, match="write False"):
        loads("x: no\n")


def test_a_bare_call_is_not_a_record_and_takes_its_call_s_tier():
    doc = 'n: "1"\nx: n.__int__()\n'
    assert not is_record(doc) and tier_of(doc) == 2
    assert tier_of("x: $HOME.__str__()\n") == 3
