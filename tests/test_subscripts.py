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
    # No v0.1 document can *write* the key `b.c` (GRAMMAR §G7 keys are bare
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


def test_a_negative_index_counts_from_the_end():
    doc = 'xs: ["p", "q", "r"]\nu: y"{xs[-1]}"\nv: y"{xs[-3]}"\n'
    assert loads(doc)["u"] == "r"
    assert loads(doc)["v"] == "p"


def test_minus_zero_is_index_zero():
    assert loads('xs: ["p", "q"]\nu: y"{xs[-0]}"\n')["u"] == "p"


def test_indexing_before_the_start_is_akan():
    akan('xs: ["p"]\nu: y"{xs[-2]}"\n',
         "index -2 is before the start of a list of 1")


def test_a_plus_sign_is_not_an_index():
    akan('xs: ["p"]\nu: y"{xs[+0]}"\n', "")


def test_a_negative_index_through_a_reference_counts_from_the_end():
    doc = 'xs: ["p", "q"]\ni: -1\nu: y"{xs[i]}"\n'
    assert loads(doc)["u"] == "q"


def test_a_negative_index_through_a_reference_is_range_checked():
    # Once raised a bare IndexError: only the far end was checked.
    akan('xs: ["p"]\ni: -5\nu: y"{xs[i]}"\n',
         "index -5 is before the start of a list of 1")


def test_a_negative_index_takes_the_last_of_a_multimap_view():
    doc = ('mm:\n  + k: "first"\n  + k: "last"\nu: y"{mm.k[-1]}"\n')
    assert loads(doc)["u"] == "last"


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
    # a yt resolves against the document, so the GRAMMAR §G5 grammar reaches exactly
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
    ("a['x]", "unterminated string"),
    ("a..b", "empty segment"),
    ("a.", "may not end with '.'"),
    (".a", "empty segment"),
    ("8080", "not an identifier"),
])
def test_malformed_references_are_akan(ref, needle):
    with pytest.raises(RefError) as e:
        parse_ref(ref)
    assert needle in str(e.value), f"wrong message: {e.value}"


def test_a_quoted_key_may_hold_a_brace():
    # the hole scanner tracks quotes, so } inside a key does not close it
    assert parse_ref('a["}"]').steps == [("key", "a"), ("key", "}")]


def test_a_quoted_key_takes_escapes():
    # GRAMMAR §G5: a STRING in a hole takes §G4.5's escapes (operator,
    # 2026-10-13; reserved until v0.3)
    assert parse_ref("a['x\\'y']").steps == [("key", "a"), ("key", "x'y")]
    assert parse_ref('a["b\\x2ec"]').steps == [("key", "a"), ("key", "b.c")]


@pytest.mark.parametrize("doc,value", [
    # GRAMMAR §G4.7, as in Python since PEP 701: a literal does not end
    # inside a hole, even at its own quote mark
    ('a:\n  b: 1\nu: y"{a["b"]}"\n', "1"),
    ("a:\n  b: 1\nu: y'{a['b']}'\n", "1"),
    ('a:\n  b: 1\nu: y"x{a["b"]}y{a[\'b\']}z"\n', "x1y1z"),
    ('a:\n  b: 1\nu: ry"{a["b"]}\\d"\n', "1\\d"),
    ('a:\n  b: 1\nu: y"""\n  {a["b"]}\n  """\n', "1\n"),
    ('a:\n  b: 1\nu: y"{{"\nv: "}}"\n', "{"),
])
def test_a_literal_does_not_end_inside_a_hole(doc, value):
    assert loads(doc)["u"] == value


def test_a_brace_in_a_hole_string_is_content():
    from yapyon.lexer import tokenize
    tok = tokenize('u: y"<{a["}"]}>"\n')[2]
    assert tok.parts == [("text", "<"), ("hole", 'a["}"]'), ("text", ">")]


@pytest.mark.parametrize("doc,needle", [
    ('a:\n  b: 1\nu: y"{a["b}"\n', "unclosed hole"),
    ('a:\n  b: 1\nu: y"{a["b"]"\nv: "}"\n', "unclosed hole"),
])
def test_an_unclosed_hole_is_still_found_on_its_own_line(doc, needle):
    # A single-line literal looks for a hole's `}` on its own line only, so
    # a brace further down the document cannot swallow the rest of the line
    akan(doc, needle)


# --------------------------------------------------------------------------- #
# SPEC §5.1.1 relative references — __PARENT__ and __KEY__
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
    assert d["u"] == '{"name": "gw", "port": 8080}'     # fits: one line (§14.1)


