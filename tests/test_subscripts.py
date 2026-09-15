"""Subscript tests — SPEC §5.1. One test per rule, named after the rule.

`a.b` is sugar for `a["b"]`: the bracket is the general form and its content
yields a key — a quoted literal, an integer index, or a reference whose
*value* is the key. When a test and the implementation disagree, check the
spec before changing either.
"""

import pytest

from yapyon import AkanError, OrderedMultimap, loads
from yapyon.lexer import RefError, parse_ref


def akan(text, needle=""):
    with pytest.raises(AkanError) as e:
        loads(text)
    assert needle in str(e.value), f"wrong message: {e.value}"


def warnings_of(text):
    seen = []
    loads(text, warn=seen.append)
    return seen


# --------------------------------------------------------------------------- #
# The dot is sugar for the bracket
# --------------------------------------------------------------------------- #
def test_a_dot_and_a_quoted_key_are_the_same_step():
    # not two constructs: the dot reduces to the bracket, so they parse alike
    assert parse_ref("a.b").steps == parse_ref("a['b']").steps


def test_a_dot_and_a_quoted_key_resolve_alike():
    doc = 'a:\n  bar: "X"\nu: y"{a.bar}"\nv: y"{a[\'bar\']}"\n'
    out = loads(doc)
    assert out["u"] == out["v"] == "X"


def test_a_bracket_reaches_keys_a_dot_cannot():
    # this is what the general form is *for* — it subsumes §9's reserved
    # "quoted hole segments" rather than adding a third spelling.
    # No v0.1 document can *write* the key `b.c` (§7 keys are bare
    # identifiers, and quoted keys are reserved), so the reference side is
    # ready ahead of the key side. That is the compatible order.
    assert parse_ref('a["b.c"]').steps == [("key", "a"), ("key", "b.c")]


# --------------------------------------------------------------------------- #
# Integer indices are bracket-only
# --------------------------------------------------------------------------- #
def test_a_list_is_indexed_with_brackets():
    assert loads('xs: ["p", "q"]\nu: y"{xs[0]}{xs[1]}"\n')["u"] == "pq"


def test_a_dotted_integer_is_akan_because_zero_is_no_identifier():
    akan('xs: ["p"]\nu: y"{xs.0}"\n', "'0' is not an identifier")


def test_indexing_past_the_end_is_akan():
    akan('xs: ["p"]\nu: y"{xs[3]}"\n', "index 3 is past the end of a list of 1")


def test_indexing_a_non_list_is_akan():
    akan('m:\n  a: 1\nu: y"{m[0]}"\n', "is not a list")


def test_a_key_on_a_list_says_to_index_it():
    akan('xs: ["p"]\nu: y"{xs.nope}"\n', "index it with brackets instead")


def test_a_negative_index_is_reserved():
    akan('xs: ["p"]\nu: y"{xs[-1]}"\n', "negative index '-1' is reserved")


# --------------------------------------------------------------------------- #
# A bracket may hold a reference: the key is that reference's value
# --------------------------------------------------------------------------- #
def test_a_reference_in_a_bracket_names_the_key():
    doc = ('p: "claude"\nd:\n  claude: "anthropic"\n  codex: "responses"\n'
           'u: y"{d[p]}"\n')
    assert loads(doc)["u"] == "anthropic"


def test_the_inner_reference_resolves_in_the_y_strings_scope():
    # NOT in the scope of the node being indexed. {d[protocol]} means "the
    # entry named by *my* protocol", which is the whole point.
    doc = ('protocol: "outer"\nd:\n  protocol: "inner"\n  outer: "OUT"\n'
           '  inner: "IN"\nu: y"{d[protocol]}"\n')
    assert loads(doc)["u"] == "OUT"


