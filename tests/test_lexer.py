"""Lexer tests — one test per spec rule, named after the rule.

When a test and the implementation disagree, check SPEC.md before changing
either.
"""

import pytest

from yapyon.lexer import tokenize, AkanError


def kinds(text):
    return [t.kind for t in tokenize(text)]


def value(text, kind=None):
    """The first token of `kind` (or the first value-ish token)."""
    for t in tokenize(text):
        if kind and t.kind == kind:
            return t.value
        if not kind and t.kind not in ("NAME", "COLON", "NEWLINE", "EOF",
                                       "INDENT", "DEDENT", "DASH"):
            return t.value
    raise AssertionError("no such token")


def akan(text, needle=""):
    with pytest.raises(AkanError) as e:
        tokenize(text)
    assert needle in str(e.value), f"wrong message: {e.value}"


# --------------------------------------------------------------------------- #
# SPEC §2 — lexical structure
# --------------------------------------------------------------------------- #
def test_basic_map_token_kinds():
    assert kinds('name: "x"') == ["NAME", "COLON", "STRING", "NEWLINE", "EOF"]


def test_comments_and_blank_lines_emit_nothing():
    assert kinds("# lead\n\na: 1\n\n# trail\n") == [
        "NAME", "COLON", "INT", "NEWLINE", "EOF"]


def test_keywords():
    assert value("a: True", "KEYWORD") is True
    assert value("a: None", "KEYWORD") is None


def test_indent_dedent_balance():
    ks = kinds('server:\n  host: "h"\n  port: 1\nname: "x"\n')
    assert ks.count("INDENT") == 1 and ks.count("DEDENT") == 1


def test_tab_in_indentation_is_akan():
    akan("a:\n\tb: 1\n", "tab")


def test_indent_matching_no_open_block_is_akan():
    akan("a:\n    b: 1\n  c: 2\n", "matches no open block")


# --------------------------------------------------------------------------- #
# SPEC §2 — dash frames
# --------------------------------------------------------------------------- #
def test_dash_frames_open_and_close():
    ks = kinds('servers:\n  - name: "w1"\n    port: 1\n  - name: "w2"\n')
    assert ks.count("DASH") == 2
    assert ks.count("INDENT") == ks.count("DEDENT") == 3   # block + 2 frames


def test_nested_dash_stacks_frames():
    assert kinds('- - "x"\n').count("DASH") == 2


# --------------------------------------------------------------------------- #
# SPEC §2 — flow suppression
# --------------------------------------------------------------------------- #
def test_newlines_and_indent_suppressed_inside_brackets():
    ks = kinds('tags: [\n  "a",\n  "b",\n]\n')
    assert ks.count("NEWLINE") == 1
    assert ks.count("INDENT") == 0


def test_unclosed_bracket_is_akan():
    akan('x: [1, 2\n', "unclosed bracket")


def test_unmatched_closer_is_akan():
    akan('x: 1]\n', "unmatched")


# --------------------------------------------------------------------------- #
# SPEC §4.1 — triple-quote dedent, anchored at the opening delimiter
# --------------------------------------------------------------------------- #
def test_dedent_by_anchor_column():
    doc = 'foo:\n    """Hello.\n    I\'m John."""\n'
    assert value(doc, "STRING") == "Hello.\nI'm John."


def test_blank_line_exempt_from_anchor():
    assert value('foo:\n  """a\n\n  b"""\n', "STRING") == "a\n\nb"


def test_indentation_deeper_than_anchor_survives():
    # the first content line sets the anchor; later, deeper lines keep the extra
    assert value('foo:\n  """a\n  b\n      deep"""\n', "STRING") == "a\nb\n    deep"


def test_outdent_past_anchor_is_akan():
    akan('foo:\n  """a\n      b\n  c"""\n', "outdents past the string")


def test_inline_multiline_is_legal_and_anchors_at_the_delimiter():
    # legal after a key; the anchor is the delimiter's column, so continuation
    # lines align under the \"\"\" (not under the first line's text)
    assert value('k: """a\n   b"""', "STRING") == "a\nb"


def test_inline_multiline_alignment_is_free():
    # both spellings are clean: the first content line sets the anchor
    assert value('k: """a\n   b"""', "STRING") == "a\nb"
    assert value('k: """a\n         b"""', "STRING") == "a\nb"


def test_newline_after_opening_delimiter_is_dropped():
    assert value('k:\n  """\n  a\n  b"""', "STRING") == "a\nb"


def test_closing_delimiter_may_not_outdent_past_the_content():
    akan('k: """a\n      b\n  """', "closing delimiter outdents")


def test_inline_triple_quote_without_line_breaks_is_legal():
    # the inline form's real use: embedded quotes, no escaping
    assert value('k: """He said "hi" to me"""', "STRING") == 'He said "hi" to me'


def test_dash_item_may_hold_a_multiline_string():
    assert value('items:\n  - """a\n    b"""', "STRING") == "a\nb"


def test_anchor_includes_the_prefix():
    t = [t for t in tokenize('k:\n  y"""{a}\n  b"""') if t.kind == "YSTR"][0]
    assert t.parts == [("hole", "a"), ("text", "\nb")]


