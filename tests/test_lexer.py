"""Lexer tests — one test per spec rule, named after the rule.

When a test and the implementation disagree, check the spec before changing
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


def test_plus_frames_open_multimap_entries():
    ks = kinds('+ a: 1\n+ b: 2\n')
    assert ks.count("PLUS") == 2
    assert ks.count("INDENT") == ks.count("DEDENT") == 2


def test_frames_of_both_kinds_interleave():
    ks = kinds('- + a: 1\n')
    assert ks[:4] == ["DASH", "INDENT", "PLUS", "INDENT"]


def test_a_marker_needs_its_space():
    # `-5` and `+5` are signed numbers, not frames
    assert kinds("-5\n")[0] == "INT"
    assert kinds("+5\n")[0] == "INT"
    assert value("-5\n", "INT") == -5 and value("+5\n", "INT") == 5


def test_marker_away_from_line_start_names_its_rule():
    akan('a: + 1\n', "only at the start of a line's content")


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


def test_backslash_newline_is_a_line_continuation():
    # both characters go, exactly as in Python
    assert value('x: """one\\\ntwo"""', "STRING") == "onetwo"


def test_a_plain_newline_in_a_triple_quote_survives():
    # the contrast that makes the continuation worth having
    assert value('x: """one\ntwo"""', "STRING") == "one\ntwo"


def test_the_continuation_is_unreachable_in_a_single_line_string():
    # not by exception: §4.1's raw-newline akan fires first, so the two
    # rules never have to know about each other
    akan('x: "one\\\ntwo"', "newline in single-line string")


def test_a_raw_triple_quote_keeps_the_backslash_and_the_newline():
    # the continuation belongs to the escape table, not to """
    assert value('x: r"""one\\\ntwo"""', "STRING") == "one\\\ntwo"


def test_surrogate_escapes_are_akan():
    # SPEC §4.2: yapyon strings are sequences of Unicode scalar values
    akan(r'x: "\ud800"', "surrogate")
    akan(r'x: "\U0000DC00"', "surrogate")
    assert value(r'x: "\U0001F600"', "STRING") == "\U0001f600"


def test_escape_outside_the_byte_range_is_akan():
    akan(r'x: b"\777"', "outside the byte range")


def test_escapes_may_carry_high_bytes_into_a_bytes_literal():
    # the literal-character rule is about source text, not escape values
    assert value(r'x: b"\x89\xff"', "BYTES") == b"\x89\xff"


# --------------------------------------------------------------------------- #
# SPEC §10 — an akan points at the character that caused it
# --------------------------------------------------------------------------- #
def positions(text):
    with pytest.raises(AkanError) as e:
        tokenize(text)
    return e.value.line, e.value.col


def test_hole_akan_points_at_the_offending_brace():
    assert positions('x: y"aaa{2,3}"') == (1, 8)      # the '{', not the quote
    assert positions('x: y"abc{host"') == (1, 8)
    assert positions('x: y"abcd}ef"') == (1, 9)       # the lone '}'


def test_hole_positions_survive_escape_processing():
    # `\t` is two source columns but one character of the value
    assert positions(r'x: y"a\tb{2,3}"') == (1, 9)


def test_hole_positions_survive_block_string_dedent():
    doc = 'k:\n  y"""first\n  second {2,3} here"""'
    assert positions(doc) == (3, 9)


def test_escape_akan_points_at_the_backslash():
    assert positions(r'x: "abc\qdef"') == (1, 7)
    assert positions(r'x: "\ud800"') == (1, 4)


def test_escaped_backslash_is_a_backslash():
    src = 'x: "abc' + chr(92)*2 + '"'      # x: "abc\\"
    assert value(src, "STRING") == "abc" + chr(92)


def test_an_escaped_quote_does_not_close_the_string():
    # §4.2's table includes \" and \'. The scan must honour them, or the
    # literal ends at the escaped quote -- which is what used to happen:
    # `"x\"y"` akaned as a dangling backslash. Fixed 2026-09-14.
    assert value('x: "a\\"b"\n', "STRING") == 'a"b'
    assert value("x: 'a\\'b'\n", "STRING") == "a'b"
    assert value('x: b"a\\"b"\n', "BYTES") == b'a"b'


def test_an_escaped_quote_does_not_close_a_raw_string_either():
    # Python's rule: the backslash stays in the value but still stops the
    # quote from closing the literal. Scanning and unescaping are separate.
    assert value('x: r"a\\"b"\n', "STRING") == 'a\\"b'


def test_a_backslash_before_the_closing_quote_is_an_unterminated_string():
    # `x: "abc\"` is unterminated in Python too -- the escaped quote is
    # content, so the literal runs to the newline.
    akan('x: "abc\\"\n', "newline in single-line string")
    akan('x: "abc\\', "unterminated string")


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
    # __ROOT__, __PARENT__ and __KEY__ are defined; the rest of the namespace
    # is still yapyon's and still akan
    akan('x: y"{__AS_JSON__}"', "reserved")
    akan('x: y"{__FUTURE__.a}"', "reserved")


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
# SPEC §5.1 — holes are recognised before escapes decode
# --------------------------------------------------------------------------- #
def test_an_escape_that_produces_a_brace_is_content_not_structure():
    # the layering Python uses: f"\x7bname\x7d" is the six characters {name}
    t = tokenize(r'x: y"\x7bname\x7d"')[2]
    assert t.kind == "YSTR" and t.parts == [("text", "{name}")]


