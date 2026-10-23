"""The emitter — SPEC §12 records back to canonical yapyon source.

The load-bearing test here is `test_every_case_round_trips`: for a normalizer,
"the value survives" is the whole contract, and it is checkable over a corpus
rather than one assertion at a time. The individual tests below pin the
*spelling* decisions, which the round-trip alone cannot see.
"""

import subprocess
import sys
from pathlib import Path

import pytest

import yapyon
from yapyon import AkanError, emit, loads_record
from yapyon.parser import parse
from yapyon.record import normalize

# One entry per shape the emitter has to make a decision about. Each must be a
# valid record; `test_every_case_round_trips` asserts emit-then-reload is
# value-preserving for all of them.
CORPUS = {
    "scalars": 'a: "s"\nb: 8080\nc: 3.10\nd: True\ne: None\n',
    "float lexemes": "a: 3.10\nb: 1e10\nc: 0x1f\nd: 1_000\ne: -2.50\n",
    "nested mappings": "a:\n  b:\n    c: 1\n",
    "sequence": "xs:\n  - 1\n  - 2\n",
    "nested sequence": "xs:\n  - - 1\n  - - 2\n",
    "mapping in sequence": "xs:\n  - x: 1\n    y: 2\n",
    "sequence under a key in a sequence": "xs:\n  - x:\n      - 1\n",
    "multimap": "m:\n  + k: 1\n  + k: 2\n",
    "multimap with a block value": "m:\n  + k:\n      a: 1\n  + k: 2\n",
    "multimap with a sequence value": "m:\n  + k:\n      - 1\n  + k: 2\n",
    "empty containers": "a: []\nb: {}\n",
    "empty containers nested": "xs:\n  - []\n  - {}\n",
    "empty string": 'a: ""\n',
    "escapes": 'a: "tab\\there"\nb: "nl\\nhere"\nc: "back\\\\slash"\n',
    "escaped quotes": 'a: "say \\"hi\\""\n',
    "control characters": 'a: "\\x01\\x7f"\n',
    "unicode stays literal": 'a: "caf\u00e9 \u65e5\u672c \U0001f600"\n',
    "raw string": 'a: r"a\\nb"\n',
    "single quotes": "a: 'x'\n",
    "b bytes": 'a: b"\\x89PNG\\r\\n"\n',
    "b64 bytes": 'a: b64"aGVsbG8="\n',
    "block string": 'a: """one\n  two"""\n',
    "block string with a blank line": 'a: """one\n\n  two"""\n',
    "block string ending in a newline": 'a: """one\n  """\n',
    "block string in a sequence": 'xs:\n  - """one\n    two"""\n',
    "deep mixture": ("top: 1\nmid:\n  xs:\n    - a: 1\n      b:\n"
                     "        - 2\n  m:\n    + k: 3\n"),
}


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_every_case_round_trips(name):
    # The contract: spelling may change, the value may not.
    source = CORPUS[name]
    assert loads_record(emit(parse(source))) == loads_record(source)


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_emitting_is_idempotent(name):
    # Canonical output is already canonical: a second pass changes nothing.
    once = emit(parse(CORPUS[name]))
    assert emit(parse(once)) == once


# --------------------------------------------------------------------------- #
# The spelling decisions (agreed 2026-09-14)
# --------------------------------------------------------------------------- #
def test_numbers_and_keywords_keep_their_source_lexeme():
    # §5.4's rule, and the reason the emitter works from the AST: by the time
    # loads_record has returned a float, 3.10 and 3.1 are the same object.
    assert emit(parse("a: 3.10\n")) == "a: 3.10\n"
    assert emit(parse("a: 1_000\n")) == "a: 1_000\n"
    assert emit(parse("a: 0x1f\n")) == "a: 0x1f\n"


@pytest.mark.parametrize("literal", [
    "'x'", '"caf\u00e9"', '"q\\"q"', 'r"a\\nb"', '"\\x41"', "'''x'''",
    'rb"\\d"', 'b"\\x89PNG"', 'b64"aGk="', "0x1f", "1_000", "3.10", "True",
])
def test_a_literal_is_written_as_the_author_wrote_it(literal):
    # SPEC \u00a74.4 v0.3: "must write each literal's lexeme"
    assert emit(parse(f"a: {literal}\n")) == f"a: {literal}\n"


def _one(scalar):
    from yapyon.parser import Mapping, Pair
    return Mapping(1, 0, [Pair(1, 0, "a", scalar)])


@pytest.mark.parametrize("value,canonical", [
    ("x", '"x"'), ("caf\u00e9", '"caf\u00e9"'), ('q"q', '"q\\"q"'),
    ("a\\nb", '"a\\\\nb"'), ("tab\there", '"tab\\there"'),
])
def test_a_string_with_no_lexeme_is_canonical(value, canonical):
    # a resolved y-string, a call's result: double quotes, minimal escapes
    from yapyon.parser import Scalar
    assert emit(_one(Scalar(1, 3, "str", value))) == f"a: {canonical}\n"


