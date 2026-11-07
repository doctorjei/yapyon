"""Structural normalization distributes known keys without flattening programs."""

import pytest

from yapyon import AkanError, merge, parse


def _reload(tree):
    text = tree.to_source()
    restored = parse(text, source='saved.yap')
    assert restored.to_source() == text
    return restored


@pytest.mark.parametrize('context', ['{}', '7', 'config: {old: 1}',
                                     'config: {nested: {old: 1}}'])
@pytest.mark.parametrize('initial,later', [
    ('', 'config: {new: 2}'),
    ('config: {}', 'config: {new: 2}'),
    ('config: {nested: {}}', 'config: {nested: {new: 2}}'),
    ('keep: 1', 'config: {new: 2}'),
    ('config: {first: 1}', 'config: {second: 2}'),
    ('config: "first"', 'config: "last"'),
])
def test_safe_dictionary_override_transitions_collapse_recursively(context, initial, later):
    tree = parse('part<base>: {' + initial + '}\n|\npart: {' + later + '}')
    restored = _reload(tree)
    assert '|' not in restored.to_source()
    assert restored['part'].label == ('base',)
    for candidate in (tree, restored):
        candidate['part'].fill(parse(context))
    assert restored.resolve() == tree.resolve()


@pytest.mark.parametrize('context', ['{}', 'config: {old: 1}', 'config: [1]'])
@pytest.mark.parametrize('initial,later', [
    ('config: "reset"', 'config: {new: 2}'),
    ('config: [1]', 'config: [2]'),
    ('config: {nested: "reset"}', 'config: {nested: {new: 2}}'),
    ('config: (choice)', 'config: {new: 2}'),
    ('config:= "reset"', 'config: {new: 2}'),
    ('config: "reset"', 'config:= {new: 2}'),
])
def test_unproven_and_kind_reset_transitions_retain_their_sequential_layers(
        context, initial, later):
    tree = parse('choice: None\npart<base>: {' + initial + '}\n|\npart: {' + later + '}')
    restored = _reload(tree)
    assert '|' in restored.to_source()
    for candidate in (tree, restored):
        candidate['part'].fill(parse(context))
    assert restored.resolve() == tree.resolve()


def test_pointwise_merging_keeps_child_collection_comparisons_deferred():
    tree = parse('f: {x: [1], z: {old: 1}}\n|\nf: {x: [2], z: {new: 2}}')
    saved = tree.to_source()
    assert saved.count('f:') == 1 and saved.count('z:') == 1
    assert saved.count('|') == 1
    assert _reload(tree).resolve() == tree.resolve() == {
        'f': {'x': [1, 2], 'z': {'old': 1, 'new': 2}}}


def test_empty_slot_absorption_keeps_the_following_validation_domain():
    tree = parse('name: "a"\npart<base>: {}\n|\npart: {a: 1, y"{name}": 2}')
    restored = _reload(tree)
    assert restored.to_source().count('part') == 1
    for candidate in (tree, restored):
        candidate['part'].fill(parse('{}'))
        with pytest.raises(AkanError, match='duplicate'):
            candidate.resolve()


def test_nonempty_dynamic_key_contributions_are_not_premerged():
    tree = parse('name: "a"\npart<base>: {y"{name}": 1}\n|\npart: {a: 2}')
    restored = _reload(tree)
    assert '|' in restored.to_source()
    for candidate in (tree, restored):
        candidate['part'].fill(parse('{}'))
        assert candidate.resolve()['part'] == {'a': 2}


def test_unexpanded_comprehension_is_not_an_empty_initial_override():
    tree = parse('names: ["a", "a"]\npart<base>: {key: 1 for key in names}\n|\npart: {a: 2}')
    restored = _reload(tree)
    assert 'for key in names' in restored.to_source() and '|' in restored.to_source()
    for candidate in (tree, restored):
        candidate['part'].fill(parse('{}'))
        with pytest.raises(AkanError, match='duplicate'):
            candidate.resolve()


def test_empty_absorption_does_not_reassociate_the_following_dictionary_program():
    tree = parse('part<base>: {}\n|\npart: ({config: "reset"} | {config: {new: 2}})')
    restored = _reload(tree)
    assert '|' not in restored.to_source()
    for candidate in (tree, restored):
        candidate['part'].fill(parse('config: {old: 1}'))
        assert candidate.resolve() == {'part': {'config': {'old': 1, 'new': 2}}}


def test_retained_slot_contributions_follow_their_matching_fields():
    tree = parse('agent: {format: "v1", persona<base.persona>: {config: "reset"}, '
                 'harness<base.harness>: {config: "reset"}, secret: "kept"}\n|\n'
                 'agent: {persona: {config: {new: 2}}, harness: {config: {new: 3}}}')
    text = tree.to_source()
    assert text.index('persona<') < text.index('persona:') < text.index('harness<')
    assert text.index('harness<') < text.index('harness:') < text.index('secret:')
    restored = _reload(tree)
    for candidate in (tree, restored):
        assert candidate['agent'].keys() == ['format', 'persona', 'harness', 'secret']
        filler = parse('persona: {config: {old: 1}}\nharness: {config: {old: 1}}')
        candidate['agent']['persona'].fill(filler)
        candidate['agent']['harness'].fill(filler)
        assert candidate.resolve()['agent'] == {
            'format': 'v1', 'persona': {'config': {'new': 2}},
            'harness': {'config': {'new': 3}}, 'secret': 'kept'}


