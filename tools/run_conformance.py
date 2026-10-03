#!/usr/bin/env python3
"""Run the yapyon conformance corpus.  Protocol: docs/conformance/README.md

The corpus is **data, not code**. A case is a pair of yapyon files — an
input and the record it must denote — or an input plus a `.meta.json`
saying it must be refused. Nothing in it is written in Python, so any
implementation can run it against itself. This is yapyon's own runner.

    python tools/run_conformance.py [-d CORPUS] [-v]

Exit status is 0 only when every case passes.

**Why the expectations are hand-authored, and why they differ from their
input.** The obvious way to produce a `.expected.ypy` is to run yapyon's
own `expand` over the input and keep what comes out. That would make this
corpus yapyon comparing itself to itself: a reader bug would be baked into
the expectation and the case would pass forever while testing nothing. So
every expectation here is written from the spec, and where the spec says two
different spellings denote the same data, the case spells them
*differently* on purpose — `b"hi"` against `b64"aGk="`, `name` against
`ｎａｍｅ`, block style against flow. A reader that mishandles either side
of one of those pairs fails, which is the property that makes the pair an
oracle rather than a tautology.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

import yapyon                                    # noqa: E402
from yapyon import AkanError                     # noqa: E402

DEFAULT_CORPUS = REPO / "docs" / "conformance"


class Case:
    """One corpus entry, as discovered on disk."""

    def __init__(self, kind: str, input_path: Path, expected_path: Path | None,
                 meta: dict | None = None):
        self.kind = kind                  # "record" | "full" | "error"
        self.input_path = input_path
        self.expected_path = expected_path
        self.meta = meta or {}

    @property
    def name(self) -> str:
        """`record/01-scalars.ypy` — relative to the `cases/` directory."""
        return self.input_path.relative_to(self.input_path.parents[1]).as_posix()

    def __repr__(self):
        return f"<Case {self.kind}:{self.name}>"


def discover(corpus_dir: Path) -> list[Case]:
    """Find every case under `corpus_dir/cases`, in a stable order."""
    cases: list[Case] = []
    cases_dir = corpus_dir / "cases"
    if not cases_dir.is_dir():
        raise SystemExit(f"no corpus at {cases_dir}")

    for kind in ("record", "full"):
        for input_path in sorted((cases_dir / kind).glob("*.ypy")):
            if input_path.name.endswith(".expected.ypy"):
                continue          # an expectation is not a case input
            expected = input_path.with_name(input_path.stem + ".expected.ypy")
            if not expected.exists():
                raise SystemExit(f"{input_path}: no {expected.name} beside it")
            cases.append(Case(kind, input_path, expected))

    for input_path in sorted((cases_dir / "error").glob("*.ypy")):
        meta_path = input_path.with_name(input_path.stem + ".meta.json")
        if not meta_path.exists():
            raise SystemExit(f"{input_path}: no {meta_path.name} beside it")
        cases.append(Case("error", input_path, None,
                         json.loads(meta_path.read_text(encoding="utf-8"))))
    return cases


def same_data(a, b) -> tuple[bool, str]:
    """Deep equality that also pins **key order**.

    Plain `==` on two dicts ignores order, and order is data in yapyon — a
    port that sorted every mapping would pass it. The expected file is a
    yapyon record, so its key order is already written down; comparing the
    key sequences as well costs nothing and closes that hole. A multimap's
    entry sequence is its data, and `OrderedMultimap.__eq__` already
    compares that (§7.1), so it needs no special handling beyond falling
    through to `==`.
    """
    if isinstance(a, dict) and isinstance(b, dict):
        if list(a.keys()) != list(b.keys()):
            return False, (f"key order: got {list(a.keys())}, "
                          f"expected {list(b.keys())}")
        for key in a:
            ok, why = same_data(a[key], b[key])
            if not ok:
                return False, f"[{key!r}] {why}"
        return True, ""
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False, f"length: got {len(a)}, expected {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            ok, why = same_data(x, y)
            if not ok:
                return False, f"[{i}] {why}"
        return True, ""
    if a == b:
        return True, ""
    return False, f"got {a!r}, expected {b!r}"


def run_case(case: Case) -> tuple[bool, str]:
    """Run one case, never raising.

    A runner that dies on the third case never tells you about the fortieth,
    so anything unexpected becomes a FAIL carrying the exception rather
    than a traceback that aborts the run.
    """
    try:
        return _run_case(case)
    except AkanError as e:
        return False, f"unexpected akan: {_first_line(str(e))}"
    except Exception as e:                       # noqa: BLE001 — see docstring
        return False, f"{type(e).__name__}: {e}"


def _run_case(case: Case) -> tuple[bool, str]:
    """Run one case. Returns `(passed, detail)`."""
    src = case.input_path.read_text(encoding="utf-8")

    if case.kind == "error":
        loader = (yapyon.loads_record if case.meta.get("loader") == "record"
                  else yapyon.loads)
        try:
            value = loader(src, source=case.name)
        except AkanError as e:
            return True, f"akan as expected: {_first_line(str(e))}"
        return False, f"expected akan ({case.meta.get('rule', '?')}), got {value!r}"

    expected = yapyon.loads_record(
        case.expected_path.read_text(encoding="utf-8"),
        source=case.expected_path.name)

    if case.kind == "record":
        # A record-tier input must actually be a record, or the case is
        # misfiled and is quietly testing the full pipeline instead.
        if yapyon.tier_of(src) != 1:
            return False, ("filed under record/ but tier_of says "
                          f"{yapyon.tier_of(src)} — it is not a record")
        got = yapyon.loads_record(src, source=case.name)
    else:
        if yapyon.tier_of(src) == 1:
            return False, ("filed under full/ but tier_of says 1 — it is a "
                          "record, so it tests nothing the record cases do not")
        got = yapyon.loads(src, source=case.name)

    ok, why = same_data(got, expected)
    if ok:
        return True, f"denotes the expected data: {_brief(got)}"
    return False, why


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0] if text.strip() else text


def _brief(value) -> str:
    text = repr(value)
    return text if len(text) <= 72 else text[:69] + "..."


def run_all(corpus_dir: Path = DEFAULT_CORPUS) -> list[tuple[Case, bool, str]]:
    return [(c, *run_case(c)) for c in discover(corpus_dir)]


def main(argv: list[str]) -> int:
    corpus = DEFAULT_CORPUS
    verbose = False
    if "-d" in argv:
        corpus = Path(argv[argv.index("-d") + 1])
    if "-v" in argv:
        verbose = True

    results = run_all(corpus)
    if not results:
        print("no cases found")
        return 1

    failures = [r for r in results if not r[1]]
    for case, ok, detail in results:
        if ok and not verbose:
            continue
        mark = "ok  " if ok else "FAIL"
        print(f"{mark} {case.kind:6} {case.name}: {detail}")

    by_kind: dict[str, list[int]] = {}
    for case, ok, _ in results:
        counts = by_kind.setdefault(case.kind, [0, 0])
        counts[0] += ok
        counts[1] += 1

    print()
    for kind, (passed, total) in sorted(by_kind.items()):
        print(f"  {kind:7} {passed}/{total}")
    print(f"  {'total':7} {len(results) - len(failures)}/{len(results)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
