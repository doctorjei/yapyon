"""SPEC §15.8: saving is structural, and continuation preserves meaning."""

import itertools
import json
import re
from pathlib import Path

import pytest

import yapyon
from yapyon import AkanError, merge, parse
from yapyon._source import _could_match
from yapyon.parser import YString


@pytest.mark.parametrize("text", [
    '42', '[]', '{}', '{+}', '(42)',
    'a: 3.10\nb: 0xff\ns: r"a\\nb"\n',
    'name: "x"\ns: y"{name}"\nr: ry"{name}\\n"\n',
    'value: b"hi"\ns: yb"{value}"\n',
    'name: "x"\ns: yt"hello {name}"\n',
    'name: "x"\nc: (name)\nf: __str__(12)\n',
    'value: None\ns: value?.__str__()\n',
    'name: "x"\ndata: {y"{name}": 1}\n',
    'name: "x"\ndata: {ry"{name}": 1}\n',
    'data: {"name": 1, "ｎａｍｅ": 2}\n',
    'name: "x"\nxs: [y"{name}", (name), __str__(12)]\n',
    'name: "x"\nm:\n  + y"{name}": 1\n  + y"{name}": 2\n',
    'name: "x"\ns: y"""hello\n    {name}\n    """\n',
    'name: "x"\nxs:\n  - s: y"""hello\n        {name}"""\n',
    'name: "x"\ny"""key\n    {name}""": 1\n',
    'name: "x"\nc: (\n  name\n)\n',
])
def test_unresolved_source_preserves_eventual_values_and_is_idempotent(text):
    tree = parse(text)
    saved = tree.to_source()
    restored = parse(saved)
    assert saved.endswith('\n')
    assert restored.to_source() == saved
    assert restored.resolve() == tree.resolve()


@pytest.mark.parametrize("text", [
    'agent<chosen.agent>: {}',
    'agent < chosen . agent >: {harness<>: {timeout: 30}}',
    'name: "x"\ny"{name}"<chosen>: {nested<other>: {}}',
    '"quoted"<chosen>: {}',
    'xs: [{part<chosen>: {name: "x"}}]',
    '"""multi\n    line"""<chosen>: {}',
    'agent<chosen>: {desc: y"{missing}", c: (missing), call: RUN(missing)}',
])
def test_slots_and_their_nested_overrides_stay_unfinished(text):
    tree = parse(text)
    saved = tree.to_source()
    restored = parse(saved)
    assert restored.to_source() == saved
    assert [(s.label, s.abstract) for s in restored.slots()] == [
        (s.label, s.abstract) for s in tree.slots()]
    with pytest.raises(AkanError, match='unfilled|abstract slot'):
        restored.resolve()


def test_selective_composition_can_be_saved_and_continued():
    tree = parse('name: "agent"\npart<base.part>: {timeout: 30}\n')
    base = parse('part:\n  name: "part"\n  desc: y"{name}"\n  harness<chosen>: {}\n')
    tree['part'].fill(base)
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        candidate['part']['harness'].fill(parse('desc: y"{__PARENT__.__PARENT__.name}"'))
        candidate['part']['name'].replace(parse('"changed"'))
        candidate['part']['timeout'].remove()
        candidate.merge(parse('extra: (part.desc)'))
    assert restored.resolve() == tree.resolve()
    assert restored.resolve()['part']['desc'] == 'changed'


def test_moved_slots_keep_layered_overrides_and_can_be_filled_later():
    tree = parse('part<base.part>: {nested: {outer: 3, x: 3}}')
    tree['part'].fill(parse('part<middle>: {nested: {inner: 2, x: 2}}'))
    tree['part'].merge(parse('nested: {last: 4}'))
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        candidate['part'].fill(parse('nested: {first: 1, x: 1}'))
    assert restored.resolve() == tree.resolve() == {
        'part': {'nested': {'first': 1, 'x': 3, 'inner': 2, 'outer': 3, 'last': 4}}}


def test_explicitly_passed_on_abstract_slots_survive():
    tree = parse('part<base>: {harness<>: {outer: 2}}')
    tree['part'].fill(parse('harness<>: {inner: 1}'))
    restored = parse(tree.to_source())
    assert restored['part']['harness'].abstract
    for candidate in (tree, restored):
        candidate['part']['harness'].fill(parse('value: 3'))
    assert restored.resolve() == tree.resolve()


