"""The `python -m yapyon.*` entry points.

What is actually being pinned here is the contract in `_cli`: shirans are
shown, they go to stderr, and they do not change the exit status. The library
keeps warnings behind `warn=`; a CLI has a person in front of it.
"""

import subprocess
import sys

import pytest

# A hole spelled the long way -- the one shiran yapyon still has (§5.1).
WARNS = 'a:\n  bar: "X"\nu: y"{a[\'bar\']}"\n'
CLEAN = 'a:\n  bar: "X"\nu: y"{a.bar}"\n'
BROKEN = "a: [1,\n"


def run(stage, text):
    return subprocess.run([sys.executable, "-m", "yapyon", stage],
                          input=text, capture_output=True, text=True)


@pytest.mark.parametrize("module", ["lexer", "parser"])
def test_a_shiran_is_shown_by_default(module):
    done = run(module, WARNS)
    assert "shiran:" in done.stderr
    assert "the long way to write .bar" in done.stderr


@pytest.mark.parametrize("module", ["lexer", "parser"])
def test_a_shiran_does_not_reach_stdout(module):
    # stdout is the payload -- for `record` it is yapyon meant to be
    # redirected into a file, and a diagnostic there would corrupt it.
    done = run(module, WARNS)
    assert "shiran:" not in done.stdout


@pytest.mark.parametrize("module", ["lexer", "parser"])
def test_a_shiran_does_not_change_the_exit_status(module):
    # legal but suspicious: a pipeline must not break because of one
    assert run(module, WARNS).returncode == 0
    assert run(module, CLEAN).returncode == 0


@pytest.mark.parametrize("module", ["lexer", "parser"])
def test_nothing_is_printed_when_there_is_nothing_to_warn_about(module):
    assert run(module, CLEAN).stderr == ""


@pytest.mark.parametrize("module", ["lexer", "parser", "record"])
def test_an_akan_goes_to_stderr_and_fails(module):
    done = run(module, BROKEN)
    assert done.returncode == 1
    assert done.stderr.startswith("akan:")
    assert done.stdout == ""


def test_the_record_cli_writes_yapyon_to_stdout_and_nothing_else():
    done = run("record", 'a: "x"\nb: 3.10\n')
    assert done.returncode == 0
    assert done.stdout == 'a: "x"\nb: 3.10\n'
    assert done.stderr == ""


def test_an_unknown_stage_is_refused():
    done = run("nonsense", "")
    assert done.returncode == 2
    assert "no such stage" in done.stderr


@pytest.mark.parametrize("module", ["lexer", "parser", "record"])
def test_the_per_module_spelling_still_works(module):
    # `python -m yapyon.lexer` re-executes an already-imported module, which
    # once gave the stage a second AkanError class that `_cli` could not
    # catch -- the akan escaped as a traceback. It must not regress.
    done = subprocess.run([sys.executable, "-m", f"yapyon.{module}"],
                          input=BROKEN, capture_output=True, text=True)
    assert done.returncode == 1
    assert "akan: line 2, col 0: unclosed bracket" in done.stderr
    assert "Traceback" not in done.stderr
