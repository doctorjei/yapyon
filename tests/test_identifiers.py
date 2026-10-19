"""The identifier rule (GRAMMAR §G4.1, SPEC §7), one test per clause.

Decided 2026-09-26: names use a pinned Unicode 14 table, exclude invisible
characters, and are *the same name* after width folding then NFC -- with no
other NFKC merge, and reserved words spelled exactly one way.
"""

import pytest

from yapyon import AkanError, emit, loads, parse
from yapyon._xid import XID_CONTINUE, XID_IGNORED, XID_START
from yapyon.lexer import fold_name, id_start, is_identifier


def akan(text, needle=""):
    with pytest.raises(AkanError) as e:
        loads(text)
    assert needle in str(e.value), f"wrong message: {e.value}"


def points(table):
    for lo, hi in table:
        yield from range(lo, hi + 1)


# --------------------------------------------------------------------------- #
# The table: Unicode 14, pinned, invisible characters removed
# --------------------------------------------------------------------------- #
def test_the_table_is_a_subset_of_every_supported_host():
    # XID membership is stable across Unicode versions, and every supported
    # Python carries Unicode 14 or later, so the host must agree with every
    # entry. This is the check that the generated table is not garbage.
    for cp in points(XID_START):
        assert chr(cp).isidentifier(), f"U+{cp:04X}"
    for cp in points(XID_CONTINUE):
        assert ("a" + chr(cp)).isidentifier(), f"U+{cp:04X}"


def test_the_table_holds_no_invisible_character():
    for cp in (0x200C, 0x200D, 0x034F, 0x115F, 0x3164, 0xFFA0, 0xFE0F,
               0x180B, 0x17B4, 0xE0100):
        assert not id_start(chr(cp)) and not is_identifier("a" + chr(cp)), \
            f"U+{cp:04X}"
    # and the diagnostics list is exactly what was removed
    assert not any(is_identifier("a" + chr(cp)) for cp in points(XID_IGNORED))


def test_the_newer_than_the_pin_message_is_the_same_on_every_host():
    # Found 2026-10-19 by running the suite on Python 3.11, whose Unicode is
    # 14.0.0: the hint asked the host's isidentifier() and printed the
    # host's character name, so 3.11 and 3.13 gave different text (trap 12).
    with pytest.raises(AkanError) as e:
        loads("\U00011F04: 1")
    assert ("U+11F04 is not in Unicode 14.0.0, which yapyon's names are "
            "pinned to") in str(e.value)
    assert "KAWI" not in str(e.value)        # a 3.11 host has no name for it


def test_the_unassigned_table_agrees_with_the_host_only_as_a_subset():
    # Whatever this host calls unassigned was unassigned in 14 as well; the
    # reverse need not hold on a newer host.
    import unicodedata
    from yapyon._xid import UNASSIGNED
    lows = [lo for lo, _ in UNASSIGNED]
    from bisect import bisect_right
    def pinned_unassigned(cp):
        i = bisect_right(lows, cp) - 1
        return i >= 0 and cp <= UNASSIGNED[i][1]
    for cp in range(0, 0x30000, 7):
        if unicodedata.category(chr(cp)) == "Cn":
            assert pinned_unassigned(cp), hex(cp)


def test_a_character_newer_than_unicode_14_is_refused_on_every_host():
    # U+11F04 KAWI LETTER A arrived in Unicode 15. Python 3.13 calls it an
    # identifier; the pin does not, so the answer no longer varies.
    akan("\U00011F04: 1", "pinned to")


@pytest.mark.parametrize("key, cp", [
    ("\u3164", "U+3164"),              # a key that is *only* a Hangul filler
    ("b\ufe0f", "U+FE0F"),             # b plus an emoji variation selector
    ("a\u034fb", "U+034F"),            # combining grapheme joiner
    ("a\u200cb", "U+200C"),            # ZWNJ: not an identifier char in 14
])
def test_an_invisible_character_in_a_key_is_akan(key, cp):
    akan(f"{key}: 1", f"{cp}")