def test_json_keeps_document_order_and_leaves_utf8_alone():
    # order is data in yapyon, so it is never sorted; and the output is UTF-8
    d = loads('cfg:\n  z: 1\n  a: "café"\n  t: True\n  n: None\n'
              'u: y"{cfg.__AS_JSON__()}"\n')
    assert d["u"] == '{"z": 1, "a": "café", "t": true, "n": null}'


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


def test_toml_has_no_null_so_none_is_left_out_and_recorded():
    # SPEC §14.5: the one omission the format makes, recorded so nothing is
    # lost; in an array a stand-in keeps every later index where it was
    d = loads('s:\n  a: None\n  b: 1\n  xs: [None, 2]\nu: y"{s.__AS_TOML__()}"\n')
    assert d["u"] == ('b = 1\nxs = ["None", 2]\n'
                      '"@_lexemes" = {a = "None", "xs/0" = "None"}\n')


def test_a_toml_document_is_a_table():
    # SPEC §5.1.2: __AS_TOML__ refuses by signature
    akan('xs: [1, 2]\nu: y"{xs.__AS_TOML__()}"\n',
         "__AS_TOML__() takes dict[str, Any] | multimap[str, Any], not list")
    akan('n: 5\nu: y"{n.__AS_TOML__()}"\n', "a TOML document is a table")


# --------------------------------------------------------------------------- #
# A list of mappings is a TOML array of tables (SPEC §5.1.2)
#
# The refusal that stood here was over-broad. SPEC §5.1.2's akan list names
# multimaps, bytes and None-in-TOML, and never a mapping nested in a
# sequence; the spec already said "nested mappings become tables", and the
# writer had simply stopped short of the repeated-key case. Measured against
# tomllib before building: `[[a]]`, nested `[[a.b]]`, inline tables inside
# arrays, and quoted keys in headers are all legal TOML.
# --------------------------------------------------------------------------- #
def test_toml_writes_a_list_of_mappings_as_an_array_of_tables():
    d = loads('s:\n  gate:\n    - name: "check"\n      on: True\n'
              '    - name: "parity"\n      on: False\n'
              'u: y"{s.__AS_TOML__()}"\n')
    assert d["u"] == ('[[gate]]\nname = "check"\non = true\n\n'
                      '[[gate]]\nname = "parity"\non = false\n')


def test_toml_gives_a_super_table_no_header_above_an_array_of_tables():
    # `[[a.b]]` already says `a` exists, so a `[a]` header would name a
    # second, redundant table.
    d = loads('s:\n  a:\n    b:\n      - k: 1\n'
              'u: y"{s.__AS_TOML__()}"\n')
    assert d["u"] == "[[a.b]]\nk = 1\n"


def test_toml_keeps_a_super_table_header_when_it_has_pairs_of_its_own():
    d = loads('s:\n  a:\n    x: 1\n    b:\n      - k: 2\n'
              'u: y"{s.__AS_TOML__()}"\n')
    assert d["u"] == "[a]\nx = 1\n\n[[a.b]]\nk = 2\n"


def test_toml_nests_an_array_of_tables_inside_an_array_of_tables():
    # Each element must be written out in full before the next header opens.
    # A nested table attaches to the *most recent* `[[fruit]]`, so emitting
    # every `[[fruit]]` header first would hang all the varieties off one.
    d = loads('s:\n  fruit:\n    - name: "apple"\n      variety:\n'
              '        - n: "red"\n        - n: "gold"\n'
              'u: y"{s.__AS_TOML__()}"\n')
    assert d["u"] == ('[[fruit]]\nname = "apple"\n\n[[fruit.variety]]\n'
                      'n = "red"\n\n[[fruit.variety]]\nn = "gold"\n')


def test_toml_writes_a_mixed_list_with_inline_tables():
    # A mixed list cannot use headers at all: TOML gives a key either an
    # array of tables or an array value, never both. Inline tables keep the
    # mappings faithful *and* keep the non-mappings, where headers would
    # have forced a choice.
    d = loads('s:\n  a:\n    - x: 1\n    - 2\n    - "s"\n'
              'u: y"{s.__AS_TOML__()}"\n')
    assert d["u"] == 'a = [{x = 1}, 2, "s"]\n'


def test_toml_writes_an_empty_list_inline_rather_than_losing_the_key():
    # An empty list has no element to give a header, and no header means no
    # key at all. `a = []` is how TOML says empty.
    d = loads('s:\n  a: []\n  b:\n    - {}\n'
              'u: y"{s.__AS_TOML__()}"\n')
    assert d["u"] == "a = []\n\n[[b]]\n"


