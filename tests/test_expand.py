"""`expand_record` / `python -m yapyon expand` — the bridge down to a record.

The contract is a property, not a case list:

    loads_record(expand_record(s)) == loads(s)

Everything else here is either the one thing that cannot cross (a `yt`) or
proof that the new path reaches every outcome the resolver already defines
(trap 9: `_serialize` joined the fixpoint but could not report a cycle, and
shipped saying the wrong thing about the wrong node).
"""

import subprocess
import sys

import pytest

import yapyon
from yapyon import (AkanError, expand_record, is_record, loads, loads_record,
                   tier_of)
from yapyon.expand import _expand

# A corpus wide enough that the property is evidence, not a coincidence.
CORPUS = [
    'a: "x"\nb: 3.10\n',
    'name: "gw"\nbanner: y"{name} v1"\n',
    'version: 3.10\nline: y"v{version}"\n',
    'a: "A"\nb: y"{a}B"\nc: y"{b}C"\n',
    'cfg:\n  a: 1\n  b: "x"\njs: y"{cfg.__AS_JSON__()}"\n',
    'm:\n  + a: 1\n  + a: 2\nfirst: y"{m.a[1]}"\n',
    'n: 8080\nu: y"http://host:{n}/api"\n',
    'a:\n  - "x"\n  - "q"\nsecond: y"{a[1]}y"\n',
    'x: b"raw"\nl:\n  - 1\n  - 2\nn: y"{l.__AS_YAML__()}"\n',
    'a: "1"\nb: "2"\nc: y"{a}{b}{a}"\n',
]


def run(stage_args, text):
    return subprocess.run([sys.executable, "-m", "yapyon", *stage_args],
                         input=text, capture_output=True, text=True)


# --------------------------------------------------------------------------- #
# The property
# --------------------------------------------------------------------------- #
def test_the_expanded_record_loads_to_what_the_full_document_means():
    for src in CORPUS:
        assert loads_record(expand_record(src)) == loads(src), src


def test_the_expanded_output_is_always_a_record():
    # The point of the bridge: the output must be loadable with no resolver.
    for src in CORPUS:
        assert is_record(expand_record(src)), src


def test_expanding_a_record_is_normalizing_it():
    # A document with nothing to resolve still works: expand degenerates to
    # what `record` does, rather than erroring on having no work to do.
    src = 'a: "x"\nb: 3.10\n'
    assert loads_record(expand_record(src)) == loads_record(src)


def test_expansion_is_stable_under_a_second_pass():
    # Expanding a record again must not drift.
    for src in CORPUS:
        once = expand_record(src)
        assert expand_record(once) == once, src


def test_the_bridge_lands_where_it_claims_to_land():
    # The two 0.2.0 items checked against each other: what the bridge
    # produces is level 1. If expand ever emitted something that still
    # needed a resolver, this is what says so.
    for src in CORPUS:
        assert tier_of(expand_record(src)) == 1, src


def test_a_full_document_enters_at_level_2_and_a_record_passes_through():
    # The corpus deliberately includes one already-record document, which
    # enters at level 1 and expands to itself; everything else is level 2.
    assert tier_of('a: "x"\nb: 3.10\n') == 1
    for src in CORPUS[1:]:
        assert tier_of(src) == 2, src


# --------------------------------------------------------------------------- #
# Spelling survives the crossing
# --------------------------------------------------------------------------- #
def test_an_unspliced_number_keeps_its_source_lexeme():
    # The whole reason the emitter reads the AST: 3.10 is not 3.1.
    assert "3.10" in expand_record('version: 3.10\nline: y"v{version}"\n')
    assert loads_record(expand_record('version: 3.10\n'))["version"] == 3.1


def test_a_spliced_number_splices_its_lexeme_not_its_repr():
    out = expand_record('version: 3.10\nline: y"v{version}"\n')
    assert loads_record(out)["line"] == "v3.10"


def test_bytes_keep_their_spelling_across_the_bridge():
    out = expand_record('x: b"raw"\n')
    assert 'b"raw"' in out
    assert "b64" not in out


# --------------------------------------------------------------------------- #
# The one thing that cannot cross: a yt
# --------------------------------------------------------------------------- #
def test_a_yt_is_refused_because_a_record_has_no_template_form():
    with pytest.raises(AkanError) as e:
        expand_record('y: "z"\nt: yt"x {y}"\n')
    assert "no record form" in str(e.value)


def test_the_yt_refusal_names_the_fix():
    with pytest.raises(AkanError) as e:
        expand_record('y: "z"\nt: yt"x {y}"\n')
    assert 'write y"..."' in str(e.value)


def test_the_yt_refusal_points_at_the_yt():
    with pytest.raises(AkanError) as e:
        expand_record('y: "z"\nt: yt"x {y}"\n')
    assert e.value.line == 2