@pytest.mark.parametrize('reverse', [False, True])
def test_empty_dictionary_cannot_conflict_with_computed_keys(reverse):
    layers = [parse('{}'), parse('y"{$HOME}": 1')]
    if reverse:
        layers.reverse()
    tree = merge(*layers)
    restored = parse(tree.to_source())
    assert 'y"{$HOME}"' in tree.to_source()
    assert restored.resolve(env={'HOME': 'x'}) == tree.resolve(env={'HOME': 'x'})


@pytest.mark.parametrize('left,right', [
    ('y"{name}": 1', 'x: 2'),
    ('x: 1', 'y"{name}": 2'),
    ('y"{name}": 1', '"x": 2'),
    ('y"{name}": 1', 'y"{alias}": 2'),
    ('y"prefix_{name}": 1', 'prefix_x: 2'),
    ('y"a{name}z": 1', 'y"{alias}z": 2'),
    ('y"a{name}": 1', 'y"{alias}b": 2'),
    ('y"x": 1', 'x: 2'),
    ('ry"{name}": 1', 'x: 2'),
])
def test_potential_cross_layer_key_matches_are_akan_only_on_saving(left, right):
    tree = merge(parse(left, source='base.yap'), parse(right, source='over.yap'))
    with pytest.raises(AkanError, match='cannot save this dictionary merge') as err:
        tree.to_source()
    assert err.value.source in {'base.yap', 'over.yap'}
    assert 'another layer' in str(err.value)
    assert len(tree.keys()) >= 1


def test_refused_source_does_not_change_successful_in_memory_resolution():
    tree = merge(parse('name: "x"\ndata: {y"{name}": {a: 1}}'),
                 parse('data: {y"x": {b: 2}}'))
    expected = {'name': 'x', 'data': {'x': {'a': 1, 'b': 2}}}
    assert tree.resolve() == expected
    with pytest.raises(AkanError, match='could match'):
        tree.to_source()
    assert tree.resolve() == expected


@pytest.mark.parametrize('left,right', [
    ('y"left_{name}": 1', 'right: 2'),
    ('left: 1', 'y"right_{name}": 2'),
    ('y"left_{name}": 1', 'y"right_{name}": 2'),
    ('y"{name}_left": 1', 'y"{name}_right": 2'),
    ('y"a{name}b": 1', 'y"a{alias}c": 2'),
    ('y"exact": 1', 'different: 2'),
    ('y"[?]": 1', 'y"other": 2'),
    ('y"a\\nb": 1', '"ab": 2'),
])
def test_literal_text_can_prove_computed_keys_disjoint_without_evaluating(left, right):
    tree = merge(parse('name: "x"\nalias: "x"\n' + left), parse(right))
    restored = parse(tree.to_source())
    assert restored.resolve() == tree.resolve()


def test_checks_are_local_to_the_dictionary_being_merged():
    tree = merge(parse('name: "x"\na: {y"{name}": 1}'),
                 parse('b: {x: 2}\na: {}'))
    assert parse(tree.to_source()).resolve() == tree.resolve()


def test_a_nested_conflict_is_refused_at_its_computed_key():
    tree = merge(parse('data:\n  y"{name}": 1\n', source='base.yap'),
                 parse('data: {x: 2}'))
    with pytest.raises(AkanError, match='could match') as err:
        tree.to_source()
    assert (err.value.source, err.value.line, err.value.col) == ('base.yap', 2, 2)


def test_computed_keys_in_replaced_dictionaries_do_not_prevent_saving():
    tree = merge(parse('data: {y"{missing}": 1}'), parse('data: None'))
    assert tree.to_source() == 'data: None\n'


def test_same_source_computed_duplicates_are_not_a_cross_layer_refusal():
    tree = merge(parse('y"x": 1\ny"x": 2'), parse('{}'))
    saved = tree.to_source()
    for candidate in (tree, parse(saved)):
        with pytest.raises(AkanError, match='duplicate key'):
            candidate.resolve()


def test_first_key_kind_spelling_and_order_survive_known_merges():
    tree = merge(parse('"name": "first"\nｘ: {a: 1}\nz: 3'),
                 parse('name: "last"\nx: {b: 2}\nnew: 4'))
    restored = parse(tree.to_source())
    assert restored.keys() == ['name', 'x', 'z', 'new']
    assert restored['name'].key_lexeme() == '"name"'
    assert restored['x'].key_lexeme() == 'ｘ'
    assert restored.resolve() == tree.resolve()
    for candidate in (tree, restored):
        candidate.merge(parse('out: y"{name}"'))
        with pytest.raises(AkanError):
            candidate.resolve()