def test_toml_quotes_a_non_ascii_key_in_an_array_header():
    # A yapyon key is always an identifier, and an identifier never contains
    # a dot -- quoted keys are reserved in v0.1 -- so the only key that can
    # make a header need quoting is a non-ASCII one. TOML's bare-key set is
    # ASCII-only, so it goes out quoted, which keeps it literal.
    d = loads('s:\n  日本:\n    - k: 1\n'
              'u: y"{s.__AS_TOML__()}"\n')
    assert d["u"] == '[["日本"]]\nk = 1\n'


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
    assert d["u"] == ('a: "no"\nb: "3"\nc: "true"\nd: plain\n'
                      'e: "with space"\nf: ""\n')


def test_yaml_does_not_wrap_a_long_scalar():
    # a folded URL is valid YAML but no longer greppable in the file it lands in
    url = "https://api.example.com/" + "x" * 120
    d = loads(f's:\n  OPENAI_HOST: "{url}"\nu: y"{{s.__AS_YAML__()}}"\n')
    assert d["u"] == f"OPENAI_HOST: {url}\n"


def test_yaml_nests_and_takes_lists():
    d = loads('s:\n  a:\n    b: 1\n  xs: ["p", "q"]\n'
              'u: y"{s.__AS_YAML__()}"\n')
    assert d["u"] == "a:\n  b: 1\nxs: [p, q]\n"      # a flat list that fits


def test_a_serialized_container_may_be_carried_by_a_template():
    t = loads('cfg: {x: 1}\nt: yt"{cfg.__AS_JSON__()}"\n')["t"]
    assert t.values == ('{"x": 1}',)


def test_a_serializer_follows_the_anchors_like_any_reference():
    d = loads('a:\n  cfg: {x: 1}\n  u: y"{__PARENT__.cfg.__AS_JSON__()}"\n')
    assert d["a"]["u"] == '{"x": 1}'


@pytest.mark.parametrize("fmt,expected", [
    # SPEC §5.1.2 v0.3: approximate, never refuse -- each format's own
    # mechanism, and no marker carries yapyon's name (§14.3-§14.5)
    ("JSON", '{"@type": "multimap", "entries": {"@list": [{"k": 1}, {"k": 2}]}}'),
    ("TOML", '"@type" = "multimap"\nentries = [{k = 1}, {k = 2}]\n'),
    ("YAML", "%TAG !multimap! tag:yaml.org,2002:\n---\n!multimap!pairs\n"
             "- k: 1\n- k: 2\n"),
])
def test_a_multimap_is_marked_in_every_format(fmt, expected):
    assert loads(f'm:\n  + k: 1\n  + k: 2\nu: y"{{m.__AS_{fmt}__()}}"\n')["u"] \
        == expected


@pytest.mark.parametrize("fmt,expected", [
    ("JSON", '{"b": "aGk=", "@_lexemes": {"b": "b64\'aGk=\'"}}'),
    ("TOML", 'b = "aGk="\n"@_lexemes" = {b = "b64\'aGk=\'"}\n'),
    ("YAML", 'b: !!binary "aGk="\n'),
])
def test_bytes_are_text_with_their_spelling_beside_them(fmt, expected):
    assert loads(f"c:\n  b: b64'aGk='\nu: y\"{{c.__AS_{fmt}__()}}\"\n")["u"] \
        == expected


def test_yapyon_does_not_prune():
    # persona-grata drops None/"" on the way out, implementing its own schema's
    # "not sent if unset" rule. That is a consumer policy: dropping a key the
    # document wrote would be a silent reinterpretation (law 7).
    d = loads('s:\n  kept: "v"\n  blank: ""\n  unset: None\n'
              'u: y"{s.__AS_JSON__()}"\n')
    assert '"blank": ""' in d["u"] and '"unset": null' in d["u"]


def test_serializing_a_single_value_writes_it_plain():
    # SPEC §5.1.2 v0.3 (operator: "this is minimal code, isn't it? Why not
    # just do it so our edge cases are fewer?") -- never wrapped
    assert loads('n: 5\nu: y"{n.__AS_JSON__()}"\n')["u"] == "5"
    assert loads('n: "x"\nu: y"{n.__AS_JSON__()}"\n')["u"] == '"x"'


@pytest.mark.parametrize("ref", [
    "cfg.__AS_XML__()",     # an unknown built-in is akan when resolved
    "cfg.foo()",            # a declared function (SPEC §13)
    "__AS_JSON__()",        # arity is the specification's, not the grammar's
    "__AS_JSON__(cfg)",     # the receiver form is sugar for this one
])
def test_the_grammar_admits_any_call(ref):
    # GRAMMAR §G5: "which ones exist, and how many arguments each takes, are
    # the specification's business -- a grammar cannot enumerate them"
    assert parse_ref(ref).call is not None


