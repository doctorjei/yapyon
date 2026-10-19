"""The thesis, as a property: the order of a mapping's keys never changes
what a document means.

§5.2's search is by name and §5.3's fixpoint resolves forward references, so
reordering the sibling keys of any mapping must load to equal data — or, for
a document that is akan, still be akan. Trap 4 is a resolver whose answer
depended on the order keys happened to appear; a subscript whose key was
written later shipped that way from 0.1.0 to 0.3.0 (fixed 2026-10-19). This
test reorders every block mapping in every corpus case, example, and
tutorial document, two ways, and requires the same answer.

Only block-mapping siblings move. Sequence items and multimap entries keep
their order, which is data. Comment and blank lines are dropped, since they
mean nothing. A document calling a serializer is skipped, because a
serializer writes keys in document order on purpose (order is data, §5.1.2);
one holding a `\"\"\"` string is skipped too: its content
lines are not structure, so a line-based reorder cannot see where it ends.
"""

import re
from pathlib import Path

import pytest

from yapyon import AkanError, loads, loads_record

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "docs" / "conformance" / "cases"
KEY_LINE = re.compile(r"^( *)[^\s\-+#\"'][^:]*:")


def _blocks(lines, start, end, indent):
    """Split lines[start:end] into blocks headed at exactly `indent`."""
    blocks, i = [], start
    while i < end:
        j = i + 1
        while j < end and _indent(lines[j]) > indent:
            j += 1
        blocks.append((i, j))
        i = j
    return blocks


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def reorder(text, how):
    """Every run of block-mapping siblings, reordered by `how(list)`."""
    lines = [ln for ln in text.splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]

    def walk(start, end, indent):
        out, run = [], []
        for i, j in _blocks(lines, start, end, indent):
            head = lines[i]
            child = next((_indent(lines[k]) for k in range(i + 1, j)), None)
            body = [head] + (walk(i + 1, j, child) if child is not None else [])
            if KEY_LINE.match(head):
                run.append(body)
            else:
                out += [ln for b in how(run) for ln in b] + body
                run = []
        return out + [ln for b in how(run) for ln in b]

    return "\n".join(walk(0, len(lines), 0)) + "\n"


def reverse(run):
    return run[::-1]


def rotate(run):
    return run[1:] + run[:1]


def documents():
    for path in sorted(CORPUS.glob("*/*.yap")):
        if path.name.endswith(".expected.yap"):
            continue
        yield f"{path.parent.name}/{path.stem}", path.read_text(encoding="utf-8")
    for path in sorted((ROOT / "examples").glob("*.yap")):
        yield f"examples/{path.stem}", path.read_text(encoding="utf-8")
    tutorial = (ROOT / "docs" / "TUTORIAL.md").read_text(encoding="utf-8")
    for n, block in enumerate(re.findall(r"^```yapyon\n(.*?)^```$", tutorial,
                                         re.M | re.S)):
        yield f"tutorial/{n}", block


# Documents built to stress the property: every reference form — dotted,
# subscripted by a literal, by a reference, and by an index, the multimap
# view, relative anchors, nearest-wins shadowing, a `yt` — waiting on
# y-strings that are themselves chains. The corpus mostly subscripts by
# literals, which is why the 0.3.0 bug needed a case of its own.
DENSE = [
    '''zz: y"{a.b[k].c}"
k: y"{k2}"
k2: y"{k3}"
k3: "two"
a:
  b:
    one: {c: "1"}
    two: {c: y"{deep}"}
deep: y"{__ROOT__.leaf}-{n}"
leaf: "L"
n: 7
''',
    '''out: y"{xs[i]}|{xs[-1]}|{mm.k[j]}|{mm.k[-1]}"
xs: ["a", y"{tail}"]
tail: y"{t1}{t2}"
t1: "t"
t2: y"{t3}"
t3: "z"
i: 0
j: 1
mm:
  + k: y"{first}"
  + k: y"{second}"
first: "m1"
second: y"{first}+"
''',
    '''personas:
  kimi:
    path: y"{base}/{__PARENT__.__KEY__}"
    who: y"{name}"
    name: y"{__PARENT__.__KEY__}!"
  goose:
    who: y"{name}"
    path: y"{base}/{__PARENT__.__KEY__}"
    name: y"{alias}"
    alias: y"{__PARENT__.__KEY__}?"
base: y"{root}/p"
root: "/r"
''',
    '''layers:
  outer:
    path: y"{path}/outer"
    inner:
      path: y"{path}/inner"
      use: y"{path}"
      pick: y"{table[sel]}"
      sel: y"{default}"
  path: y"{prefix}"
prefix: "/x"
table:
  alpha: y"{prefix}-A"
  beta: "B"
default: y"{d0}"
d0: "alpha"
''',
    '''t: yt"{a}{b[c]}{xs[n]}"
a: y"{b.q}"
b:
  q: "Q"
  w: y"{a}w"
c: y"{c0}"
c0: "w"
xs: [y"{a}", "s"]
n: -2
''',
]


# A serializer writes keys in document order — order is data (§5.1.2) — so
# its output legitimately follows a reorder; those documents are left out.
CASES = [(name, text) for name, text in documents()
         if '"""' not in text and "__AS_" not in text]
CASES += [(f"dense/{n}", text) for n, text in enumerate(DENSE)]


def outcome(name, text):
    load = loads_record if name.startswith("record/") else loads
    try:
        return "ok", load(text)
    except AkanError:
        return "akan", None


def test_the_property_has_cases_that_move():
    moved = [n for n, t in CASES
             if reorder(t, reverse) != reorder(t, lambda r: r)]
    assert len(CASES) > 50 and len(moved) > 30, (len(CASES), len(moved))


def test_reorder_keeps_sequences_and_multimaps_in_place():
    text = "b: 1\nxs:\n  - 1\n  - 2\nmm:\n  + k: 1\n  + k: 2\na:\n  y: 1\n  x: 2\n"
    assert reorder(text, reverse) == (
        "a:\n  x: 2\n  y: 1\nmm:\n  + k: 1\n  + k: 2\nxs:\n  - 1\n  - 2\nb: 1\n")


@pytest.mark.parametrize("how", [reverse, rotate], ids=["reverse", "rotate"])
@pytest.mark.parametrize("name,text", CASES, ids=[n for n, _ in CASES])
def test_key_order_does_not_change_meaning(name, text, how):
    base = outcome(name, text)
    moved = outcome(name, reorder(text, how))
    assert moved == base, f"{name}: {base} became {moved}"
