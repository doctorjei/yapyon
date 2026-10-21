"""`yapyon expand` — the bridge from a full document down to a record.

`expand_record(text)` parses, resolves, and emits: the document's
y-strings are replaced by the values they resolve to, and what comes out
is a **record** (SPEC §12) — every leaf a literal, loadable by an
implementation that has no resolver at all. It is the tier-crossing step:
full form in, minimal form out.

**It emits from the resolved AST, never from loaded values.** That is the
same discipline `emitter` is built on, and for the same reason: `3.10` must
stay `3.10`. The distinction here is *when* the tree stops being a record.
A record is one that never had a y-string; this is one that had them and
resolved them away. Untouched literals keep their `Scalar.lexeme`, so a
`version: 3.10` the document never splices still comes back as `3.10` and
not `3.1`. A resolved y-string becomes a `Scalar` carrying its value and
no lexeme, which is right — the joined text *is* the value, and there is
no earlier spelling of it worth preserving.

**The one thing that cannot cross is a `yt`.** Its value is a `Template`:
the parts plus the resolved values, deliberately **unjoined**, because
§6 puts rendering in the hands of the consumer that knows the destination.
A record's leaves must be literals, and a template is not one. So this
refuses rather than joining: joining would make yapyon render a template
that §6 says only the consumer may render, and would make `yt` mean `y` in
the output — a silent change of meaning, which law 7 puts an akan on
instead. A record-level construct that could hold a template would be a
format change, not an emitter feature.

The guarantee, for a document without a `yt`:

    loads_record(expand_record(s)) == loads(s)

which is the property the tests assert over a corpus rather than a list of
hand-picked cases.
"""

from __future__ import annotations

import os
import sys

from ._cli import run
from .emitter import emit
from .environment import ENV_ALL, STANDARD_ENV, environment
from ._digits import REFUSE_DIGITS
from .lexer import AkanError, Lexer
from .loader import _functions
from .parser import Parser
from .resolver import REFUSE_DEPTH, REFUSE_SIZE, resolve
from .serializers import YEETED_YT


def _refuse_template(tokens, source: str | None = None) -> None:
    """A `yt` has no record form, so an expanded document cannot hold one.

    Decided over the token stream, on the same footing as `loader
    ._refuse_deferred`: the prefix alone decides, with no context to
    consult, and the token still carries the position the akan needs.

    Runs **before** resolution on purpose. A `yt` makes expansion
    impossible whatever the resolver would go on to produce, so making the
    caller wait through a full resolve to be told that would be work for
    nothing — and if the document *also* had a cycle, this reports the
    thing that actually blocks *this* operation. The cycle is still
    reported by `loads`, which is where it belongs.
    """
    for tok in tokens:
        if tok.kind == "YTSTR":
            raise AkanError(YEETED_YT, tok.line, tok.col, source)


def _expand(text: str, source: str | None = None, *,
            max_depth: int = REFUSE_DEPTH, max_size: int = REFUSE_SIZE,
            max_digits: int = REFUSE_DIGITS, contract=None, provide=None,
            warn=None, env_allow=STANDARD_ENV,
            env=os.environ) -> tuple[str, list[str]]:
    """Full document in; record source out, plus any shirans on the way.

    Shirans are reported as they happen rather than batched at the end, so
    that a later akan cannot swallow an earlier warning — the ordering
    `loads` already keeps.
    """
    view = environment(env, env_allow)
    lexer = Lexer(text, source=source, max_digits=max_digits)
    tokens = lexer.tokenize()
    parser = Parser(tokens, lexer.warnings, source=source)
    tree = parser.parse()
    _refuse_template(tokens, source)

    shirans: list[str] = []

    def report(message: str) -> None:
        shirans.append(message)
        if warn is not None:
            warn(message)

    for message in parser.warnings:
        report(message)
    resolved = resolve(tree, max_depth=max_depth, max_size=max_size,
                       max_digits=max_digits,
                       functions=_functions(contract, provide),
                       environment=view, warn=report, source=source)
    return emit(resolved, source=source), shirans


def expand_record(text: str, *, env_allow=STANDARD_ENV, env=os.environ,
                  max_depth: int = REFUSE_DEPTH,
                  max_size: int = REFUSE_SIZE, max_digits: int = REFUSE_DIGITS,
                  contract=None, provide=None,
                  source: str | None = None) -> str:
    """A full document in; canonical record source out.

    Warnings are dropped here, as everywhere in the library API; the CLI
    surfaces them (see `_cli`). Use `_expand` to reach them.

    **Why `expand_record` and not `expand`:** the CLI stage has to be a
    module named `expand`, and a function exported under the same name
    shadows it — `import yapyon.expand as m` would bind the *function* and
    `m.main` would be gone. The house already keeps the two apart for
    exactly that reason (`emitter.py` exports `emit`), and `_record` puts
    this beside `loads_record`, `load_record` and `is_record`, where the
    suffix marks the record form the operation is about.
    """
    return _expand(text, source=source, max_depth=max_depth,
                   max_size=max_size, max_digits=max_digits,
                   contract=contract, provide=provide,
                   env_allow=env_allow, env=env)[0]


USAGE = ("usage: python -m yapyon expand [--env-allow NAME]... [--env-all] "
         "[--no-env] [FILE]")


def main(argv: list[str]) -> int:
    """`--env-allow NAME` (repeatable) exposes a variable beyond the standard
    set, `--env-all` exposes every one, and `--no-env` turns environment
    access off (SPEC §5.1.3, §5.1.4)."""
    rest, allow, env_all, no_env = [argv[0]], set(), False, False
    args = iter(argv[1:])
    for arg in args:
        if arg == "--env-allow":
            name = next(args, None)
            if name is None:
                print(f"akan: --env-allow needs a name\n{USAGE}",
                      file=sys.stderr)
                return 2
            allow.add(name)
        elif arg == "--env-all":
            env_all = True
        elif arg == "--no-env":
            no_env = True
        elif arg.startswith("--"):
            print(f"akan: unknown option {arg}\n{USAGE}", file=sys.stderr)
            return 2
        else:
            rest.append(arg)
    env_allow = ENV_ALL if env_all else STANDARD_ENV | allow
    env = None if no_env else os.environ
    return run(rest, lambda text, source: _expand(
        text, source, env_allow=env_allow, env=env))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
