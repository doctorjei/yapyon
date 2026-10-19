"""GRAMMAR §G6: what a document is. `document ::= block_value EOF`.

**Any value is a valid document** — a file holding just `42` loads as `42`
(keep: operator, 2026-10-19, "it's important for some applications"). A tool
wanting a mapping at the top level enforces that itself. YAML and JSON agree;
TOML does not, which is why `__AS_TOML__()` refuses a single value — a fact
about serializer output, not about yapyon files.

Two edges differ from YAML, both by the grammar: a document must hold a
value, so an empty file is akan where YAML reads null; and a bare word is
akan where YAML reads a string (no plain scalars, ehmon 1).

Until 2026-10-19 nothing executed this rule (trap 6), and writing these
tests found the writers turning a root `{}` or `[]` into empty output.
"""

import subprocess
import sys

import pytest

from yapyon import (AkanError, emit, expand_record, loads, loads_record,
                    parse, tier_of)

SINGLE_VALUES = [
    ("42", 42), ("-1.5", -1.5), ("0xff", 255), ('"x"', "x"), ("'x'", "x"),
    ('b"x"', b"x"), ("hex'68'", b"h"), ("None", None), ("True", True),
    ("[1, 2]", [1, 2]), ("[]", []), ("{}", {}), ("{a: 1}", {"a": 1}),
    ('"""\n  two\n  lines\n  """', "two\nlines\n"),
]


@pytest.mark.parametrize("text,value", SINGLE_VALUES)
def test_any_value_is_a_document(text, value):
    loaded = loads(text + "\n")
    assert loaded == value and type(loaded) is type(value)


@pytest.mark.parametrize("text,value", SINGLE_VALUES)
def test_a_single_literal_is_a_record(text, value):
    assert loads_record(text + "\n") == value
    assert tier_of(text + "\n") == 1


@pytest.mark.parametrize("text,value", SINGLE_VALUES)
def test_a_single_value_round_trips_through_every_writer(text, value):
    # the emitter, the record bridge, and __AS_YAPYON__ share one writer
    assert loads_record(emit(parse(text + "\n"))) == value
    assert loads_record(expand_record(text + "\n")) == value
    wrapped = loads(f"a: {text}\nu: y\"{{a.__AS_YAPYON__()}}\"\n")["u"]
    assert loads_record(wrapped) == value


@pytest.mark.parametrize("text", ["{}", "[]"])
def test_an_empty_root_container_is_written_flow(text):
    # found 2026-10-19: these came back as "" -- an empty document, so akan
    assert emit(parse(text + "\n")) == text + "\n"
    assert expand_record(text + "\n") == text + "\n"


def test_the_record_cli_takes_a_single_value():
    done = subprocess.run([sys.executable, "-m", "yapyon", "record"],
                          input="0x2A\n", capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout == "0x2A\n"


def test_a_single_y_string_is_a_template_level_document():
    assert loads('y"x"\n') == "x"
    assert tier_of('y"x"\n') == 2
    assert expand_record('y"x"\n') == '"x"\n'


def test_a_single_value_may_be_indented_and_commented():
    assert loads("# a count\n  42\n") == 42


@pytest.mark.parametrize("text", ["", "\n", "   \n", "# only a comment\n",
                                  "\n# two\n\n# comments\n"])
def test_an_empty_document_is_akan(text):
    # GRAMMAR §G6 requires a value; YAML would read null here
    with pytest.raises(AkanError) as e:
        loads(text)
    assert "empty document" in str(e.value)


@pytest.mark.parametrize("text,needle", [
    ("42\n43\n", "expected end of file"),          # one document per file
    ("42 43\n", "expected end of line"),
    ("hello\n", "bare word 'hello'"),             # no plain scalars
])
def test_a_document_is_exactly_one_value(text, needle):
    with pytest.raises(AkanError) as e:
        loads(text)
    assert needle in str(e.value)
