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

from run_conformance import DEFAULT_CORPUS, discover, run_case  # noqa: E402

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
