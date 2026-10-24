"""GRAMMAR §G5's `ref` production, against `lexer.parse_ref` — trap 8's gate.

`tools/check_ref_grammar.py` existed for a session as a script somebody was
supposed to remember to run after touching either side. That is a reminder, and
a reminder is exactly what trap 8 defeated: the stale production sat in a
docstring for two releases because nothing executed it. Running it here makes it
a catch.

The two assertions answer different questions and neither subsumes the other.
The corpus compares *shapes* — what each side accepts — and since v0.3 the
grammar admits any dunder call, so no shape can tell which built-ins exist.
`test_spec_builtins_match_code` compares SPEC §5.1.2's table against
`SERIALIZER_NAMES` directly, which is the one thing a shape comparison
structurally cannot see.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_ref_grammar as crg  # noqa: E402

from yapyon.serializers import SERIALIZER_NAMES  # noqa: E402


def test_document_and_implementation_agree_over_the_corpus():
    n, bad = crg.mismatches()
    assert n == len(list(crg.corpus())) > 5000
    assert bad == [], "\n".join(
        f"{c!r} impl={'Y' if impl else 'n'} grammar={'Y' if doc else 'n'}"
        for c, impl, doc in bad
    )


def test_the_corpus_has_both_answers():
    """A corpus the grammar rejects wholesale would agree with a parser that
    rejects everything; it must hold forms on both sides of the line."""
    accepted = sum(map(crg.generates, crg.corpus()))
    assert 1000 < accepted < len(list(crg.corpus())) - 1000


def test_spec_builtins_match_code():
    assert set(crg.builtins_from_spec()) == set(SERIALIZER_NAMES)


def test_spec_builtins_are_actually_read_from_the_document():
    """A reader that silently found nothing would make the check above vacuous."""
    assert set(crg.builtins_from_spec()) == {
        "__as_json__", "__as_toml__", "__as_yaml__", "__as_yapyon__",
    }


def test_every_serializer_is_exercised_by_the_corpus():
    """The corpus is derived from the code, so a new serializer joins it."""
    for name in SERIALIZER_NAMES:
        assert f".{name}()" in crg.tails
