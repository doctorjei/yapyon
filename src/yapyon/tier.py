"""CLI: `python -m yapyon.tier FILE` — the level a document needs.

Prints **1**, **2** or **3** on stdout and nothing else, so it composes in
a shell test rather than needing to be parsed out of prose:

    [ "$(python -m yapyon.tier cfg.ypn)" = 1 ] && echo "a minimal loader can read this"

The level is *computed from the bytes*, not read off a declaration the
author wrote about the file. That is the whole point of it: a loader can
check a claimed level instead of trusting one. `loader.tier_of` holds what
each level means; **3 is unreachable today**, because no shipped construct
reaches outside the document.

The levels have no names yet — naming is deferred
(`workbook/designs/document-tiers.md`) — so this prints a number rather
than a word the format has not chosen.
"""

from __future__ import annotations

import sys

from ._cli import run
from .loader import tier_of


def _level(text: str, source: str | None = None) -> tuple[str, list[str]]:
    """The document's level, as the line stdout gets, plus any shirans.

    The warning channel is wired but structurally cannot fire: every shiran
    yapyon has comes from a hole (GRAMMAR §G5.4's avoidable bracket), which
    is a parse- and resolution-time fact, and this lexes only. It stays
    connected rather than special-cased away, so a future lex-time shiran is
    surfaced by construction instead of being forgotten.
    """
    return f"{tier_of(text, source=source)}\n", []


def main(argv: list[str]) -> int:
    return run(argv, _level)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