def test_the_persona_grata_shape_resolves():
    # mind.dialects[protocol].api_uri — the case with no workaround, and the
    # api_uri's own hole still reaches its uncle
    doc = ('protocol: "claude"\nmind:\n  endpoint: "https://api"\n'
           '  dialects:\n    claude:\n      api_uri: y"{endpoint}/v1"\n'
           '    codex:\n      api_uri: y"{endpoint}/responses"\n'
           '  chosen: y"{dialects[protocol].api_uri}"\n')
    assert loads(doc)["mind"]["chosen"] == "https://api/v1"


def test_a_reference_may_nest_in_a_bracket():
    doc = 'i: "k"\nj:\n  k: "deep"\nd:\n  deep: "found"\nu: y"{d[j[i]]}"\n'
    assert loads(doc)["u"] == "found"


def test_a_reference_naming_an_integer_indexes():
    assert loads('i: 1\nxs: ["p", "q"]\nu: y"{xs[i]}"\n')["u"] == "q"


def test_a_subscript_naming_a_container_is_akan():
    akan('c:\n  x: 1\nd:\n  a: 1\nu: y"{d[c]}"\n', "not a container")


# --------------------------------------------------------------------------- #
# The bracket spelling of an identifier key is a shiran
# --------------------------------------------------------------------------- #
def test_the_long_spelling_of_an_identifier_key_warns():
    w = warnings_of('a:\n  bar: "X"\nu: y"{a[\'bar\']}"\n')
    assert len(w) == 1 and w[0].startswith("shiran:")
    assert 'the long way to write .bar' in w[0]


def test_the_warning_does_not_fire_where_the_bracket_is_needed():
    # a shiran must mark a probable mistake, not merely unusual code
    assert parse_ref('a["b.c"]').shirans == []      # a dot cannot reach it
    assert parse_ref('a["b-c"]').shirans == []
    assert warnings_of('i: 0\nxs: ["p"]\nu: y"{xs[i]}"\n') == []
    assert warnings_of('xs: ["p"]\nu: y"{xs[0]}"\n') == []


def test_the_long_spelling_still_works():
    # legal, not akan — the middle rung of the register
    assert loads('a:\n  bar: "X"\nu: y"{a[\'bar\']}"\n')["u"] == "X"


# --------------------------------------------------------------------------- #
# Multimap by-key traversal is a list view (§7.1)
# --------------------------------------------------------------------------- #
def test_a_multimap_key_names_every_value_under_it():
    doc = ('m:\n  + a: "1"\n  + b: "x"\n  + a: "2"\n'
           'u: y"{m.a[0]}{m.a[1]}"\n')
    assert loads(doc)["u"] == "12"


def test_the_view_is_a_list_so_splicing_it_whole_is_akan():
    akan('m:\n  + a: "1"\nu: y"{m.a}"\n',
         "cannot interpolate a list, dict, or multimap")


def test_zero_one_and_many_are_the_same_shape():
    # totality is what beats "unique-only": validity never depends on data
    for entries, expect in [('  + a: "1"\n', 1), ('  + a: "1"\n  + a: "2"\n', 2)]:
        doc = f'm:\n{entries}u: y"{{m.a[0]}}"\n'
        assert loads(doc)["u"] == "1"
    akan('m:\n  + a: "1"\nu: y"{m.zz[0]}"\n', "past the end of a list of 0")


# --------------------------------------------------------------------------- #
# Templates traverse identically — one grammar, three users
# --------------------------------------------------------------------------- #
def test_a_template_takes_the_same_subscripts():
    # a yt resolves against the document, so the §5.1 grammar reaches exactly
    # what it reaches in a y-string -- one grammar, and now only two users
    t = loads('p: "claude"\nd:\n  claude: "anthropic"\n'
              'xs: ["a", "b"]\nt: yt"{d[p]}/{xs[1]}"\n')["t"]
    assert t.values == ("anthropic", "b")
    assert t.render() == "anthropic/b"


def test_a_template_traverses_a_multimap_as_a_list_view():
    t = loads('m:\n  + k: "first"\n  + k: "second"\nt: yt"{m.k[1]}"\n')["t"]
    assert t.render() == "second"


