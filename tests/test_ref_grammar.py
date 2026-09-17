"""GRAMMAR §G5's `ref` production, against `lexer.parse_ref` — trap 8's gate.

`tools/check_ref_grammar.py` existed for a session as a script somebody was
supposed to remember to run after touching either side. That is a reminder, and
a reminder is exactly what trap 8 defeated: the stale production sat in a
docstring for two releases because nothing executed it. Running it here makes it
a catch.

The two assertions answer different questions and neither subsumes the other.
The corpus compares *shapes* — what each side accepts — so it can only test
serializer names that appear in the corpus. `test_serializer_production_matches_code`
compares the document's terminal list against `SERIALIZER_NAMES` directly, which
is the one thing a shape comparison structurally cannot see.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_ref_grammar as crg  # noqa: E402

from yapyon.serializers import SERIALIZER_NAMES  # noqa: E402


def test_document_and_implementation_agree_over_the_corpus():
    n, bad = crg.mismatches()
    assert n == len(crg.heads) * len(crg.steps) * len(crg.tails)
    assert bad == [], "\n".join(
        f"{c!r} impl={'Y' if impl else 'n'} grammar={'Y' if doc else 'n'}"
        for c, impl, doc in bad
    )


def test_serializer_production_matches_code():
    assert set(crg.serializers_from_grammar()) == set(SERIALIZER_NAMES)


def test_serializer_production_is_actually_read_from_the_document():
    """A parser that silently found nothing would make the check above vacuous."""
    assert set(crg.serializers_from_grammar()) == {
        "__AS_JSON__", "__AS_TOML__", "__AS_YAML__",
    }


def test_every_serializer_is_exercised_by_the_corpus():
    """The corpus is derived from the code, so a new serializer joins it."""
    for name in SERIALIZER_NAMES:
        assert f".{name}()" in crg.tails
