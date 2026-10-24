"""The environment (SPEC §5.1.3, §5.1.4) — one test per rule, named after it.

Every test passes `env=` explicitly, so none depends on the machine running
it (trap 12): the rules are about the lookup, not about this host.
"""

import re
from pathlib import Path

import pytest

import yapyon
from yapyon import (ENV_ALL, POSIX_STANDARD_ENV, STANDARD_ENV,
                    WINDOWS_STANDARD_ENV, AkanError, expand_record, loads,
                    lookup)
from yapyon.environment import Environment

SPEC = Path(__file__).resolve().parent.parent / "docs" / "SPEC.md"
HOME = {"HOME": "/home/ana"}


def akan_of(text, **kw):
    with pytest.raises(AkanError) as e:
        loads(text, **kw)
    return str(e.value)


# --------------------------------------------------------------------------- #
# {$NAME} is strict; __env__ falls back
# --------------------------------------------------------------------------- #
def test_a_dollar_reference_splices_the_variable():
    assert loads('h: y"{$HOME}/x"\n', env=HOME) == {"h": "/home/ana/x"}


def test_a_dollar_reference_to_an_unset_variable_is_akan():
    assert "$HOME is not set, or not exposed" in akan_of('h: y"{$HOME}"\n',
                                                          env={})


def test_env_returns_the_variable_when_it_is_set():
    assert loads('h: y"{__env__(\'HOME\', \'/\')}"\n', env=HOME)["h"] \
        == "/home/ana"


def test_env_returns_the_fallback_when_it_is_unset():
    assert loads('h: y"{__env__(\'HOME\', \'/\')}"\n', env={})["h"] == "/"


def test_env_with_one_argument_returns_none_which_splices_as_none():
    # as f"{os.getenv('X')}" does; the author asked for it
    assert loads('h: y"{__env__(\'HOME\')}/x"\n', env={})["h"] == "None/x"


def test_the_fallback_may_be_given_by_keyword():
    assert loads('h: y"{__env__(\'HOME\', fallback=\'/\')}"\n',
                 env={})["h"] == "/"


def test_the_fallback_may_be_a_reference():
    doc = 'd: "/tmp"\nh: y"{__env__(\'HOME\', d)}"\n'
    assert loads(doc, env={})["h"] == "/tmp"


def test_the_fallback_is_resolved_even_when_it_is_not_used():
    # like any argument (§13.1), and like os.getenv's default
    doc = 'h: y"{__env__(\'XDG_CONFIG_HOME\', d)}"\nd: y"{$HOME}/.config"\n'
    assert "$HOME is not set" in akan_of(doc, env={"XDG_CONFIG_HOME": "/c"})


def test_the_variable_name_may_be_a_reference():
    doc = 'n: "HOME"\nh: y"{__env__(n)}"\n'
    assert loads(doc, env=HOME)["h"] == "/home/ana"


def test_the_variable_name_must_be_a_string():
    assert "var_name takes str, not int" in akan_of(
        'h: y"{__env__(1)}"\n', env=HOME)


def test_env_reaches_a_name_dollar_cannot_spell():
    env = {"ProgramFiles(x86)": "C:\\PF86"}
    doc = 'p: y"{__env__(\'ProgramFiles(x86)\')}"\n'
    assert loads(doc, env=env, env_allow=ENV_ALL)["p"] == "C:\\PF86"


@pytest.mark.parametrize("call,why", [
    ("__env__()", "takes a variable name and an optional fallback, not 0"),
    ("__env__('A', 'b', 'c')", "not 3 arguments"),
    ("__env__('A', bogus=1)", "has no keyword argument bogus"),
    ("__env__('A', 'b', fallback='c')", "by position and again by keyword"),
])
def test_env_checks_its_shape(call, why):
    assert why in akan_of(f'h: y"{{{call}}}"\n', env={})


# --------------------------------------------------------------------------- #
# What the lookup sees
# --------------------------------------------------------------------------- #
def test_an_empty_value_is_a_value_not_unset():
    assert loads('h: y"[{$HOME}]"\n', env={"HOME": ""})["h"] == "[]"
    assert loads('h: y"{__env__(\'HOME\', \'/\')}"\n',
                 env={"HOME": ""})["h"] == ""