def test_the_receiver_form_is_sugar():
    assert parse_ref("cfg.__AS_JSON__()") == parse_ref("__AS_JSON__(cfg)")


def test_an_unknown_built_in_is_akan_naming_those_that_exist():
    akan('cfg:\n  a: 1\nu: y"{cfg.__AS_XML__()}"\n',
         "there is no built-in named __AS_XML__()")


def test_nothing_follows_a_key():
    with pytest.raises(RefError) as e:
        parse_ref("__KEY__.__AS_JSON__()")
    assert "a key is already text" in str(e.value)


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
    assert parse_ref(ref).call.name.startswith("__AS_")


def test_the_circular_akan_lands_in_a_document_at_the_hole():
    akan('blk:\n  a: 1\n  me: y"{__PARENT__.__AS_JSON__()}"\n',
         "contains this hole")


def test_serializing_a_sibling_block_through_an_anchor_works():
    # the shape the bar leaves intact, end to end
    d = loads('blk:\n  a: 1\n  b: "two"\nout: y"j={__ROOT__.blk.__AS_JSON__()}"\n')
    assert d["out"] == 'j={"a": 1, "b": "two"}'


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
    # The array-of-tables shapes, added with the emitter that writes them: the
    # corpus is what checks the output against a reader nobody wrote for it.
    's:\n  gate:\n    - name: "check"\n      on: True\n'
    '    - name: "parity"\n      on: False\n',
    's:\n  a:\n    b:\n      - k: 1\n      - k: 2\n',
    's:\n  a:\n    x: 1\n    b:\n      - k: 2\n',
    's:\n  fruit:\n    - name: "apple"\n      variety:\n'
    '        - n: "red"\n        - n: "gold"\n',
    's:\n  a:\n    - x: 1\n    - 2\n    - "s"\n',
    's:\n  a: []\n  b:\n    - {}\n',
    's:\n  日本:\n    - k: 1\n',
    's:\n  a:\n    - d:\n        e:\n          - f: 1\n',
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


# --------------------------------------------------------------------------- #
# A serializer whose target is not resolved *yet* must defer, not refuse
#
# `NotEncodable` conflated two different things: "this has no faithful
# encoding" (permanent) and "this still holds a y-string" (ask again next
# pass). Conflating them made a mutual cycle between two serializer calls
# report "a YString cannot be serialized" -- the wrong problem, at the wrong
# line, with no mention of the cycle or the other reference. 0.1.0a3 ships it.
#
# The fixpoint already knows how to defer on a YString and how to call a stall
# a cycle (§5.3), so the fix is to rejoin it rather than pre-empt it.
# --------------------------------------------------------------------------- #
def test_serializer_defers_to_a_resolvable_inner_ystring():
    # the ordinary case: the inner y-string resolves first, then the encode
    d = loads('base: "x"\ncfg:\n  p: y"{base}/1"\n  q: 8080\n'
              'out: y"j={cfg.__AS_JSON__()}"\n')
    assert d["out"] == 'j={"p": "x/1", "q": 8080}'


@pytest.mark.parametrize("src", [
    # two calls, each encoding the block the other sits in
    'b1:\n  m: y"{__ROOT__.b2.__AS_JSON__()}"\nb2:\n  m: y"{__ROOT__.b1.__AS_JSON__()}"\n',
    # and a three-way ring, so the fix is not special-cased to pairs
    'a:\n  m: y"{__ROOT__.b.__AS_JSON__()}"\n'
    'b:\n  m: y"{__ROOT__.c.__AS_JSON__()}"\n'
    'c:\n  m: y"{__ROOT__.a.__AS_JSON__()}"\n',
])
def test_mutually_referencing_serializers_report_a_cycle(src):
    with pytest.raises(AkanError) as e:
        loads(src)
    msg = str(e.value)
    assert "form a cycle" in msg
    # the old wrong message must not come back
    assert "cannot be serialized" not in msg


@pytest.mark.parametrize("src,needle", [
    ('xs: [y"{base}"]\nbase: "x"\nout: y"{xs.__AS_TOML__()}"\n',
     "a TOML document is a table"),
    ('base: "x"\ns:\n  p: y"{base}"\n  t: yt"{base}"\n'
     'out: y"{s.__AS_JSON__()}"\n', "yeeted yt"),
])
def test_refusals_survive_deferral(src, needle):
    # v0.3 serializers approximate rather than refuse, so the refusals left
    # are a signature and a template; deferring must not swallow either
    akan(src, needle)
