"""CLI: `python -m yapyon.record FILE` — a record, normalized.

Prints the document back as **yapyon**, not as Python. A conformance tool
whose output were a Python `repr` would be useless to the audience it exists
for — a second implementation of the format — and a user wanting the loaded
values already has `yapyon.loads_record`.

Refuses a non-record at the offending prefix's line and column, per §12.5:
the document is well-formed yapyon, it is simply not a record.

Normalization loses spelling but never value, and **comments do not survive**
(`emitter` says why). The guarantee is
`loads_record(output) == loads_record(input)`.
"""

from __future__ import annotations

import sys

from ._cli import run
from .emitter import emit
from .lexer import Lexer
from .loader import _refuse_deferred
from .parser import Parser


def _normalize(text: str, source: str | None = None) -> tuple[str, list[str]]:
    """Record source in; canonical record source out, plus any shirans."""
    lexer = Lexer(text, source=source)
    tokens = lexer.tokenize()
    parser = Parser(tokens, lexer.warnings, source=source)
    tree = parser.parse()
    # After the parse, and over tokens: a record is a strict subset of yapyon,
    # so subset membership is only a meaningful question about a member of the
    # set -- the same ordering `loads_record` uses, and the same message.
    _refuse_deferred(tokens, source)
    return emit(tree, source=source), parser.warnings


def normalize(text: str, *, source: str | None = None) -> str:
    """Record source in, canonical record source out.

    Warnings are dropped here, as everywhere in the library API; the CLI
    surfaces them (see `_cli`). Use `_normalize` to reach them.
    """
    return _normalize(text, source)[0]


def main(argv: list[str]) -> int:
    # The warning channel is wired but structurally cannot fire here: every
    # shiran yapyon has comes from a hole (§5.1's avoidable bracket), and a
    # record has no holes at all. It stays connected rather than being
    # special-cased away, so that a future record-side shiran is surfaced by
    # construction instead of being forgotten.
    return run(argv, _normalize)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
