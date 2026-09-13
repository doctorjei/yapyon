"""yapyon record tests — one test per rule, named after the rule.

A **yapyon record** is the restricted form in which every leaf element has a
literal value. When a test and the implementation disagree, check the spec
before changing either.
"""

import io

import pytest

import yapyon
from yapyon import (AkanError, OrderedMultimap, Template, is_record,
                    load_record, loads, loads_record)


def akan(text, needle=""):
    with pytest.raises(AkanError) as e:
        loads_record(text)
    assert needle in str(e.value), f"wrong message: {e.value}"


# --------------------------------------------------------------------------- #
# The rule: every leaf element has a literal value
# --------------------------------------------------------------------------- #
def test_the_five_literals_are_all_records():
    assert loads_record('a: "x"\nb: b"\\x89PNG"\nc: 1\nd: 3.10\ne: None\n') == {
        "a": "x", "b": b"\x89PNG", "c": 1, "d": 3.1, "e": None}


def test_containers_are_structure_not_leaves():
    # the rule reaches all the way down: nesting never makes a record less of
    # one, because a container is not a leaf
    doc = loads_record('m:\n  k:\n    - 1\n    - [2, {a: 3}]\nxs: []\n')
    assert doc == {"m": {"k": [1, [2, {"a": 3}]]}, "xs": []}


def test_a_y_string_is_akan():
    akan('root: "/srv"\nlogs: y"{root}/logs"\n',
         "a record's leaves must all be literals")


def test_the_akan_names_the_prefix_as_written():
    # y and ry share one token kind; the message must still name the spelling
    akan('a: "x"\nb: ry"{a}\\n"\n', "a ry-string defers its value")
    akan('a: "x"\nb: yb"{a}"\n', "a yb-string defers its value")
    akan('b: yt"{a}"\n', "a yt-string defers its value")


def test_the_akan_names_the_full_form_as_the_fix():
    akan('a: y"x"\n', "load with yapyon.loads for the full form")


def test_the_akan_points_at_the_y_string():
    with pytest.raises(AkanError) as e:
        loads_record('a: "x"\nb: "y"\nc: y"{a}"\n')
    assert (e.value.line, e.value.col) == (3, 3)


def test_a_y_string_anywhere_disqualifies_the_document():
    # the marker is the prefix, per string — it is not a top-level property
    akan('m:\n  xs:\n    - 1\n    - y"x"\n', "must all be literals")
    akan('m:\n  + a: 1\n  + b: y"x"\n', "must all be literals")


# --------------------------------------------------------------------------- #
# Braces in a plain string are inert — the record/full split is unambiguous
# --------------------------------------------------------------------------- #
def test_a_plain_string_holding_braces_is_a_record():
    # "{foo}" is six characters in every implementation; one with no resolver
    # never has to decide. This is what makes a minimal implementation
    # genuinely conforming.
    text = 'a: "{foo}"\nb: "{{foo}}"\nc: r"{foo}\\n"\n'
    expected = {"a": "{foo}", "b": "{{foo}}", "c": "{foo}\\n"}
    assert loads_record(text) == expected
    assert loads(text) == expected          # same answer in full yapyon


# --------------------------------------------------------------------------- #
# Return types (design table): no Template; OrderedMultimap is fine
# --------------------------------------------------------------------------- #
def test_a_record_never_returns_a_template():
    # yt is the one y-family prefix that would otherwise survive to `build`
    akan('t: yt"Hello {user}"\n', "must all be literals")


def test_a_multimap_is_plain_keyed_data_and_so_is_allowed():
    mm = loads_record('changes:\n  + registry: "set"\n  + file: "delete"\n'
                      '  + registry: "remove"\n')["changes"]
    assert isinstance(mm, OrderedMultimap)
    assert [(k, v) for k, v in mm] == [
        ("registry", "set"), ("file", "delete"), ("registry", "remove")]


# --------------------------------------------------------------------------- #
# A record is a strict subset of yapyon
# --------------------------------------------------------------------------- #
def test_every_record_is_a_valid_yapyon_document():
    text = 'a: "x"\nm:\n  - 1\n  - True\n'
    assert loads_record(text) == loads(text)


def test_a_syntax_error_is_reported_before_the_record_rule():
    # asking whether something belongs to the subset is only meaningful once
    # it belongs to the set
    akan('a: no\nb: y"x"\n', 'write False for the value or "no" for the string')


def test_a_lexical_error_still_reports_itself():
    akan('a: f"x"\n', "yapyon has no f-strings")


# --------------------------------------------------------------------------- #
# is_record — checkable by lexing alone
# --------------------------------------------------------------------------- #
def test_is_record_is_true_for_literal_leaves():
    assert is_record('a: "x"\nb: 1\nxs: [1, 2]\n')
    assert is_record('a: "{foo}"\n')
    assert is_record("")


def test_is_record_is_false_for_each_y_family_prefix():
    assert not is_record('a: y"x"\n')
    assert not is_record('a: ry"x"\n')
    assert not is_record('a: yb"x"\n')
    assert not is_record('a: yt"x"\n')


def test_is_record_answers_the_record_question_only():
    # lexes but does not parse: still a record, and the parse error waits
    # until it is loaded
    assert is_record("a: no\n")
    with pytest.raises(AkanError):
        loads_record("a: no\n")


def test_is_record_raises_when_there_is_no_document_to_answer_about():
    with pytest.raises(AkanError):
        is_record('a: f"x"\n')


# --------------------------------------------------------------------------- #
# The everyday API
# --------------------------------------------------------------------------- #
def test_load_record_reads_a_file_object():
    assert load_record(io.StringIO('a: "x"\n')) == {"a": "x"}


def test_load_record_refuses_a_y_string_from_a_file():
    with pytest.raises(AkanError):
        load_record(io.StringIO('a: y"x"\n'))


def test_a_record_takes_no_resolver_caps():
    # max_depth/max_size are §5.3 resolver limits; there is no resolver here
    import inspect
    params = inspect.signature(loads_record).parameters
    assert "max_depth" not in params and "max_size" not in params
    assert "text" in params and "warn" in params


def test_the_package_exposes_the_record_api():
    for name in ("load_record", "loads_record", "is_record"):
        assert name in yapyon.__all__ and hasattr(yapyon, name)


def test_template_is_still_reachable_for_full_yapyon():
    assert isinstance(loads('t: yt"{a}"\n')["t"], Template)
