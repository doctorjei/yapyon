"""Diagnostics tests — the register, and where an akan says it happened.

SPEC §10. One test per rule, named after the rule. When a test and the
implementation disagree, check the spec before changing either.
"""

import io

import pytest

from yapyon import (AkanError, is_record, load, load_record, loads,
                    loads_record)


def akan_of(text, **kw):
    with pytest.raises(AkanError) as e:
        loads(text, **kw)
    return e.value


# --------------------------------------------------------------------------- #
# Source labels — naming the file an akan came from
# --------------------------------------------------------------------------- #
def test_without_a_source_the_wording_is_unchanged():
    # the old form is what every existing caller reads; adding the feature
    # must not move it
    e = akan_of("a: no\n")
    assert str(e).startswith("akan: line 1, col 3: ")
    assert e.source is None


def test_a_source_switches_to_the_file_line_col_form():
    e = akan_of("a: no\n", source="dialect.default.ypn")
    assert str(e).startswith("akan: dialect.default.ypn:1:3: ")
    assert e.source == "dialect.default.ypn"


def test_the_position_is_the_same_either_way():
    bare, named = akan_of("a: no\n"), akan_of("a: no\n", source="x.ypn")
    assert (bare.line, bare.col) == (named.line, named.col) == (1, 3)


def test_every_stage_carries_the_source():
    # lexer, parser, resolver, and the record filter each raise their own
    assert akan_of('a: f"x"\n', source="s").source == "s"          # lexer
    assert akan_of("a: no\n", source="s").source == "s"            # parser
    assert akan_of('a: y"{nope}"\n', source="s").source == "s"     # resolver
    with pytest.raises(AkanError) as e:
        loads_record('a: y"x"\n', source="s")                      # record
    assert e.value.source == "s"


def test_a_template_keeps_its_source_past_the_document():
    # the document is long gone by fill time; the label is the only way back
    t = loads('t: yt"{x}"\n', source="tpl.ypn")["t"]
    with pytest.raises(AkanError) as e:
        t.fill(other=1)
    assert str(e.value).startswith("akan: tpl.ypn:1:3: ")


def test_a_shiran_carries_the_source_too():
    # vehicle: the avoidable-bracket shiran (shadowing no longer warns)
    seen = []
    loads('a:\n  bar: "X"\nu: y"{a[\'bar\']}"\n', warn=seen.append,
          source="sh.ypn")
    assert seen[0].startswith("shiran: sh.ypn:3:5: ")


def test_is_record_names_the_source_when_the_text_will_not_lex():
    with pytest.raises(AkanError) as e:
        is_record('a: f"x"\n', source="probe.ypn")
    assert e.value.source == "probe.ypn"


def test_load_defaults_the_source_to_the_file_name(tmp_path):
    p = tmp_path / "gateway.ypy"
    p.write_text("a: no\n")
    with p.open() as fp, pytest.raises(AkanError) as e:
        load(fp)
    assert e.value.source == str(p)


def test_load_record_defaults_the_source_to_the_file_name(tmp_path):
    p = tmp_path / "rec.ypy"
    p.write_text('a: y"x"\n')
    with p.open() as fp, pytest.raises(AkanError) as e:
        load_record(fp)
    assert e.value.source == str(p)


def test_an_explicit_source_beats_the_file_name(tmp_path):
    p = tmp_path / "on-disk.ypy"
    p.write_text("a: no\n")
    with p.open() as fp, pytest.raises(AkanError) as e:
        load(fp, source="what-the-caller-calls-it")
    assert e.value.source == "what-the-caller-calls-it"


def test_a_nameless_stream_stays_unlabelled():
    # StringIO has no .name, which is why this is not just fp.name
    with pytest.raises(AkanError) as e:
        load(io.StringIO("a: no\n"))
    assert e.value.source is None


# --------------------------------------------------------------------------- #
# Hints are earned, not automatic
# --------------------------------------------------------------------------- #
def test_the_quantifier_hint_fires_only_on_quantifier_shaped_content():
    assert "doubled braces" in str(akan_of('a: y"{2,3}"\n'))
    assert "doubled braces" in str(akan_of('a: y"{3}"\n'))


def test_the_quantifier_hint_does_not_fire_on_everything_else():
    # it used to be appended to every non-identifier hole, which told an
    # author about regex when they had written something else entirely
    for src in ('a: y"{$HOME}"\n', 'a: y"{a-b}"\n', 'a: y"{a b}"\n'):
        assert "doubled braces" not in str(akan_of(src)), src


def test_a_dollar_segment_gets_the_environment_hint():
    e = akan_of('a: y"{$HOME}"\n')
    assert "'$HOME' is not an identifier" in str(e)
    assert "yapyon does not expand them" in str(e)


def test_an_unresolved_hole_after_a_dollar_gets_the_hint():
    # y"${HOME}" is a literal $ plus the hole {HOME}; the akan is right and
    # only the wording needed work
    e = akan_of('a: y"${HOME}"\n')
    assert "no value named 'HOME' is in scope here" in str(e)
    assert "yapyon does not expand them" in str(e)


def test_the_hint_says_after_loading_not_pre_process():
    # the pre-parse text pass is the injection-prone path
    assert "do that after loading" in str(akan_of('a: y"${HOME}"\n'))


def test_an_unresolved_hole_with_no_dollar_gets_no_hint():
    assert "environment variable" not in str(akan_of('a: y"{nope}"\n'))


def test_the_hint_is_hedged_and_never_changes_the_outcome():
    # $ is an ordinary character: a resolving ${VAR} is a real idiom (build
    # "$NEW_VAR" for something downstream) and must stay silent
    seen = []
    assert loads('HOME: "h"\np: y"${HOME}"\n', warn=seen.append) == {
        "HOME": "h", "p": "$h"}
    assert seen == []


def test_a_dollar_further_away_does_not_trigger_the_hint():
    assert "environment variable" not in str(akan_of('a: y"$ {nope}"\n'))


def test_a_dotted_reference_after_a_dollar_still_gets_the_hint():
    assert "environment variable" in str(akan_of('a: y"${HOME.sub}"\n'))


def test_merged_fragments_can_each_name_themselves():
    # the case the feature exists for: several fragments parsed separately,
    # where a bare line and column points into nothing identifiable
    from yapyon import parse
    parse('a: "x"\n', source="base.ypn")
    with pytest.raises(AkanError) as e:
        parse("b: no\n", source="override.ypn")
    assert str(e.value).startswith("akan: override.ypn:1:3: ")
