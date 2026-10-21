"""README.md and docs/DETAILS.md: every `>>>` session in them runs as a doctest.

The README is the first thing a user reads and the first thing that goes
stale (trap 6). Its long messages are hand-wrapped for reading, so
whitespace is normalized; the words are not. Since 2026-10-21 the README is
a short front page and the longer material lives in `docs/DETAILS.md`, so
both are executed, each on its own.
"""

import doctest
import pathlib
import re

import pytest

import yapyon

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGES = [ROOT / "README.md", ROOT / "docs" / "DETAILS.md"]


def _doctest(path):
    # A closing fence would read as expected output; blank every fence line.
    text = re.sub(r"^```.*$", "", path.read_text(encoding="utf-8"),
                  flags=re.M)
    # Each page reads as a continuation of the README, which imports
    # yapyon once at the top; DETAILS.md's sessions do not repeat it.
    return doctest.DocTestParser().get_doctest(
        text, {"yapyon": yapyon}, path.name, str(path), 0)


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.name)
def test_page_doctests(path):
    test = _doctest(path)
    assert test.examples, f"{path.name} has no >>> session left to run"
    runner = doctest.DocTestRunner(
        optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)
    runner.run(test)
    assert runner.failures == 0


def test_the_pages_still_carry_their_examples():
    # Guards against the sessions quietly disappearing in an edit, which
    # would leave the tests above passing while checking nothing.
    assert sum(len(_doctest(p).examples) for p in PAGES) >= 10
