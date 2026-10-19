"""README.md: every `>>>` session in it runs as a doctest.

The README is the first thing a user reads and the first thing that goes
stale (trap 6). Its long messages are hand-wrapped for reading, so
whitespace is normalized; the words are not.
"""

import doctest
import pathlib
import re

README = pathlib.Path(__file__).resolve().parent.parent / "README.md"


def test_readme_doctests():
    # A closing fence would read as expected output; blank every fence line.
    text = re.sub(r"^```.*$", "", README.read_text(encoding="utf-8"),
                  flags=re.M)
    test = doctest.DocTestParser().get_doctest(text, {}, "README.md",
                                               str(README), 0)
    assert len(test.examples) >= 10
    runner = doctest.DocTestRunner(
        optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)
    runner.run(test)
    assert runner.failures == 0