def test_an_invisible_character_in_a_hole_is_akan():
    akan('ab: 1\nv: y"{a\u200db}"', "is invisible")


# --------------------------------------------------------------------------- #
# Identity: width folding, then NFC
# --------------------------------------------------------------------------- #
def test_fullwidth_and_ascii_are_the_same_name():
    doc = loads('ｎａｍｅ: 1\nv: y"{name}"\nw: y"{ｎａｍｅ}"\n')
    assert doc == {"name": 1, "v": "1", "w": "1"}


def test_two_spellings_of_one_name_are_a_duplicate_key():
    akan("ｎａｍｅ: 1\nname: 2\n",
         "duplicate key 'name' (first defined on line 1; written 'ｎａｍｅ' "
         "there and 'name' here)")


def test_halfwidth_katakana_folds_to_standard_katakana():
    assert loads("ｶﾞｲﾄﾞ: 1") == {"ガイド": 1}


def test_width_folds_before_nfc():
    # Halfwidth ﾞ unfolds to a *combining* voiced mark; only NFC afterwards
    # composes カ + U+3099 into ガ. The other order leaves it decomposed.
    assert fold_name("ｶﾞ") == "\u30ac"


def test_decomposed_and_precomposed_are_the_same_name():
    doc = loads('cafe\u0301: 1\nv: y"{caf\u00e9}"\n')
    assert doc == {"caf\u00e9": 1, "v": "1"}


def test_no_other_nfkc_merge():
    # ﬁ and fi look different; merging them is the silent collision the
    # 2026-09-09 door refused, and it still stands.
    assert loads("ﬁle: 1\nfile: 2\n") == {"ﬁle": 1, "file": 2}


def test_folding_keeps_every_name_a_name():
    # Identity must never leave the identifier set: fold every table
    # character in continue position and in start position.
    for cp in points(XID_CONTINUE):
        assert is_identifier(fold_name("a" + chr(cp))), f"U+{cp:04X}"
    for cp in points(XID_START):
        assert is_identifier(fold_name(chr(cp))), f"U+{cp:04X}"


def test_a_name_is_judged_as_written_then_folded():
    # As in Python: `＿` may continue a name but not start one, even though
    # it folds to `_`. Inside a name it folds like any other width variant.
    akan("＿x: 1", "cannot start a name")
    assert loads('x＿: 1\nv: y"{x_}"\n') == {"x_": 1, "v": "1"}


def test_a_key_in_brackets_or_through_a_reference_folds_too():
    # A resolved key means what a written one means.
    assert loads('d:\n  name: 7\nv: y"{d[\'ｎａｍｅ\']}"\n')["v"] == "7"
    assert loads('d:\n  name: 7\np: "ｎａｍｅ"\nv: y"{d[p]}"\n')["v"] == "7"


def test_multimap_keys_fold():
    doc = loads('m:\n  + ｎａｍｅ: 1\n  + name: 2\nv: y"{m.name[0]}"\n')
    assert [k for k, _ in doc["m"]] == ["name", "name"]
    assert doc["v"] == "1"      # the fullwidth entry is in the `name` view


def test_the_emitter_writes_the_key_as_spelled():
    # SPEC §7 / §4.4 v0.3 (operator, 2026-10-12, "lexemes everywhere"): the
    # identity is folded, the spelling is kept
    assert emit(parse("ｎａｍｅ: 1\n")) == "ｎａｍｅ: 1\n"


# --------------------------------------------------------------------------- #
# Reserved words have exactly one spelling
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("doc, word", [
    ("Ｔｒｕｅ: 1", "'True'"),                 # a keyword, fullwidth
    ("x: Ｎｏｎｅ", "'None'"),
    ('x: ｂ"s"', "'b'"),                      # a string prefix, fullwidth
    ("_＿ROOT＿_: 1", "'__ROOT__'"),           # a dunder, part fullwidth
    ('a: 1\nv: y"{_＿ROOT＿_.a}"', "'__ROOT__'"),
])
def test_a_reserved_word_in_another_spelling_is_akan(doc, word):
    akan(doc, f"another spelling of {word}")