def test_a_template_carries_a_whole_multimap_list_view():
    # §5.5 bars joining a list, but a yt may carry one -- the consumer that
    # wanted a JSON array gets the list
    t = loads('m:\n  + k: 1\n  + k: 2\nt: yt"{m.k}"\n')["t"]
    assert t.values == ([1, 2],)


def test_template_holes_report_the_source_spelling():
    t = loads('a:\n  b: "B"\nxs: ["x"]\nt: yt"{a[\'b\']}{xs[0]}"\n')["t"]
    assert tuple(h.ref for h in t.holes) == ("a['b']", "xs[0]")


# --------------------------------------------------------------------------- #
# Grammar errors
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ref,needle", [
    ("a[", "unclosed '['"),
    ("a[]", "empty subscript"),
    ("a['x]", "unclosed '['"),
    ("a..b", "empty segment"),
    ("a.", "may not end with '.'"),
    (".a", "empty segment"),
    ("a['x\\\\y']", "escapes in a quoted key are reserved"),
    ("8080", "not an identifier"),
])
def test_malformed_references_are_akan(ref, needle):
    with pytest.raises(RefError) as e:
        parse_ref(ref)
    assert needle in str(e.value), f"wrong message: {e.value}"


def test_a_quoted_key_may_hold_a_brace():
    # the hole scanner tracks quotes, so } inside a key does not close it
    assert parse_ref('a["}"]').steps == [("key", "a"), ("key", "}")]


def test_the_string_delimiter_still_ends_the_string():
    # y"{a["b"]}" closes at the inner quote; use the other one, as in
    # Python before PEP 701
    akan('a:\n  b: 1\nu: y"{a["b"]}"\n', "unclosed hole")


# --------------------------------------------------------------------------- #
# SPEC §9 relative references — __PARENT__ and __KEY__
# --------------------------------------------------------------------------- #
def test_key_names_the_pair_this_hole_sits_in():
    assert loads('a:\n  b:\n    here: y"{__KEY__}"\n')["a"]["b"]["here"] \
        == "here"


def test_parent_key_names_the_enclosing_block():
    # the useful one: persona-grata's {{__PARENT__.__KEY__}}, ×4
    d = loads('a:\n  b:\n    up1: y"{__PARENT__.__KEY__}"\n'
              '    up2: y"{__PARENT__.__PARENT__.__KEY__}"\n')
    assert d["a"]["b"]["up1"] == "b"
    assert d["a"]["b"]["up2"] == "a"


def test_parent_repeats_where_root_may_not():
    # __PARENT__ moves one level, so a chain is the only way to move several
    d = loads('top: "T"\na:\n  b:\n    out: y"{__PARENT__.__PARENT__'
              '.__PARENT__.top}"\n')
    assert d["a"]["b"]["out"] == "T"


def test_parent_reaches_a_sibling_explicitly():
    d = loads('a:\n  b:\n    inner: "I"\n    got: y"{__PARENT__.inner}"\n')
    assert d["a"]["b"]["got"] == "I"


def test_an_anchor_may_be_subscripted_directly():
    # position plus indirection: the enclosing mapping, keyed by p's value
    d = loads('p: "inner"\na:\n  b:\n    inner: "I"\n'
              '    got: y"{__PARENT__[p]}"\n')
    assert d["a"]["b"]["got"] == "I"


def test_parent_climbs_the_same_chain_the_scope_search_walks():
    # sequences add no frame to §5.2's search, so they add none here either:
    # one notion of nesting, not two (and a list has no key to report)
    d = loads('a:\n  xs:\n    - y"{__PARENT__.__KEY__}"\n')
    assert d["a"]["xs"] == ["a"]


def test_climbing_past_the_root_is_akan():
    akan('a:\n  b: y"{__PARENT__.__PARENT__.__PARENT__.q}"\n',
         "past the document root")
    akan('a:\n  b: y"{__PARENT__.__PARENT__.__KEY__}"\n',
         "past the document root")