def test_a_backslash_before_a_brace_is_akan():
    akan(r'x: y"\{name}"', "backslash never escapes a brace")


def test_an_escaped_backslash_still_leaves_the_brace_structural():
    t = tokenize(r'x: y"\\{name}"')[2]
    assert t.parts == [("text", "\\"), ("hole", "name")]


def test_raw_y_strings_keep_the_backslash_and_the_hole():
    t = tokenize(r'x: ry"\d{name}"')[2]
    assert t.parts == [("text", "\\d"), ("hole", "name")]


def test_yb_text_parts_are_bytes_without_a_latin1_round_trip():
    t = tokenize(r'x: yb"\xff{n}\x00"')[2]
    assert t.parts == [("text", b"\xff"), ("hole", "n"), ("text", b"\x00")]


def test_format_specs_and_conversions_name_their_reservation():
    akan('x: y"{a:>5}"', "format specs and conversions are reserved")
    akan('x: y"{a!r}"', "format specs and conversions are reserved")


# --------------------------------------------------------------------------- #
# SPEC §8 — reserved tokens
# --------------------------------------------------------------------------- #
def test_document_markers_name_their_reservation():
    akan("---\na: 1\n", "'---' is reserved")
    akan("a: 1\n...\n", "'...' is reserved")


# --------------------------------------------------------------------------- #
# SPEC §3 — numbers, with lexeme preserved for splicing
# --------------------------------------------------------------------------- #
def test_numeric_zoo():
    vals = [t.value for t in tokenize("a: [0xFF, 1_000, -5, 1e-3, .5]")
            if t.kind in ("INT", "FLOAT")]
    assert vals == [255, 1000, -5, 0.001, 0.5]


def test_float_lexeme_is_preserved():
    t = next(t for t in tokenize("ratio: 3.10") if t.kind == "FLOAT")
    assert t.value == 3.1 and t.lexeme == "3.10"


def test_keyword_lexeme_is_preserved():
    # `True` and `None` splice as themselves (SPEC §5.4)
    t = next(t for t in tokenize("a: None") if t.kind == "KEYWORD")
    assert t.value is None and t.lexeme == "None"


def test_string_prefix_and_lexeme_are_separate_fields():
    t = next(t for t in tokenize('a: b64"aGk="') if t.kind == "BYTES")
    assert t.prefix == "b64" and t.lexeme == ""


def test_malformed_number_is_akan():
    akan("a: 1__0", "malformed number")


def test_no_inf_nan_spelling():
    # `inf` is just a NAME (akan later, in value position, at the parser)
    assert kinds("a: inf")[2] == "NAME"


# --------------------------------------------------------------------------- #
# SPEC §7 — names are Unicode identifiers (UAX #31: XID_Start | '_', then
# XID_Continue).  The same rule governs hole segments, so every key a
# document can write is a key a hole can name.
# --------------------------------------------------------------------------- #
def test_ascii_names():
    assert kinds("name: 1") == ["NAME", "COLON", "INT", "NEWLINE", "EOF"]
    assert kinds("_x: 1")[0] == "NAME"
    assert kinds("x1: 1")[0] == "NAME"


def test_names_outside_ascii():
    for name in ("名前", "やぴょん", "имя", "λ"):
        assert kinds(f"{name}: 1")[0] == "NAME"


def test_combining_marks_continue_a_name():
    # "é" as e + U+0301, the form macOS filesystems hand you.  A combining
    # mark is XID_Continue but not alphanumeric, so an isalnum() rule
    # rejected this.
    assert value("é: 1", "NAME") == "é"


def test_zero_width_joiner_continues_a_name():
    # ZWJ is XID_Continue; Persian and several Indic scripts need it.
    assert value("zwj‍x: 1", "NAME") == "zwj‍x"


def test_digits_outside_ascii_continue_a_name():
    # Arabic-Indic digits are XID_Continue, so they are legal inside a name…
    assert value("x٣: 1", "NAME") == "x٣"


def test_a_digit_cannot_start_a_name():
    # …but not at the front, and the akan says which of the two it is.
    akan("٣: 1", "cannot start a name")


def test_characters_no_identifier_admits_are_akan():
    # U+00B2 is alphanumeric to str.isalnum() but is not XID_Continue;
    # Python rejects `a² = 5` for the same reason.
    akan("a²: 1", "cannot appear in a name")


def test_names_are_not_nfkc_folded():
    # U+FB01 folds to "fi" under NFKC, which Python applies to identifiers
    # and yapyon does not: two keys here, one there (SPEC §11).
    toks = [t for t in tokenize("ﬁ: 1\nfi: 2\n") if t.kind == "NAME"]
    assert [t.value for t in toks] == ["ﬁ", "fi"]


def test_numbers_are_ascii_only():
    # str.isdigit() is True for U+0663, but a number literal is ASCII: the
    # akan must name the number, not send the reader hunting for a name.
    akan("a: 1٣", "malformed number")
