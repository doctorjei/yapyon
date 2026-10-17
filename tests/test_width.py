"""SPEC §14.1's width, pinned to Unicode 14.0.0 — tested independently of
the host's own Unicode (trap 12: a test of host-derived behavior passes on
the host it was written on)."""

import unicodedata

import pytest

from yapyon._wcwidth import UNICODE_VERSION, WIDE, ZERO
from yapyon._width import char_width, text_width


def test_the_pin_is_the_identifier_pin():
    from yapyon._xid import UNICODE_VERSION as XID
    assert UNICODE_VERSION == XID == "14.0.0"


@pytest.mark.parametrize("ch,width", [
    ("a", 1), (" ", 1), ("é", 1), ("\u0301", 0),     # combining acute: Mn
    ("\u20dd", 0),                                     # enclosing circle: Me
    ("\u200d", 0), ("\u00ad", 0),                      # ZWJ, soft hyphen: Cf
    ("\u115f", 0),                                     # Hangul filler: DICP
    ("中", 2), ("ｎ", 2), ("ﾅ", 1), ("ア", 2),          # W, F, H, W
    ("😀", 2), ("❤", 1), ("㐀", 2),
    ("\U0002fffd", 2),                                 # unassigned, Plane 2: W
    ("\U0001fae8", 1),                                 # new in Unicode 15: N here
    ("\U000e0001", 0),                                 # language tag: Cf
])
def test_char_width(ch, width):
    assert char_width(ch) == width


@pytest.mark.parametrize("text,width", [
    ("", 0), ("abc", 3), ("e\u0301", 1), ("中文", 4),
    ("❤\ufe0f", 2),                # U+FE0F makes the character before it 2
    ("😀\ufe0f", 2),               # already 2, stays 2
    ("a❤\ufe0fb", 4),
    ("\ufe0f", 0),                 # nothing before it to widen
    ("👩\u200d💻", 4),              # a ZWJ sequence overcounts; never under
])
def test_text_width(text, width):
    assert text_width(text) == width


def test_wide_is_disjoint_from_zero():
    zero = {c for lo, hi in ZERO for c in range(lo, hi + 1)}
    assert not any(c in zero for lo, hi in WIDE for c in range(lo, hi + 1))


def test_the_table_agrees_with_the_host_only_where_both_are_14():
    # A subset check, never equality: characters assigned in Unicode 14 and
    # still W/F on this host must be wide here. A newer host may widen more.
    for lo, hi in WIDE[:200]:
        for c in range(lo, min(hi, lo + 50) + 1):
            ch = chr(c)
            if unicodedata.category(ch) != "Cn":
                assert unicodedata.east_asian_width(ch) in "WF", hex(c)