def test_layered_slot_overrides_use_the_same_conflict_check():
    tree = parse('part<base>: {y"{name}": 1}')
    tree['part'].merge(parse('x: 2'))
    with pytest.raises(AkanError, match='could match'):
        tree.to_source()


def test_disjoint_computed_slot_overrides_remain_deferred():
    tree = parse('name: "x"\npart<base>: {y"left_{name}": 1}')
    tree['part'].merge(parse('right: 2'))
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        candidate['part'].fill(parse('{}'))
    assert restored.resolve() == tree.resolve()


def test_unfilled_abstract_slot_is_not_a_completed_fill_obligation():
    tree = parse('part<>: {timeout: 30}')
    restored = parse(tree.to_source())
    assert restored['part'].abstract
    for candidate in (tree, restored):
        candidate['part'].fill(parse('value: 1'))
    assert restored.resolve() == tree.resolve()


def test_completed_fill_with_deferred_obligation_has_a_separate_save_refusal():
    tree = parse('part<base>: {other: 42}', source='user.yap')
    tree['part'].fill(parse('name: "x"\ny"need_{name}"<>: {}', source='base.yap'))
    with pytest.raises(AkanError, match='undecided abstract-slot obligation') as err:
        tree.to_source()
    assert err.value.source == 'user.yap'
    assert (err.value.line, err.value.col) == (1, 4)
    tree.merge(parse('part: {need_x: {done: True}}'))
    with pytest.raises(AkanError, match='overrides must give that key a value'):
        tree.resolve()


def test_native_record_emit_still_refuses_slots_and_expressions():
    for text in ('part<base>: {}', 'name: "x"\ndesc: y"{name}"'):
        tree = parse(text)
        assert parse(tree.to_source()).to_source() == tree.to_source()
        with pytest.raises(AkanError):
            yapyon.emit(tree)


def test_saving_does_not_mutate_handles_locations_or_diagnostics():
    tree = merge(parse('data: {y"left_{name}": 1}', source='first.yap'),
                 parse('data: {right: 2}', source='second.yap'))
    key = tree['data'].keys()[0]
    handle = tree['data'][key]
    before = (tree['data'].keys(), handle.where, handle.lexeme, tree.warnings[:])
    text = tree.to_source()
    assert tree.to_source() == text
    assert (tree['data'].keys(), handle.where, handle.lexeme, tree.warnings) == before
    handle.replace(parse('3'))
    assert handle.value == 3


