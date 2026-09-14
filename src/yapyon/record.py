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

from .emitter import emit
from .lexer import AkanError, Lexer
from .loader import _refuse_deferred
from .parser import Parser


def normalize(text: str, *, source: str | None = None) -> str:
    """Record source in, canonical record source out."""
    lexer = Lexer(text, source=source)
    tokens = lexer.tokenize()
    tree = Parser(tokens, lexer.warnings, source=source).parse()
    # After the parse, and over tokens: a record is a strict subset of yapyon,
    # so subset membership is only a meaningful question about a member of the
    # set -- the same ordering `loads_record` uses, and the same message.
    _refuse_deferred(tokens, source)
    return emit(tree, source=source)


def main(argv: list[str]) -> int:
    name = argv[1] if len(argv) > 1 else None
    text = open(name, encoding="utf-8").read() if name else sys.stdin.read()
    try:
        sys.stdout.write(normalize(text, source=name))
    except AkanError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