def test_newline_in_single_line_string_is_akan():
    akan('x: "a\nb"', "newline")


# --------------------------------------------------------------------------- #
# SPEC §4.2 — escapes (Python's table minus \N{...}; unknown is akan)
# --------------------------------------------------------------------------- #
def test_escape_table():
    assert value(r'x: "a\n\t\x41\u00e9\\"', "STRING") == "a\n\tA\u00e9\\"


def test_unknown_escape_is_akan():
    akan(r'x: "\q"', "unknown escape")


def test_escaped_backslash_is_a_backslash():
    src = 'x: "abc' + chr(92)*2 + '"'      # x: "abc\\"
    assert value(src, "STRING") == "abc" + chr(92)


def test_dangling_backslash_is_akan():
    akan('x: "abc\\"\n', "dangling backslash")


def test_raw_string_keeps_backslashes():
    assert value(r'x: r"a\nb"', "STRING") == "a\\nb"


# --------------------------------------------------------------------------- #
# SPEC §3 — bytes
# --------------------------------------------------------------------------- #
def test_bytes_escapes():
    assert value(r'x: b"\x89PNG"', "BYTES") == b"\x89PNG"


def test_non_ascii_in_bytes_literal_is_akan():
    akan('x: b"é"', "non-ASCII")


def test_b64_decodes_at_parse_time():
    assert value('x: b64"aGVsbG8="', "BYTES") == b"hello"


def test_invalid_b64_is_akan():
    akan('x: b64"!!!"', "invalid base64")


def test_raw_bytes():
    assert value(r'x: rb"\d"', "BYTES") == rb"\d"


# --------------------------------------------------------------------------- #
# SPEC §4.3 — prefixes: canonical spellings only, per-prefix hints
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("src,needle", [
    ('x: f"h"', "no f-strings"),
    ('x: t"h"', "yeeted"),
    ('x: u"h"', "just remove it"),
    ('x: br"h"', "canonical order is rb"),
    ('x: yr"h"', "canonical order is ry"),
    ('x: yb64"aGk="', "reserved"),
    ('x: zz"h"', "use one of"),
])
def test_rejected_prefixes_name_their_fix(src, needle):
    akan(src, needle)


def test_whitespace_before_quote_is_not_a_prefix():
    # `b "x"` is two tokens, not a bytes literal
    assert kinds('a: b "x"')[2] == "NAME"


# --------------------------------------------------------------------------- #
# SPEC §5.1 — hole grammar
# --------------------------------------------------------------------------- #
def test_y_string_parts():
    t = tokenize('x: y"{host}/api"')[2]
    assert t.kind == "YSTR"
    assert t.parts == [("hole", "host"), ("text", "/api")]


def test_dotted_hole_and_brace_escape():
    t = tokenize('x: y"{server.host} {{literal}}"')[2]
    assert t.parts == [("hole", "server.host"), ("text", " {literal}")]


def test_root_is_valid_first_segment_only():
    assert tokenize('x: y"{__ROOT__.host}"')[2].parts == [("hole", "__ROOT__.host")]
    akan('x: y"{a.__ROOT__}"', "first segment")


def test_other_dunders_are_reserved():
    akan('x: y"{__PARENT__}"', "reserved")


def test_non_identifier_hole_content_is_akan_with_quantifier_hint():
    akan('x: ry"a{2,3}"', "doubled braces")


def test_literals_in_holes_are_akan():
    akan('x: y"{8080}"', "identifier")


def test_unclosed_hole_and_lone_brace_are_akan():
    akan('x: y"{host"', "unclosed hole")
    akan('x: y"a}b"', "lone")


def test_yb_holes_over_bytes():
    t = tokenize('x: yb"*{count}\\r\\n"')[2]
    assert t.kind == "YBSTR"
    assert t.parts[0] == ("text", b"*")
    assert t.parts[1] == ("hole", "count")


def test_ry_is_raw_with_live_holes():
    t = tokenize('x: ry"^{prefix}\\d+"')[2]
    assert t.parts == [("text", "^"), ("hole", "prefix"), ("text", "\\d+")]


def test_yt_produces_template_token():
    t = tokenize('x: yt"Hello {user}!"')[2]
    assert t.kind == "YTSTR" and ("hole", "user") in t.parts


def test_plain_strings_are_inert():
    assert value('x: "{name}"', "STRING") == "{name}"


# --------------------------------------------------------------------------- #
# SPEC §3 — numbers, with lexeme preserved for splicing
# --------------------------------------------------------------------------- #
def test_numeric_zoo():
    vals = [t.value for t in tokenize("a: [0xFF, 1_000, -5, 1e-3, .5]")
            if t.kind in ("INT", "FLOAT")]
    assert vals == [255, 1000, -5, 0.001, 0.5]


def test_float_lexeme_is_preserved():
    t = next(t for t in tokenize("ratio: 3.10") if t.kind == "FLOAT")
    assert t.value == 3.1 and t.prefix == "3.10"   # TODO: rename to .lexeme


def test_malformed_number_is_akan():
    akan("a: 1__0", "malformed number")


def test_no_inf_nan_spelling():
    # `inf` is just a NAME (akan later, in value position, at the parser)
    assert kinds("a: inf")[2] == "NAME"