def test_key_is_text_and_so_is_akan_in_a_byte_string():
    # law 5 with no special case: a key is text, and text never reaches bytes
    akan('a:\n  b: yb"{__KEY__}"\n', "no implicit encode")


def test_a_template_carries_a_key_like_any_other_value():
    t = loads('a:\n  b: yt"{__PARENT__.__KEY__}"\n')["a"]["b"]
    assert t.values == ("a",) and t.render() == "a"


@pytest.mark.parametrize("ref,needle", [
    ("a.__KEY__", "after a key the name is already known"),
    ("__KEY__.x", "ends a reference"),
    ("a.__PARENT__", "may only lead a reference"),
    ("__ROOT__.__PARENT__.x", "__ROOT__ already anchors"),
    ("__ROOT__.__KEY__", "the document root has no key"),
])
def test_the_anchors_are_positional_and_the_grammar_says_so(ref, needle):
    with pytest.raises(RefError) as e:
        parse_ref(ref)
    assert needle in str(e.value)


# --------------------------------------------------------------------------- #
# SPEC §5.1.2 — named container serializers
# --------------------------------------------------------------------------- #
def test_a_container_crosses_into_text_when_the_author_names_the_encoding():
    # law 5's extension: §5.5 bars a bare container, and this is the named
    # bridge, exactly as b64"..." is the named bridge for bytes
    d = loads('cfg:\n  name: "gw"\n  port: 8080\n'
              'u: y"{cfg.__AS_JSON__()}"\n')
    assert d["u"] == '{\n  "name": "gw",\n  "port": 8080\n}'


def test_json_keeps_document_order_and_leaves_utf8_alone():
    # order is data in yapyon, so it is never sorted; and the output is UTF-8
    d = loads('cfg:\n  z: 1\n  a: "café"\n  t: True\n  n: None\n'
              'u: y"{cfg.__AS_JSON__()}"\n')
    assert d["u"] == ('{\n  "z": 1,\n  "a": "café",\n  "t": true,\n'
                      '  "n": null\n}')


def test_toml_nests_mappings_into_tables():
    d = loads('store:\n  model: "m1"\n  providers:\n    codex:\n'
              '      wire_api: "responses"\n'
              'u: y"{store.__AS_TOML__()}"\n')
    assert d["u"] == ('model = "m1"\n\n[providers.codex]\n'
                      'wire_api = "responses"\n')


def test_toml_value_types_and_quoting():
    d = loads('s:\n  i: 3\n  f: 1.5\n  yes: True\n  no: False\n'
              '  xs: ["x", "y"]\n'
              'u: y"{s.__AS_TOML__()}"\n')
    out = d["u"]
    assert "i = 3" in out and "f = 1.5" in out
    assert "yes = true" in out and "no = false" in out
    assert 'xs = ["x", "y"]' in out


def test_toml_has_no_null_so_none_is_akan():
    # persona-grata never meets this because it prunes first; yapyon does not
    # prune, so it must refuse rather than drop the key (law 7)
    akan('s:\n  a: None\nu: y"{s.__AS_TOML__()}"\n', "TOML has no null")


def test_a_toml_document_is_a_table():
    akan('xs: [1, 2]\nu: y"{xs.__AS_TOML__()}"\n', "needs a mapping")


def test_yaml_is_block_style_in_declaration_order():
    d = loads('store:\n  GOOSE_PROVIDER: "openai"\n  GOOSE_MODEL: "nav-m1"\n'
              'u: y"{store.__AS_YAML__()}"\n')
    # declaration order, not alphabetical -- GOOSE_MODEL would sort first
    assert d["u"] == "GOOSE_PROVIDER: openai\nGOOSE_MODEL: nav-m1\n"


