"""The conformance corpus, run as part of the suite.

`docs/conformance/` is the artifact a second implementation checks itself
against. Running it here is what stops it rotting: a case that yapyon
regresses on fails the suite, not just some external run nobody scheduled.

One pytest case per corpus case, so a failure names the file. The protocol
is `docs/conformance/README.md`; the runner is `tools/run_conformance.py`,
which is deliberately importable and deliberately not yapyon-specific in
its logic — a port reads the protocol and writes its own runner against the
same data.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from run_conformance import Case, DEFAULT_CORPUS, discover, run_case, same_data  # noqa: E402

CASES = discover(DEFAULT_CORPUS)


def test_the_corpus_is_present_and_has_all_three_kinds():
    # an empty corpus would make every test below vacuously green
    kinds = {c.kind for c in CASES}
    assert kinds == {"record", "full", "error"}, kinds
    assert len(CASES) >= 40, f"only {len(CASES)} cases — did a directory go missing?"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_conformance_case(case):
    ok, detail = run_case(case)
    assert ok, detail


@pytest.mark.parametrize('left,right', [(True, 1), (1, 1.0), ([True], [1]),
                                       ({'key': 1}, {'key': 1.0})])
def test_corpus_oracle_does_not_conflate_numeric_kinds(left, right):
    assert not same_data(left, right)[0]


def test_corpus_oracle_checks_types_inside_multimap_entries():
    import yapyon
    left, right = yapyon.OrderedMultimap(), yapyon.OrderedMultimap()
    left.insert('key', True)
    right.insert('key', 1)
    assert not same_data(left, right)[0]


def test_profile_corpus_oracle_detects_a_wrong_warning_count(tmp_path):
    folder = tmp_path / 'record'
    folder.mkdir()
    source = folder / 'warning.yap'
    expected = folder / 'warning.expected.yap'
    source.write_text('yes: 1\n', encoding='utf-8')
    expected.write_text('"yes": 1\n', encoding='utf-8')
    case = Case('record', source, expected, {'profile': 'yamlplus', 'warnings': 0})
    ok, why = run_case(case)
    assert not ok and 'warnings: got 1, expected 0' in why


@pytest.mark.parametrize('meta,reason', [
    ({'profile': 'yamlplus', 'info': []}, 'info:'),
    ({'profile': 'yamlplus', 'info': ['1 None value(s)'], 'formatted': 'missing: "None"\n'}, 'formatting:'),
])
def test_profile_corpus_oracle_detects_wrong_info_or_formatting(tmp_path, meta, reason):
    folder = tmp_path / 'record'
    folder.mkdir()
    source, expected = folder / 'notice.yap', folder / 'notice.expected.yap'
    source.write_text('missing: None\n', encoding='utf-8')
    expected.write_text('missing: None\n', encoding='utf-8')
    ok, why = run_case(Case('record', source, expected, meta))
    assert not ok and reason in why


def test_profile_error_oracle_detects_a_reader_that_accepts_too_much(tmp_path, monkeypatch):
    import yapyon

    folder = tmp_path / 'error'
    folder.mkdir()
    source = folder / 'number.yap'
    source.write_text('a: "\\101"\n', encoding='utf-8')
    case = Case('error', source, None, {'loader': 'yamlplus'})
    assert run_case(case)[0]
    monkeypatch.setattr(yapyon.yamlplus, 'loads', yapyon.loads_record)
    ok, why = run_case(case)
    assert not ok and 'expected akan' in why