def test_a_variable_not_exposed_is_indistinguishable_from_an_unset_one():
    env = {"API_KEY": "s3cret"}
    assert "$API_KEY is not set, or not exposed" in akan_of(
        'k: y"{$API_KEY}"\n', env=env)
    assert loads('k: y"{__env__(\'API_KEY\', \'-\')}"\n', env=env)["k"] == "-"


def test_env_allow_widens_the_standard_set():
    assert loads('k: y"{$API_KEY}"\n', env={"API_KEY": "s3cret"},
                 env_allow=STANDARD_ENV | {"API_KEY"}) == {"k": "s3cret"}


def test_env_allow_can_narrow_it():
    assert "not set, or not exposed" in akan_of(
        'h: y"{$HOME}"\n', env=HOME, env_allow=set())


def test_env_all_exposes_everything():
    assert loads('k: y"{$API_KEY}"\n', env={"API_KEY": "s3cret"},
                 env_allow=ENV_ALL) == {"k": "s3cret"}


def test_access_off_is_akan_for_both_forms_even_with_a_fallback():
    # a fallback answers "not set", never "not allowed"
    for doc in ('h: y"{$HOME}"\n', 'h: y"{__env__(\'HOME\', \'/\')}"\n'):
        assert "environment access is off" in akan_of(doc, env=None)


def test_a_value_that_is_not_unicode_text_is_akan():
    # POSIX holds bytes; Python decodes undecodable ones to lone surrogates
    assert "not valid Unicode text" in akan_of(
        'h: y"{$HOME}"\n', env={"HOME": "/home/\udcff"})


def test_names_compare_exactly_on_posix():
    env = Environment({"HOME": "/h"}, POSIX_STANDARD_ENV, windows=False)
    assert env.get("HOME") == "/h"
    assert env.get("home") is None


def test_names_ignore_case_on_windows_for_exposure_and_lookup_alike():
    env = Environment({"Path": "C:\\bin", "appdata": "C:\\a"},
                      {"PATH", "APPDATA"}, windows=True)
    assert env.get("PATH") == "C:\\bin"
    assert env.get("AppData") == "C:\\a"


def test_the_environment_is_read_once_per_load():
    source = {"HOME": "/before"}
    env = Environment(source, ENV_ALL, windows=False)
    source["HOME"] = "/after"
    assert env.get("HOME") == "/before"


def test_the_default_environment_is_the_process_s_own(monkeypatch):
    monkeypatch.setenv("HOME", "/from/process")
    assert loads('h: y"{$HOME}"\n') == {"h": "/from/process"}


@pytest.mark.parametrize("kw", [
    {"env": {"HOME": 1}},
    {"env": {1: "x"}},
    {"env_allow": "HOME"},
    {"env_allow": {1}},
])
def test_bad_arguments_are_type_errors_at_the_call(kw):
    with pytest.raises(TypeError):
        loads('a: 1\n', **{"env": HOME, **kw})


# --------------------------------------------------------------------------- #
# Where the value goes: the ordinary rules
# --------------------------------------------------------------------------- #
def test_splicing_cannot_inject_structure():
    hostile = '"\nevil: True\n'
    assert loads('h: y"{$HOME}"\n', env={"HOME": hostile}) == {"h": hostile}


def test_a_call_may_follow_a_dollar_reference():
    assert loads('j: y"{$HOME.__as_json__()}"\n',
                 env={"HOME": 'a"b'})["j"] == '"a\\"b"'


def test_a_dollar_reference_may_be_an_argument():
    assert loads('j: y"{__as_json__($HOME)}"\n', env=HOME)["j"] \
        == '"/home/ana"'


def test_a_dollar_reference_keys_a_mapping_in_a_bracket():
    doc = 'shells:\n  ana: "zsh"\n  bo: "fish"\ns: y"{shells[$LOGNAME]}"\n'
    assert loads(doc, env={"LOGNAME": "bo"})["s"] == "fish"


def test_a_dollar_reference_cannot_index_a_list():
    doc = 'xs: [1, 2]\nv: y"{xs[$LOGNAME]}"\n'
    assert "akan" in akan_of(doc, env={"LOGNAME": "0"})