def test_yaml_quotes_anything_yaml_would_guess_at():
    # yapyon exists partly because YAML guesses; emitting into it means
    # quoting unless the scalar is provably inert
    d = loads('s:\n  a: "no"\n  b: "3"\n  c: "true"\n  d: "plain"\n'
              '  e: "with space"\n  f: ""\n'
              'u: y"{s.__AS_YAML__()}"\n')
    assert d["u"] == ("a: 'no'\nb: '3'\nc: 'true'\nd: plain\n"
                      "e: 'with space'\nf: ''\n")


def test_yaml_does_not_wrap_a_long_scalar():
    # a folded URL is valid YAML but no longer greppable in the file it lands in
    url = "https://api.example.com/" + "x" * 120
    d = loads(f's:\n  OPENAI_HOST: "{url}"\nu: y"{{s.__AS_YAML__()}}"\n')
    assert d["u"] == f"OPENAI_HOST: {url}\n"


def test_yaml_nests_and_takes_lists():
    d = loads('s:\n  a:\n    b: 1\n  xs: ["p", "q"]\n'
              'u: y"{s.__AS_YAML__()}"\n')
    assert d["u"] == "a:\n  b: 1\nxs:\n  - p\n  - q\n"


def test_a_serialized_container_may_be_carried_by_a_template():
    t = loads('cfg: {x: 1}\nt: yt"{cfg.__AS_JSON__()}"\n')["t"]
    assert t.values == ('{\n  "x": 1\n}',)


def test_a_serializer_follows_the_anchors_like_any_reference():
    d = loads('a:\n  cfg: {x: 1}\n  u: y"{__PARENT__.cfg.__AS_JSON__()}"\n')
    assert d["a"]["u"] == '{\n  "x": 1\n}'


@pytest.mark.parametrize("fmt", ["JSON", "TOML", "YAML"])
def test_no_format_here_can_hold_a_multimap(fmt):
    # law 1: repeated keys have no faithful form in any of them, so refuse
    # rather than pick a reading
    akan(f'm:\n  + k: 1\n  + k: 2\nu: y"{{m.__AS_{fmt}__()}}"\n',
         "no faithful encoding")


@pytest.mark.parametrize("fmt", ["JSON", "TOML", "YAML"])
def test_bytes_have_no_named_encoding_in_any_of_them(fmt):
    akan(f'c:\n  b: b64"aGk="\nu: y"{{c.__AS_{fmt}__()}}"\n',
         "has no bytes")


def test_yapyon_does_not_prune():
    # persona-grata drops None/"" on the way out, implementing its own schema's
    # "not sent if unset" rule. That is a consumer policy: dropping a key the
    # document wrote would be a silent reinterpretation (law 7).
    d = loads('s:\n  kept: "v"\n  blank: ""\n  unset: None\n'
              'u: y"{s.__AS_JSON__()}"\n')
    assert '"blank": ""' in d["u"] and '"unset": null' in d["u"]


def test_serializing_a_single_value_is_reserved():
    # narrowing later would not be compatible; this leaves the door open
    akan('n: 5\nu: y"{n.__AS_JSON__()}"\n', "is reserved")


@pytest.mark.parametrize("ref,needle", [
    ("cfg.__AS_XML__()", "there is no serializer named"),
    ("cfg.foo()", "not a serializer"),
    ("__AS_JSON__()", "needs a value to encode"),
    ("__KEY__.__AS_JSON__()", "a key is already text"),
])
def test_the_serializer_set_belongs_to_the_format(ref, needle):
    # a closed, format-defined set is the line between these and the
    # consumer-registered functions that remain undesigned
    with pytest.raises(RefError) as e:
        parse_ref(ref)
    assert needle in str(e.value)


