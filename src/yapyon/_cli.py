"""Shared plumbing for the `python -m yapyon.*` entry points.

Three rules live here, once, because four copies of them would drift:

* **Shirans go to stderr and are shown by default.** The library keeps them
  behind `warn=` — a caller may not want them — but a person at a terminal
  asked to see what the tool thinks, so a CLI that swallowed them would be
  hiding the only warning rung the format has.
* **A shiran never changes the exit status.** It is legal-but-suspicious, not
  an error; a pipeline consuming stdout must not break because of one.
* **Diagnostics never go to stdout.** `python -m yapyon.record` writes yapyon
  there and its output is meant to be redirected, so an akan or a shiran on
  stdout would corrupt the file it is being written into.
"""

from __future__ import annotations

import sys

from .lexer import AkanError


def source_from(argv: list[str]) -> tuple[str, str | None]:
    """The file named on the command line, or stdin. The name is returned so
    diagnostics can carry it — `f.ypy:3:9` rather than `line 3, col 9`."""
    name = argv[1] if len(argv) > 1 else None
    text = open(name, encoding="utf-8").read() if name else sys.stdin.read()
    return text, name


def run(argv: list[str], work) -> int:
    """`work(text, source) -> (stdout_text, warnings)`, wrapped in the rules.

    Warnings are written before the output: they are diagnostics *about* the
    input, and on a terminal a long dump would otherwise scroll them away.
    """
    text, name = source_from(argv)
    try:
        out, warnings = work(text, name)
    except AkanError as exc:
        print(exc, file=sys.stderr)
        return 1
    for warning in warnings:
        print(warning, file=sys.stderr)
    sys.stdout.write(out)
    return 0
