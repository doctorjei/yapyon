"""docs/TUTORIAL.md: every example in it is executed.

The tutorial is Lore, not Law — it teaches and the spec defines — but an
example that has stopped being true is worse than none (trap 6: a sentence
with nothing executing it is indistinguishable from a false one). So:

- every `>>>` session runs as a doctest;
- every ```yapyon block loads with `yapyon.loads`; and
- every `# -> value` comment in one is compared with the loaded value at
  that key, the path found by indentation.
"""

import ast
import doctest
import pathlib
import re

import pytest

import yapyon

TUTORIAL = pathlib.Path(__file__).resolve().parent.parent / "docs" / "TUTORIAL.md"
TEXT = TUTORIAL.read_text(encoding="utf-8")

BLOCKS = re.findall(r"^```yapyon\n(.*?)^```$", TEXT, re.M | re.S)
KEY = re.compile(r"^( *)(\w+):")
EXPECT = re.compile(r"#\s*->\s*(.+?)\s*$")


def expectations(block):
    """(path, expected) for each `# -> value` comment, by indentation."""
    stack = []
    for line in block.splitlines():
        m = KEY.match(line)
        if not m:
            continue
        indent = len(m.group(1))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, m.group(2)))
        e = EXPECT.search(line)
        if e:
            yield [k for _, k in stack], ast.literal_eval(e.group(1))


def test_tutorial_doctests():
    # A closing fence would read as expected output; blank every fence line.
    text = re.sub(r"^```.*$", "", TEXT, flags=re.M)
    parser = doctest.DocTestParser()
    test = parser.get_doctest(text, {}, "TUTORIAL.md", str(TUTORIAL), 0)
    assert len(test.examples) > 20
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    runner.run(test)
    assert runner.failures == 0


def test_tutorial_has_blocks():
    assert len(BLOCKS) > 15
    assert sum(len(list(expectations(b))) for b in BLOCKS) > 30


@pytest.mark.parametrize("block", BLOCKS, ids=lambda b: b.splitlines()[0][:40])
def test_tutorial_block(block):
    warnings = []
    value = yapyon.loads(block, warn=warnings.append)
    assert warnings == []
    for path, expected in expectations(block):
        got = value
        for key in path:
            got = got[key]
        assert got == expected and type(got) is type(expected), (path, got)


def test_tutorial_console_matches_bridge():
    """The `$ python -m yapyon` session is what the CLI says about the file."""
    source = (TUTORIAL.parent.parent / "examples" / "bridge.yap").read_text(
        encoding="utf-8")
    session = re.search(r"^```console\n(.*?)^```$", TEXT, re.M | re.S).group(1)
    tier, expanded = re.match(
        r"\$ python -m yapyon tier examples/bridge\.yap\n(\d)\n"
        r"\$ python -m yapyon expand examples/bridge\.yap\n(.*)", session,
        re.S).groups()
    assert int(tier) == yapyon.tier_of(source)
    assert expanded == yapyon.expand_record(source)
