"""`python -m yapyon <stage> [FILE]` — the stages, from the command line.

    python -m yapyon lexer  FILE    # token dump
    python -m yapyon parser FILE    # AST dump
    python -m yapyon record FILE    # a record, normalized back to yapyon

Prefer this spelling over `python -m yapyon.lexer`. Both work, but the
per-module form re-executes a module the package has already imported, which
makes CPython print a `RuntimeWarning` onto the very stream the diagnostics
use — and, before this indirection existed, gave the stage a second copy of
`AkanError` that `_cli` could not catch.

Diagnostics go to stderr, output to stdout, and a shiran does not change the
exit status; `_cli` holds those rules.
"""

from __future__ import annotations

import sys

STAGES = ("lexer", "parser", "record")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip(), file=sys.stderr)
        return 0 if len(argv) > 1 else 2
    stage, rest = argv[1], argv[2:]
    if stage not in STAGES:
        print(f"akan: no such stage {stage!r}; try one of "
              f"{', '.join(STAGES)}", file=sys.stderr)
        return 2
    from importlib import import_module
    module = import_module(f".{stage}", __package__)
    return module.main([f"yapyon {stage}", *rest])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