def test_joining_would_be_the_wrong_answer_and_is_not_offered():
    # If expand joined a yt, `t` would come back as a plain string and the
    # document would silently mean `y` instead. Assert the refusal rather
    # than trusting the absence of a join.
    src = 'y: "z"\nt: yt"x {y}"\n'
    with pytest.raises(AkanError):
        expand_record(src)
    # ...and the same document with `y` does cross, so the refusal is about
    # the template, not about splicing.
    assert loads_record(expand_record('y: "z"\nt: y"x {y}"\n'))["t"] == "x z"


def test_the_yt_refusal_precedes_resolution():
    # A document that has a yt AND would not resolve reports the yt: that
    # is what blocks *this* operation, and it is reported without doing the
    # work that cannot finish.
    src = 'a: y"{b}"\nb: y"{a}"\nt: yt"{a}"\n'
    with pytest.raises(AkanError) as e:
        expand_record(src)
    assert "no record form" in str(e.value)


# --------------------------------------------------------------------------- #
# Trap 9: every outcome the resolver defines is reachable through this path
# --------------------------------------------------------------------------- #
def test_a_cycle_is_still_reported_as_a_cycle():
    with pytest.raises(AkanError) as e:
        expand_record('a: y"{b}"\nb: y"{a}"\n')
    assert "cycle" in str(e.value)


def test_a_missing_name_is_still_reported_as_missing():
    with pytest.raises(AkanError) as e:
        expand_record('a: y"{nope}"\n')
    assert "nope" in str(e.value)


def test_the_depth_ceiling_is_reachable_through_expand():
    src = 'a0: "x"\n' + "".join(
        f'a{i}: y"{{a{i - 1}}}"\n' for i in range(1, 8))
    # Comfortably under the default ceiling.
    assert loads_record(expand_record(src))["a7"] == "x"
    with pytest.raises(AkanError) as e:
        expand_record(src, max_depth=3)
    assert "depth" in str(e.value)


def test_the_size_ceiling_is_reachable_through_expand():
    src = 'a0: "xxxxx"\n' + "".join(
        f'a{i}: y"{{a{i - 1}}}{{a{i - 1}}}"\n' for i in range(1, 6))
    with pytest.raises(AkanError) as e:
        expand_record(src, max_size=20)
    assert "size" in str(e.value)


def test_a_shiran_passes_through_without_changing_the_result():
    # GRAMMAR §G5.4's avoidable bracket: legal, worth saying, changes nothing.
    src = 'a:\n  bar: "X"\nu: y"{a[\'bar\']}"\n'
    text, shirans = _expand(src)
    assert any("shiran" in m for m in shirans)
    assert loads_record(text)["u"] == "X"


def test_a_shiran_reaches_the_callers_warn_channel_as_it_happens():
    # Reported as it happens, not batched at the end, so a later akan cannot
    # swallow an earlier warning.
    seen = []
    _expand('a:\n  bar: "X"\nu: y"{a[\'bar\']}"\n', warn=seen.append)
    assert any("shiran" in m for m in seen)


def test_the_bridged_example_is_the_one_the_readme_shows():
    # The README shows `expand examples/bridge.ypy` as the demo, so the
    # example has to actually cross. gateway.ypy carries a `yt` and cannot;
    # registry.ypy starts as a record, so expanding it proves nothing.
    from pathlib import Path
    example = Path(__file__).resolve().parent.parent / "examples" / "bridge.ypy"
    src = example.read_text(encoding="utf-8")
    assert tier_of(src) == 2
    out = expand_record(src)
    assert tier_of(out) == 1
    assert loads_record(out) == loads(src)
    # And the spelling the README's comment promises: 3.10, not 3.1.
    assert "3.10" in out


# --------------------------------------------------------------------------- #
# The CLI
# --------------------------------------------------------------------------- #
def test_the_cli_writes_the_record_to_stdout():
    done = run(["expand"], 'name: "gw"\nbanner: y"{name} v1"\n')
    assert done.returncode == 0
    assert 'banner: "gw v1"' in done.stdout


def test_the_cli_sends_an_akan_to_stderr_not_stdout():
    done = run(["expand"], 'a: y"{missing}"\n')
    assert done.stdout == ""
    assert "akan" in done.stderr
    assert done.returncode == 1


def test_the_cli_shows_a_shiran_without_failing():
    done = run(["expand"], 'a:\n  bar: "X"\nu: y"{a[\'bar\']}"\n')
    assert "shiran" in done.stderr
    assert "shiran" not in done.stdout
    assert done.returncode == 0


def test_the_cli_refuses_a_yt_on_stderr():
    done = run(["expand"], 'y: "z"\nt: yt"x {y}"\n')
    assert done.stdout == ""
    assert "no record form" in done.stderr
    assert done.returncode == 1


# --------------------------------------------------------------------------- #
# The export is not shadowed by the module of the same name
# --------------------------------------------------------------------------- #
def test_expand_record_is_the_public_name_and_the_module_does_not_shadow_it():
    assert yapyon.expand_record is not None
    assert "expand_record" in yapyon.__all__
    from yapyon.expand import expand_record as f
    assert f is yapyon.expand_record
