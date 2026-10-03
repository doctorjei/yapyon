"""Document-level tests — one test per rule, named after the rule.

The axis is **closure, not power**: what a loader must have in hand to know
what the document means. **1** is a record (no resolver at all, §12), **2**
is self-contained (resolver in hand, law 3), **3** needs something outside
the document and is unreachable today.

Naming for the levels is deferred (`workbook/designs/document-tiers.md`),
so these tests speak in numbers deliberately.
"""

import subprocess
import sys

import pytest

import yapyon
from yapyon import AkanError, is_record, tier_of
from yapyon.loader import _DEFERRED_KINDS, _TIER3_KINDS

RECORDS = [
    'a: "x"\n',
    'a: 1\nb: 3.10\nc: None\n',
    'a:\n  - 1\n  - 2\n',
    'a: b"\\x89PNG"\n',
    'a: "x"\na: "y"\n',          # a multimap is plain keyed data
]

FULL = [
    'n: "gw"\nb: y"{n} v1"\n',
    'a: ry"x"\n',
    'a: yb"x"\n',
    'a: yt"x"\n',
]


def run(text):
    return subprocess.run([sys.executable, "-m", "yapyon", "tier"],
                         input=text, capture_output=True, text=True)


# --------------------------------------------------------------------------- #
# The rule: the level is the lowest loader capability the bytes need
# --------------------------------------------------------------------------- #
def test_a_record_is_level_1():
    for text in RECORDS:
        assert tier_of(text) == 1, text


def test_a_y_string_makes_the_document_level_2():
    assert tier_of('n: "gw"\nb: y"{n} v1"\n') == 2


def test_all_four_y_prefixes_are_level_2():
    # `ry` shares the YSTR token kind with `y` (lexer._TOKEN_KIND_FOR_PREFIX),
    # which is what makes _DEFERRED_KINDS cover all four prefixes with three
    # kinds. If that mapping ever changes, this is the test that notices
    # `tier_of` quietly started calling `ry` a record.
    for prefix in ("y", "yb", "yt", "ry"):
        assert tier_of(f'a: {prefix}"x"\n') == 2, prefix


def test_level_1_is_exactly_is_record():
    # Two functions, one question. A divergence here would be trap 5's shape:
    # two implementations of one rule, silently disagreeing.
    for text in RECORDS + FULL:
        assert (tier_of(text) == 1) == is_record(text), text


def test_an_empty_document_is_level_1():
    assert tier_of("") == 1


# --------------------------------------------------------------------------- #
# The tripwire: level 3 is unreachable because nothing reaches outside
# --------------------------------------------------------------------------- #
def test_no_construct_is_level_3_yet():
    # This asserts an *absence*, and it is the test that guards the absence.
    # When a tier-3 construct is built -- embedding, environment access --
    # this fails. Do not delete it: give the new construct its own token kind
    # in loader._TIER3_KINDS, its own level-3 test here, and re-read the
    # docstring on _TIER3_KINDS, which says why the set was empty.
    assert _TIER3_KINDS == frozenset()


def test_no_shipped_document_reaches_level_3():
    assert 3 not in {tier_of(t) for t in RECORDS + FULL}


# --------------------------------------------------------------------------- #
# The discipline: read the tokens, leave the parse alone
# --------------------------------------------------------------------------- #
def test_text_that_lexes_but_does_not_parse_still_gets_a_level():
    # Same discipline as is_record: the level is a fact about the token
    # stream, so a parse error is not this function's to report -- it
    # surfaces at load. This document mixes a pair and a sequence item, so
    # it lexes clean and fails to parse; the level is still answered.
    # (An unclosed bracket would NOT work here -- that is a lexer fact, and
    # this function would raise on it.)
    assert tier_of('a: "x"\n- 1\n') == 1


def test_text_that_does_not_lex_raises_and_names_the_source():
    with pytest.raises(AkanError) as e:
        tier_of('a: "unterminated\n', source="broken.ypn")
    assert "broken.ypn" in str(e.value)


def test_tier_of_is_part_of_the_public_api():
    assert yapyon.tier_of is tier_of
    assert "tier_of" in yapyon.__all__


# --------------------------------------------------------------------------- #
# The CLI: a number on stdout, nothing else
# --------------------------------------------------------------------------- #
def test_the_cli_prints_the_level_and_nothing_else():
    done = run('n: "gw"\nb: y"{n}"\n')
    assert done.stdout == "2\n"
    assert done.returncode == 0


def test_the_cli_prints_1_for_a_record():
    assert run('a: "x"\n').stdout == "1\n"


def test_the_cli_reports_an_unlexable_document_on_stderr_not_stdout():
    # stdout is the payload; a diagnostic there would corrupt whatever a
    # redirect is writing into it.
    done = run('a: "unterminated\n')
    assert done.stdout == ""
    assert "akan" in done.stderr
    assert done.returncode == 1


def test_tier_is_a_named_stage():
    done = subprocess.run([sys.executable, "-m", "yapyon", "nope"],
                         input="", capture_output=True, text=True)
    assert "tier" in done.stderr