def test_locality_does_not_split_a_computed_key_validation_domain():
    tree = parse('name: "harness"\nagent: {persona<base>: {config: "reset"}, '
                 'harness: 1, y"{name}": 2}\n|\nagent: {persona: {config: {new: 2}}}')
    restored = _reload(tree)
    for candidate in (tree, restored):
        candidate['agent']['persona'].fill(parse('{}'))
        with pytest.raises(AkanError, match='duplicate'):
            candidate.resolve()


def test_normalized_known_keys_preserve_spelling_visibility_and_replacement_intent():
    tree = parse('part<base>: {"x": {}, ｚ: 3.10}\n|\npart: {x: {new: 0x2}, z:= 0b1}')
    restored = _reload(tree)
    assert '|' not in restored.to_source()
    assert '"x":' in restored.to_source() and 'ｚ:= 0b1' in restored.to_source()
    for candidate in (tree, restored):
        candidate['part'].fill(parse('"x": {old: 1}'))
        candidate.merge(parse('out: y"{part.x}"'))
        with pytest.raises(AkanError, match='quoted and computed keys are not names'):
            candidate.resolve()


def test_abstract_slot_and_explicit_replacement_do_not_keep_an_old_named_label():
    for text in ('part<>: {}\n|\npart: {value: 1}',
                 'part<base>: {}\n|\npart:= {value: 1}'):
        tree = parse(text)
        restored = _reload(tree)
        assert restored.slots() == []
        assert restored.resolve() == tree.resolve() == {'part': {'value': 1}}


@pytest.mark.parametrize('following', [
    '{y"{name}": 2}', '{a: 1, y"{name}": 2}',
    '{key: 1 for key in names}',
])
def test_nested_empty_dictionary_does_not_leave_a_redundant_validation_layer(following):
    tree = parse('name: "a"\nnames: ["a", "a"]\npart<base>: {config: {}}\n|\n'
                 'part: {config: ' + following + '}')
    restored = _reload(tree)
    assert '|' not in restored.to_source()
    for candidate in (tree, restored):
        candidate['part'].fill(parse('config: {old: 1}'))
        if following == '{y"{name}": 2}':
            assert candidate.resolve()['part'] == {'config': {'old': 1, 'a': 2}}
        else:
            with pytest.raises(AkanError, match='duplicate'):
                candidate.resolve()


def test_absorption_performs_no_evaluation_or_collection_comparison(monkeypatch):
    tree = parse('part<base>: {config: {}}\n|\npart: {config: {y"{key}": RUN()}, '
                 'home: y"{$HOME}", rows: {k: 1 for k in names}, items: [1] | [2]}')
    before = tree['part'].where, tree['part'].label, tree.warnings[:]

    def forbidden(*args, **kwargs):
        pytest.fail('recursive normalization evaluated unfinished data')

    for target in ('yapyon.resolver.Resolver.resolve', 'yapyon.resolver.Resolver._lookup',
                   'yapyon.resolver.Resolver._call', 'yapyon.resolver.Resolver._env',
                   'yapyon._expressions.evaluate', 'yapyon._expressions._comprehend',
                   'yapyon.environment.Environment.get', 'yapyon.Template.render',
                   'yapyon.assembly.collection_merge', 'yapyon.assembly._fingerprint'):
        monkeypatch.setattr(target, forbidden)
    text = tree.to_source()
    assert text.count('part<base>') == 1 and text.count('part:') == 0
    assert 'RUN()' in text and '{$HOME}' in text and 'for k in names' in text
    assert '|' in text
    assert parse(text).to_source() == text
    assert (tree['part'].where, tree['part'].label, tree.warnings) == before


def test_recursive_override_rules_preserve_a_bounded_continuation_matrix():
    choices = ['config: None', 'config: {}', 'config: {a: 1}',
               'config: {deep: {}}', 'config: {deep: "reset"}',
               'config<chosen>: {a: 1}', 'config<>: {a: 1}',
               'config:= None', 'config:= {}', 'config:= {a: 1}',
               '"config": {b: 2}', 'config: {y"dynamic": 1}']
    fillers = ['config: None', 'config: {old: 1}',
               'config<>: {old: 1}', 'config<old>: {old: 1}',
               'config: {deep: {old: 1}}', 'config: {deep<>: {old: 1}}']

    def finish(tree, filler):
        try:
            tree['part'].fill(parse(filler))
            while tree.slots():
                tree.slots()[0].fill(parse('provided: 0\ndeep: {provided: 0}'))
            return ('value', tree.resolve())
        except AkanError:
            return ('akan',)

    for initial in choices:
        for later in choices:
            tree = parse('part<base>: {' + initial + '}\n|\npart: {' + later + '}')
            restored = _reload(tree)
            for filler in fillers:
                assert finish(merge(tree), filler) == finish(merge(restored), filler), (
                    initial, later, filler, restored.to_source())


def test_field_edits_after_empty_absorption_keep_logical_dictionary_continuations():
    tree = parse('part<base>: {config: {}}\n|\npart: {config: {new: 2}}')
    restored = _reload(tree)
    for candidate in (tree, restored):
        candidate['part'].fill(parse('config: {old: 1}'))
        candidate['part']['config']['new'].remove()
        candidate['part']['config'].merge(parse('later: 3'))
        assert candidate.resolve() == {'part': {'config': {'old': 1, 'later': 3}}}