def test_saving_performs_no_resolution_environment_lookup_or_serialization(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('source writing evaluated the document')

    tree = parse('home: y"{$HOME}"\ncall: RUN(home)\nout: home.__as_json__()\n'
                 'part<chosen>: {}\ny"key_{$HOME}": (home)')
    monkeypatch.setattr('yapyon.tree.resolve', forbidden)
    monkeypatch.setattr('yapyon.tree.environment', forbidden)
    monkeypatch.setattr('yapyon.resolver.resolve', forbidden)
    monkeypatch.setattr('yapyon.emitter.emit', forbidden)
    saved = tree.to_source()
    assert 'RUN(home)' in saved and 'y"key_{$HOME}"' in saved
    assert 'part<chosen>: {}' in saved
    assert parse(saved).to_source() == saved


def test_subsequent_resolution_reads_the_new_environment_and_contract():
    tree = parse('home: y"{$HOME}"\ncall: RUN(home)\npart<chosen>: {}')
    restored = parse(tree.to_source())
    contract = yapyon.loads_contract('''
RUN:
  params: {value: "str"}
  returns: "str"
  impl: {python: {symbol: "run"}}
''')
    calls = []

    def run(value):
        calls.append(value)
        return 'result:' + value

    for candidate in (tree, restored):
        candidate['part'].fill(parse('desc: y"{home}"'))
    for home in ('/first', '/second'):
        options = dict(env={'HOME': home}, contract=contract, provide={'run': run})
        assert restored.resolve(**options) == tree.resolve(**options)
    assert calls == ['/first', '/first', '/second', '/second']


def test_reloading_uses_saved_file_positions_but_original_keeps_its_source():
    tree = parse('# comment\n\nmissing: y"{unknown}"', source='old.yap')
    restored = parse(tree.to_source(), source='saved.yap')
    assert tree['missing'].where == ('old.yap', 3, 9)
    assert restored['missing'].where == ('saved.yap', 1, 9)
    for candidate, source in ((tree, 'old.yap'), (restored, 'saved.yap')):
        with pytest.raises(AkanError) as err:
            candidate.resolve()
        assert err.value.source == source


def _key(pattern):
    return YString(1, 0, 'y', [('hole', 'unknown') if ch == '*' else ('text', ch)
                               for ch in pattern])


def test_potential_match_checker_agrees_with_independent_finite_language_oracle():
    patterns = [''.join(chars) for n in range(4)
                for chars in itertools.product('ab*', repeat=n)]
    words = [''.join(chars) for n in range(7)
             for chars in itertools.product('ab', repeat=n)]
    languages = {p: {w for w in words if re.fullmatch(p.replace('*', '.*'), w)}
                 for p in patterns}
    for left in patterns:
        for right in patterns:
            assert _could_match(_key(left), _key(right)) == bool(
                languages[left] & languages[right]), (left, right)


CORPUS = Path(__file__).resolve().parents[1] / 'docs' / 'conformance' / 'cases'
INPUTS = [path for kind in ('record', 'full') for path in sorted((CORPUS / kind).glob('*.yap'))
          if not path.name.endswith('.expected.yap')]


@pytest.mark.parametrize('path', INPUTS, ids=lambda p: f'{p.parent.name}/{p.stem}')
def test_portable_success_corpus_can_be_saved_without_resolving(path):
    tree = parse(path.read_text(encoding='utf-8'), source=str(path))
    text = tree.to_source()
    restored = parse(text)
    assert restored.to_source() == text
    environment_file = path.with_name(path.stem + '.env.json')
    options = json.loads(environment_file.read_text(encoding='utf-8')) if environment_file.exists() else {}
    allow = options.get('allow', 'posix-standard')
    exposure = {'posix-standard': yapyon.POSIX_STANDARD_ENV,
                'windows-standard': yapyon.WINDOWS_STANDARD_ENV,
                'all': yapyon.ENV_ALL}.get(allow) if isinstance(allow, str) else frozenset(allow)
    expected = yapyon.loads_record(path.with_name(path.stem + '.expected.yap').read_text(encoding='utf-8'))
    arguments = dict(env=options.get('env', {}), env_allow=exposure)
    assert restored.resolve(**arguments) == tree.resolve(**arguments) == expected


@pytest.mark.parametrize('grouped', [False, True])
def test_collapsing_safe_layers_preserves_merge_grouping(grouped):
    first = parse('name: "x"\ny"prefix_{name}": 1\ndata: {old: 1}')
    middle, last = parse('data: None'), parse('data: {new: 2}')
    tree = merge(first, merge(middle, last)) if grouped else merge(first, middle, last)
    restored = parse(tree.to_source())
    assert restored.resolve() == tree.resolve()
    assert restored.resolve()['data'] == ({'old': 1, 'new': 2} if grouped else {'new': 2})


def test_conflicting_save_does_not_invalidate_pending_key_handles():
    tree = merge(parse('y"{name}": 1'), parse('x: 2'))
    key = tree.keys()[0]
    handle = tree[key]
    before = (key, handle.value, handle.where)
    with pytest.raises(AkanError, match='could match'):
        tree.to_source()
    assert (tree.keys()[0], handle.value, handle.where) == before
    tree['x'].remove()
    assert 'y"{name}"' in tree.to_source()


@pytest.mark.parametrize('text', [
    '{part<\n  base . agent\n>: {}}',
    'name: "x"\ns: yt"""a {\n    name\n    } b"""',
    'name: "x"\nxs: [(\n   __str__(name)\n)]',
    'name: "x"\nxs: [__str__(\n   name\n)]',
])
def test_multiline_labels_holes_and_calls_remain_parseable(text):
    tree = parse(text)
    restored = parse(tree.to_source())
    assert restored.to_source() == tree.to_source()
    if not tree.slots():
        assert restored.resolve() == tree.resolve()


@pytest.mark.parametrize('context', ['root', 'sequence'])
def test_edits_must_leave_slots_attached_to_dictionary_keys(context):
    slot = parse('part<base>: {}')['part']
    tree = parse('{}' if context == 'root' else '[0]')
    (tree.root if context == 'root' else tree[0]).replace(slot)
    with pytest.raises(AkanError, match='attached to a dictionary key'):
        tree.to_source()


def test_pending_override_layers_refuse_to_erase_a_dictionary_replacement_boundary():
    tree = parse('part<base>: {config: None}', source='first.yap')
    tree['part'].merge(parse('config: {new: 2}', source='second.yap'))
    with pytest.raises(AkanError, match='replacement boundary') as err:
        tree.to_source()
    assert 'config' in str(err.value)
    assert 'first.yap' in str(err.value) and 'second.yap' in str(err.value)
    tree['part'].fill(parse('config: {old: 1}'))
    assert tree.resolve() == {'part': {'config': {'new': 2}}}
    assert parse(tree.to_source()).resolve() == tree.resolve()


@pytest.mark.parametrize('first,last', [
    ('config: "old"', 'config: {}'),
    ('config: []', 'config: {new: 2}'),
    ('config: {+}', 'config: {new: 2}'),
    ('config: __str__(1)', 'config: {new: 2}'),
    ('config: (value)', 'config: {new: 2}'),
    ('config<>: {}', 'config: {new: 2}'),
    ('config: {}', 'config<next>: {}'),
    ('config<first>: {}', 'config<last>: {}'),
    ('config<first>: {}', 'config<>: {}'),
    ('config: {nested: None}', 'config: {nested: {new: 2}}'),
])
def test_replacement_check_handles_nested_values_and_slot_replacements(first, last):
    tree = parse('part<base>: {' + first + '}')
    tree['part'].merge(parse(last))
    with pytest.raises(AkanError, match='replacement boundary'):
        tree.to_source()


@pytest.mark.parametrize('layers', [
    ['config: None', 'config: {new: 2}', 'config: None'],
    ['config: {new: 2}', 'config: None'],
    ['config: {a: 1}', 'config: {b: 2}'],
    ['config<first>: {a: 1}', 'config: {b: 2}'],
    ['config<>: {a: 1}', 'config<last>: {b: 2}'],
    ['config<>: {a: 1}', 'config<>: {b: 2}'],
])
def test_safe_override_chains_are_not_refused(layers):
    tree = parse('part<base>: {}')
    for layer in layers:
        tree['part'].merge(parse(layer))
    saved = tree.to_source()
    for filler in ('config: {old: 1}', 'config<>: {old: 1}', 'config: None'):
        assert _finish(merge(tree), filler) == _finish(parse(saved), filler)


def test_a_premerged_override_tree_is_not_reinterpreted_as_sequential_overrides():
    tree = parse('part<base>: {}')
    overrides = merge(parse('config: None'), parse('config: {new: 2}'))
    tree['part'].merge(overrides)
    restored = parse(tree.to_source())
    for candidate in (tree, restored):
        candidate['part'].fill(parse('config: {old: 1}'))
    assert restored.resolve() == tree.resolve() == {
        'part': {'config': {'old': 1, 'new': 2}}}


def _finish(tree, filler):
    try:
        tree['part'].fill(parse(filler))
        while tree.slots():
            tree.slots()[0].fill(parse('provided: 0\nnested: {provided: 0}'))
        return ('value', tree.resolve())
    except AkanError:
        return ('akan',)


def test_override_check_has_real_continuation_witnesses_and_admits_safe_chains(monkeypatch):
    choices = ['config: None', 'config: {}', 'config: {a: 1}',
               'config: {nested: None}', 'config: {nested: {a: 1}}',
               'config<chosen>: {a: 1}', 'config<>: {a: 1}']
    fillers = ['config: None', 'config: {inherited: -1}',
               'config<>: {inherited: -1}', 'config<old>: {inherited: -1}',
               'config: {nested: {inherited: -1}}',
               'config: {nested<>: {inherited: -1}}']
    admitted = refused = 0
    for length in (2, 3):
        for layers in itertools.product(choices, repeat=length):
            tree = parse('part<base>: {}')
            for layer in layers:
                tree['part'].merge(parse(layer))
            try:
                text = tree.to_source()
                blocked = False
                admitted += 1
            except AkanError as exc:
                assert 'replacement boundary' in str(exc)
                blocked = True
                refused += 1
                with monkeypatch.context() as patch:
                    patch.setattr('yapyon._source._check_overrides', lambda *args: None)
                    text = tree.to_source()
            differences = [filler for filler in fillers
                           if _finish(merge(tree), filler) != _finish(parse(text), filler)]
            assert bool(differences) == blocked, (layers, differences)
    assert admitted and refused