def test_text_from_the_environment_does_not_splice_into_bytes():
    assert "cannot splice text into a byte string" in akan_of(
        'b: yb"{$HOME}"\n', env=HOME)


def test_a_yt_part_reads_dollar_name():
    t = loads('t: yt"cd {$HOME}"\n', env=HOME)["t"]
    hole = list(t)[1]
    assert (hole.ref, hole.value) == ("$HOME", "/home/ana")


def test_a_step_after_a_dollar_reference_is_refused_by_the_grammar():
    for doc in ('h: y"{$HOME.x}"\n', 'h: y"{$HOME[0]}"\n'):
        assert "has no keys or positions" in akan_of(doc, env=HOME)


def test_a_dollar_outside_a_hole_is_text():
    assert loads('HOME: "h"\np: y"${HOME}"\n', env=HOME) == {
        "HOME": "h", "p": "$h"}


# --------------------------------------------------------------------------- #
# The other entry points
# --------------------------------------------------------------------------- #
def test_expand_record_writes_the_values_it_read():
    assert expand_record('h: y"{$HOME}"\n', env=HOME) == 'h: "/home/ana"\n'


def test_lookup_takes_an_environment_too():
    tree = loads('a:\n  b: 1\n')
    assert lookup(tree, tree["a"], "$HOME", env=HOME) == "/home/ana"


def test_the_names_are_exported():
    for name in ("STANDARD_ENV", "POSIX_STANDARD_ENV",
                 "WINDOWS_STANDARD_ENV", "ENV_ALL"):
        assert name in yapyon.__all__


# --------------------------------------------------------------------------- #
# The standard sets against SPEC §5.1.4's table
# --------------------------------------------------------------------------- #
def _spec_table():
    """SPEC §5.1.4's best-practice table, read from the document — the
    other side of the comparison, so it must not come from the code."""
    rows = {}
    inside = False
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            inside = line.startswith("### 5.1.4 ")
            continue
        m = re.match(r"^\| (POSIX|Windows)-compatible \| (.*) \|$", line)
        if inside and m:
            rows[m.group(1)] = frozenset(re.findall(r"`([^`]+)`", m.group(2)))
    return rows


def test_the_posix_set_is_spec_s_table():
    assert POSIX_STANDARD_ENV == _spec_table()["POSIX"]


def test_the_windows_set_is_spec_s_table():
    assert WINDOWS_STANDARD_ENV == _spec_table()["Windows"]


def test_standard_env_is_this_system_s_set():
    assert STANDARD_ENV in (POSIX_STANDARD_ENV, WINDOWS_STANDARD_ENV)


# --------------------------------------------------------------------------- #
# The CLI
# --------------------------------------------------------------------------- #
def _expand_cli(args, env, text):
    import subprocess, sys, os
    return subprocess.run([sys.executable, "-m", "yapyon", "expand", *args],
                          input=text, capture_output=True, text=True,
                          env={**{k: v for k, v in os.environ.items()
                                  if k in ("PATH", "PYTHONPATH")}, **env})


def test_the_cli_reads_standard_variables_by_default():
    done = _expand_cli([], {"HOME": "/h"}, 'h: y"{$HOME}"\n')
    assert done.stdout == 'h: "/h"\n'


def test_the_cli_env_allow_exposes_one_more_name():
    doc = 'k: y"{__env__(\'API_KEY\', \'-\')}"\n'
    assert _expand_cli([], {"API_KEY": "s"}, doc).stdout == 'k: "-"\n'
    assert _expand_cli(["--env-allow", "API_KEY"], {"API_KEY": "s"},
                       doc).stdout == 'k: "s"\n'
    assert _expand_cli(["--env-all"], {"API_KEY": "s"}, doc).stdout \
        == 'k: "s"\n'


def test_the_cli_no_env_turns_access_off():
    done = _expand_cli(["--no-env"], {"HOME": "/h"}, 'h: y"{$HOME}"\n')
    assert "environment access is off" in done.stderr
    assert done.returncode == 1


def test_the_cli_refuses_an_unknown_option():
    done = _expand_cli(["--bogus"], {}, 'a: 1\n')
    assert "unknown option --bogus" in done.stderr
    assert done.returncode == 2