# --------------------------------------------------------------------------- #
# A serializer may not be applied to a bare anchor (SPEC §5.1.2)
#
# Not a restriction on anchors, and not an implementation artifact: an anchor
# is *always* an ancestor of the hole, so encoding it would need the value it
# is computing. Unconditionally circular, so it is akan at parse, where the
# author can see it (law 7), rather than as a cycle reported later.
#
# The useful shape -- an anchor plus a step leading away from the hole -- is
# legal and is covered below, so the bar costs nothing.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ref", [
    "__ROOT__.__AS_JSON__()",
    "__PARENT__.__AS_JSON__()",
    "__PARENT__.__PARENT__.__AS_YAML__()",
    "__ROOT__.__AS_TOML__()",
])
def test_a_serializer_on_a_bare_anchor_is_circular(ref):
    with pytest.raises(RefError) as e:
        parse_ref(ref)
    msg = str(e.value)
    assert "contains this hole" in msg
    # the message must name the real reason, not the bare-serializer one:
    # "needs a value to encode" is false here, since an anchor names a value
    assert "needs a value to encode" not in msg


@pytest.mark.parametrize("ref", [
    "__ROOT__.blk.__AS_JSON__()",
    "__PARENT__.blk.__AS_JSON__()",
    "__PARENT__.__PARENT__.blk.__AS_YAML__()",
    "__ROOT__[p].__AS_JSON__()",
    "cfg.__AS_JSON__()",
])
def test_an_anchor_with_a_step_may_be_serialized(ref):
    # what the bar above does *not* cost: naming a block through an anchor
    assert parse_ref(ref).serializer.startswith("__AS_")


def test_the_circular_akan_lands_in_a_document_at_the_hole():
    akan('blk:\n  a: 1\n  me: y"{__PARENT__.__AS_JSON__()}"\n',
         "contains this hole")


def test_serializing_a_sibling_block_through_an_anchor_works():
    # the shape the bar leaves intact, end to end
    d = loads('blk:\n  a: 1\n  b: "two"\nout: y"j={__ROOT__.blk.__AS_JSON__()}"\n')
    assert d["out"] == 'j={\n  "a": 1,\n  "b": "two"\n}'


# --------------------------------------------------------------------------- #
# The serializers, checked against independent readers
#
# An emitter that nobody reads back is a guess. tomllib is stdlib (read-only,
# which is exactly why the writer above had to be ours); PyYAML is a dev extra.
# This is the check that found the escaped-quote bug in yapyon's own emitter.
# --------------------------------------------------------------------------- #
SERIALIZER_CORPUS = (
    's:\n  name: "gw"\n  port: 8080\n  ratio: 3.5\n  on: True\n  off: False\n',
    's:\n  xs: ["a", "b"]\n  ns: [1, 2, 3]\n',
    's:\n  a:\n    b:\n      c: "deep"\n',
    's:\n  uni: "café 日本 😀"\n  esc: "quote\\" back\\\\ slash"\n',
    's:\n  tricky: "no"\n  numeric: "3"\n  spaced: "a b"\n  empty: ""\n',
    's:\n  url: "https://api.example.com/v1?a=1&b=2"\n',
    's:\n  deep:\n    xs: [1, 2]\n  after: "kept"\n',
)


@pytest.mark.parametrize("src", SERIALIZER_CORPUS)
def test_emitted_toml_reads_back_as_the_same_data(src):
    import tomllib
    text = loads(src + 'u: y"{s.__AS_TOML__()}"\n')["u"]
    assert tomllib.loads(text) == loads(src)["s"]


@pytest.mark.parametrize("src", SERIALIZER_CORPUS)
def test_emitted_yaml_reads_back_as_the_same_data(src):
    yaml = pytest.importorskip("yaml")
    text = loads(src + 'u: y"{s.__AS_YAML__()}"\n')["u"]
    assert yaml.safe_load(text) == loads(src)["s"]


@pytest.mark.parametrize("src", SERIALIZER_CORPUS)
def test_emitted_json_reads_back_as_the_same_data(src):
    import json
    text = loads(src + 'u: y"{s.__AS_JSON__()}"\n')["u"]
    assert json.loads(text) == loads(src)["s"]
