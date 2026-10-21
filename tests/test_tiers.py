"""Document tiers (SPEC §12) — one test per rule, named after the rule.

**1** a record (literals only), **2** a ledger (splices and built-ins,
finished by its own bytes), **3** a template (finished by something outside
the document: the environment it reads, or the consumer joining a `yt`),
**4** an assembly (calls a function a contract declares).
"""

import subprocess
import sys

import pytest

import yapyon
from yapyon import AkanError, is_record, tier_of

RECORDS = [
    'a: "x"\n',
    'a: 1\nb: 3.10\nc: None\n',
    'a:\n  - 1\n  - 2\n',
    'a: b"\\x89PNG"\n',
    'a: "x"\na: "y"\n',          # a multimap is plain keyed data
]

LEDGERS = [
    'n: "gw"\nb: y"{n} v1"\n',
    'a: ry"x"\n',
    'a: yb"x"\n',
    'cfg:\n  a: 1\nj: y"{cfg.__AS_JSON__()}"\n',
]

TEMPLATES = [
    'a: yt"x"\n',
    'home: y"{$HOME}"\n',
    'home: y"{__ENV__(\'HOME\')}"\n',
    'j: y"{$HOME.__AS_JSON__()}"\n',
    'd:\n  x: 1\nv: y"{d[$USER]}"\n',
    'v: y"{__AS_JSON__($HOME)}"\n',
]

ASSEMBLIES = [
    'v: y"{f(1)}"\n',
    'home: y"{f($HOME)}"\n',          # a declared call outranks the env
    'a: yt"{f(1)}"\n',
]


def run(text):
    return subprocess.run([sys.executable, "-m", "yapyon", "tier"],
                         input=text, capture_output=True, text=True)


# --------------------------------------------------------------------------- #
# The rule: the tier is the least the bytes need
# --------------------------------------------------------------------------- #
def test_a_record_is_tier_1():
    for text in RECORDS:
        assert tier_of(text) == 1, text


def test_y_yb_and_ry_make_a_ledger():
    for text in LEDGERS:
        assert tier_of(text) == 2, text


def test_built_in_serializers_keep_a_document_a_ledger():
    assert tier_of('cfg:\n  a: 1\nj: y"{cfg.__AS_YAML__()}"\n') == 2


def test_a_yt_makes_a_template():
    # SPEC §6: the consumer joins a `yt`'s parts, so the document alone does
    # not finish it, and it cannot reduce to a record.
    assert tier_of('a: yt"x"\n') == 3


def test_reading_the_environment_makes_a_template():
    for text in TEMPLATES:
        assert tier_of(text) == 3, text


def test_calling_a_declared_function_makes_an_assembly():
    for text in ASSEMBLIES:
        assert tier_of(text) == 4, text


def test_tier_1_is_exactly_is_record():
    # Two functions, one question. A divergence here would be trap 5's shape.
    for text in RECORDS + LEDGERS + TEMPLATES + ASSEMBLIES:
        assert (tier_of(text) == 1) == is_record(text), text


def test_an_env_reference_nested_in_a_bracket_still_counts():
    assert tier_of('d:\n  x: 1\nv: y"{d[e[$X]]}"\ne:\n  a: "x"\n') == 3


def test_a_dollar_outside_a_hole_reads_nothing():
    # `y"${HOME}"` is a `$` and then the hole `{HOME}` (GRAMMAR §G4.7).
    assert tier_of('HOME: "h"\nv: y"${HOME}"\n') == 2


def test_an_empty_document_is_tier_1():
    assert tier_of("") == 1


# --------------------------------------------------------------------------- #
# The discipline: read the tokens, leave the parse alone
# --------------------------------------------------------------------------- #
def test_text_that_lexes_but_does_not_parse_still_gets_a_tier():
    assert tier_of('a: "x"\n- 1\n') == 1


def test_text_that_does_not_lex_raises_and_names_the_source():
    with pytest.raises(AkanError) as e:
        tier_of('a: "unterminated\n', source="broken.yap")
    assert "broken.yap" in str(e.value)


def test_tier_of_is_part_of_the_public_api():
    assert yapyon.tier_of is tier_of
    assert "tier_of" in yapyon.__all__


# --------------------------------------------------------------------------- #
# The CLI: a number on stdout, nothing else
# --------------------------------------------------------------------------- #
def test_the_cli_prints_the_tier_and_nothing_else():
    done = run('n: "gw"\nb: y"{n}"\n')
    assert done.stdout == "2\n"
    assert done.returncode == 0


def test_the_cli_prints_1_for_a_record():
    assert run('a: "x"\n').stdout == "1\n"


def test_the_cli_prints_3_for_a_template_and_4_for_an_assembly():
    assert run('h: y"{$HOME}"\n').stdout == "3\n"
    assert run('v: y"{f(1)}"\n').stdout == "4\n"


def test_the_cli_reports_an_unlexable_document_on_stderr_not_stdout():
    done = run('a: "unterminated\n')
    assert done.stdout == ""
    assert "akan" in done.stderr
    assert done.returncode == 1


def test_tier_is_a_named_stage():
    done = subprocess.run([sys.executable, "-m", "yapyon", "nope"],
                         input="", capture_output=True, text=True)
    assert "tier" in done.stderr