def test_bytes_with_no_lexeme_are_b_spelled():
    from yapyon.parser import Scalar
    assert emit(_one(Scalar(1, 3, "bytes", b"\x89P"))) == 'a: b"\\x89P"\n'


def test_the_block_form_is_canonical_exactly_when_there_is_a_newline():
    from yapyon.parser import Scalar
    assert emit(_one(Scalar(1, 3, "str", "one\ntwo"))) == \
        'a: """\n  one\n  two"""\n'


@pytest.mark.parametrize("doc,expected", [
    # a block lexeme keeps its spelling and takes the writer's indentation
    ('a: """one\n        two"""\n', 'a: """one\n  two"""\n'),
    ('a:\n  b: """\n          x\n            y\n\n          """\n',
     'a:\n  b: """\n    x\n      y\n\n    """\n'),
    ('- """\n x\n """\n', '- """\n  x\n  """\n'),
])
def test_a_block_lexeme_is_reindented_as_a_whole(doc, expected):
    out = emit(parse(doc))
    assert out == expected
    assert loads_record(out) == loads_record(doc)


def test_bytes_keep_the_spelling_the_document_chose():
    # A consumer naming its own encoding is the closed door behind §5.5; the
    # emitter must not decide base64 on a b"..." author's behalf.
    assert emit(parse('a: b"\\x89PNG"\n')) == 'a: b"\\x89PNG"\n'
    assert emit(parse('a: b64"aGVsbG8="\n')) == 'a: b64"aGVsbG8="\n'


def test_an_empty_container_is_written_flow():
    # There is no block spelling for emptiness.
    assert emit(parse("a: []\nb: {}\n")) == "a: []\nb: {}\n"


def test_layout_is_section_14_1_s():
    # a sequence holding no mapping or multimap is one line if it fits;
    # mappings are block whatever their source spelling
    assert emit(parse("a:\n  - 1\n  - 2\n")) == "a: [1, 2]\n"
    assert emit(parse("a: [[1], [], 'x']\n")) == "a: [[1], [], 'x']\n"
    assert emit(parse("a: {x: 1}\n")) == "a:\n  x: 1\n"
    assert emit(parse("a: [{x: 1}]\n")) == "a:\n  - x: 1\n"


def test_a_sequence_that_does_not_fit_is_block():
    long = ", ".join(f'"item{i:02}"' for i in range(12))
    out = emit(parse(f"a: [{long}]\n"))
    assert out.startswith('a:\n  - "item00"\n')
    assert emit(parse(f"a: [{long[:60]}]\n")).count("\n") == 1


def test_a_multi_line_lexeme_keeps_its_list_in_block_form():
    assert emit(parse('a:\n  - """\n    x\n    """\n')) == \
        'a:\n  - """\n    x\n    """\n'


def test_comments_do_not_survive():
    # Stated, not discovered: comment-preserving round-trip is unsolved, so
    # this is a normalizer and not a round-tripper.
    assert emit(parse("# gone\na: 1\n")) == "a: 1\n"


# --------------------------------------------------------------------------- #
# §12.5 — a non-record is refused where the mistake is
# --------------------------------------------------------------------------- #
def test_a_y_string_is_refused_at_its_own_position():
    with pytest.raises(AkanError) as e:
        emit(parse('a: "x"\nb: y"{a}"\n'))
    assert "must all be literals" in str(e.value)
    assert (e.value.line, e.value.col) == (2, 3)


def test_normalize_refuses_a_non_record_and_names_the_source():
    with pytest.raises(AkanError) as e:
        normalize('a: "x"\nb: y"{a}"\n', source="f.yap")
    assert str(e.value).startswith("akan: f.yap:2:3: ")


def test_normalize_is_the_whole_pipeline():
    assert normalize("a:\n  - 1\n  - 2\n") == "a: [1, 2]\n"


# --------------------------------------------------------------------------- #
# The CLI
# --------------------------------------------------------------------------- #
def _run(text):
    return subprocess.run([sys.executable, "-m", "yapyon.record"],
                          input=text, capture_output=True, text=True)


def test_the_cli_prints_yapyon_on_stdout():
    done = _run("a: [1, 2]\n")
    assert done.returncode == 0
    assert done.stdout == "a: [1, 2]\n"


def test_the_cli_refuses_a_non_record_on_stderr():
    done = _run('a: "x"\nb: y"{a}"\n')
    assert done.returncode == 1
    assert "must all be literals" in done.stderr
    assert done.stdout == ""


def test_the_worked_example_round_trips():
    # examples/registry.yap is a real record written for its own sake, not
    # as a fixture for this test -- which is what makes it worth asserting on.
    path = Path(yapyon.__file__).parents[2] / "examples" / "registry.yap"
    if not path.exists():
        pytest.skip(f"{path} not present")
    source = path.read_text(encoding="utf-8")
    assert loads_record(normalize(source)) == loads_record(source)
