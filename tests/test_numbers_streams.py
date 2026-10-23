"""Numbers are numbers; bytes are streams (SPEC §3, §3.1, §4.3; GRAMMAR
§G4.3, §G4.6). One test per rule, named after it.

The stream oracle is independent of the lexer: each spelling's bits are
written out here from the grammar's alphabet table, so a decoder bug cannot
agree with itself (trap 10).
"""

import sys

import pytest

from yapyon import AkanError, emit, loads, loads_record
from yapyon.parser import parse
from yapyon._digits import REFUSE_DIGITS, WARN_DIGITS


def value(literal, **kw):
    return loads(f"a: {literal}\n", **kw)["a"]


def akan(literal, needle="", **kw):
    with pytest.raises(AkanError) as e:
        loads(f"a: {literal}\n", **kw)
    assert needle in str(e.value), f"wrong message: {e.value}"


# --------------------------------------------------------------------------- #
# Integers: five radixes, PEP 515, signed and unbounded
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("literal,expected", [
    ("0b101", 5), ("0B101", 5), ("0q123", 27), ("0Q_3", 3), ("0o17", 15),
    ("0O17", 15), ("0x1f", 31), ("0X1F", 31), ("0z7Z", 255), ("0z7z", 255),
    ("0x_ff", 255), ("0z_7Z", 255), ("-0xff", -255), ("+0z1", 1),
    ("0xffffffff", 4294967295),          # never two's complement
    ("0x00ff", 255),                     # leading zeros mean nothing
    ("1_000", 1000), ("00", 0), ("-0", 0),
])
def test_integer_literals(literal, expected):
    assert value(literal) == expected and type(value(literal)) is int


def test_crockford_aliases_read_as_their_digits():
    assert value("0zO") == value("0zo") == 0
    assert value("0zI") == value("0zi") == value("0zL") == value("0zl") == 1


@pytest.mark.parametrize("literal", [
    "0x", "0x__f", "0xf_", "0b2", "0q4", "0o8", "0xg", "0zU", "0zu",
    "1__0", "1_", "007", "0_7",
])
def test_malformed_integers_are_akan(literal):
    akan(literal, "malformed number")


def test_a_name_character_glued_to_a_number_is_part_of_the_mistake():
    akan("1٣", "malformed number '1٣'")
    akan("1.5f", "malformed number '1.5f'")


def test_a_float_that_overflows_is_akan_not_infinity():
    # yapyon has no inf (§3); Python reads 1e400 as inf, which would be a
    # silent reinterpretation (ehmon 7)
    akan("1e400", "no infinity")
    akan("-1e400", "no infinity")


def test_negative_zero_float_keeps_its_sign():
    assert str(value("-0.0")) == "-0.0"


# --------------------------------------------------------------------------- #
# §3.1 long decimals: warn at 4,300 digits, refuse above the ceiling, and the
# host's own limit never decides
# --------------------------------------------------------------------------- #
def test_the_warn_threshold_is_the_spec_s_and_the_ceiling_four_times_it():
    assert WARN_DIGITS == 4300 and REFUSE_DIGITS == 17200


def test_at_the_threshold_there_is_no_shiran():
    seen = []
    assert value("7" * WARN_DIGITS, warn=seen.append) == int("7" * WARN_DIGITS)
    assert seen == []


def test_past_the_threshold_is_shiran_and_loads():
    seen = []
    n = value("9" * (WARN_DIGITS + 1), warn=seen.append)
    assert n == 10 ** (WARN_DIGITS + 1) - 1
    assert len(seen) == 1 and "4,301 digits" in seen[0]


def test_past_the_ceiling_is_akan_and_the_ceiling_moves():
    akan("1" * (REFUSE_DIGITS + 1), "ceiling of 17,200")
    assert value("1" * 20, max_digits=20) == int("1" * 20)
    akan("1" * 21, "ceiling of 20", max_digits=20)


def test_separators_and_sign_are_not_digits():
    seen = []
    value("-" + "1_" * WARN_DIGITS + "1", warn=seen.append)   # 4,301 digits
    assert "4,301 digits" in seen[0]


def test_the_host_s_digit_limit_does_not_change_meaning():
    # CPython 3.11+ refuses str(n) past 4,300 digits by default; yapyon's
    # conversions are its own, so loading, splicing, and writing all work
    if not hasattr(sys, "get_int_max_str_digits"):
        pytest.skip("host has no digit limit")
    digits = "8" * 9000
    d = loads(f"a: {digits}\nb: y\"{{a}}\"\n", warn=lambda m: None)
    assert d["b"] == digits
    assert emit(parse(f"a: {digits}\n", )) == f"a: {digits}\n"


def test_power_of_two_radixes_are_not_limited():
    seen = []
    assert value("0x" + "f" * 20000, warn=seen.append) == 16 ** 20000 - 1
    assert seen == []


# --------------------------------------------------------------------------- #
# Stream literals (§4.3): every spelling of b"hi", from SPEC's own table
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("literal", [
    "bin'0110100001101001'", "dna'CAATCAAC'", "oct'320644'", "hex'6869'",
    "c32'D1MG'", "b64'aGk='", 'b"hi"',
])
def test_every_spelling_of_hi(literal):
    assert value(literal) == b"hi"


@pytest.mark.parametrize("literal,expected", [
    # SPEC §4.3: streams fill from the left and pad at the end
    ("hex'badf00d'", bytes.fromhex("badf00d0")),
    ("bin'0101'", b"\x50"),
    ("dna'GAC'", b"\xe4"),
    ("hex''", b""), ("oct''", b""), ("c32''", b""),
])
def test_streams_are_padded_at_the_end(literal, expected):
    assert value(literal) == expected


@pytest.mark.parametrize("a,b", [
    ("hex'6869'", "hex'6869'".upper().replace("HEX", "hex")),
    ("dna'CAATCAAC'", "dna'caatcaac'"),
    ("c32'D1MG'", "c32'd1mg'"),
    ("c32'D1MG'", "c32'D1-MG'"),          # hyphens, c32 only
    ("c32'D1MG'", "c32'DIMG'"),           # I reads as 1
    ("hex'6869'", "hex' 68\t69 '"),       # whitespace between symbols
    ("hex'6869'", 'hex"""\n  68\n  69\n  """'),
])
def test_spellings_each_standard_accepts(a, b):
    assert value(a) == value(b)


def oracle(prefix, data):
    """The canonical symbols, written from GRAMMAR §G4.6's table by hand."""
    bits, alphabet = {"bin": (1, "01"), "dna": (2, "TCAG"),
                      "oct": (3, "01234567"), "hex": (4, "0123456789abcdef"),
                      "c32": (5, "0123456789ABCDEFGHJKMNPQRSTVWXYZ")}[prefix]
    stream = "".join(f"{byte:08b}" for byte in data)
    stream += "0" * (-len(stream) % bits)
    return "".join(alphabet[int(stream[i:i + bits], 2)]
                   for i in range(0, len(stream), bits))


@pytest.mark.parametrize("prefix", ["bin", "dna", "oct", "hex", "c32"])
@pytest.mark.parametrize("data", [b"", b"\x00", b"hi", b"\xff\x00\x81",
                                  bytes(range(256))])
def test_streams_round_trip_against_an_independent_encoder(prefix, data):
    assert value(f"{prefix}'{oracle(prefix, data)}'") == data


@pytest.mark.parametrize("literal,needle", [
    ("oct'32'", "2 oct symbols is not a count an encoder writes"),
    ("c32'D1M'", "3 c32 symbols is not a count"),
    ("oct'321'", "spell it oct'320'"),             # spare bit set
    ("c32'D1MH'", "spell it c32'D1MG'"),
    ("b64'aGl='", "non-canonical base64"),
    ("b64'aGk'", "padding, which is required"),
    ("hex'6g'", "'g' is not a hex symbol"),
    ("bin'2'", "'2' is not a bin symbol"),
    ("dna'X'", "'X' is not a dna symbol"),
    ("c32'U'", "'U' is not a c32 symbol"),
    ("hex'6-8'", "'-' is not a hex symbol"),       # hyphens are c32's alone
    ("hex'\\x41'", "'\\\\' is not a hex symbol"),   # no escapes
    ("hex'{a}'", "'{' is not a hex symbol"),       # no holes
    ("hex'68\u00a069'", "is not a hex symbol"),   # NBSP: whitespace is the grammar's
])
def test_malformed_streams_are_akan(literal, needle):
    akan(literal, needle)


def test_a_symbol_akan_points_at_the_symbol():
    with pytest.raises(AkanError) as e:
        loads("a: hex'68g9'\n")
    assert (e.value.line, e.value.col) == (1, 9)


def test_a_stream_keeps_its_lexeme_and_splices_as_bytes():
    assert emit(parse("a: dna'CAATCAAC'\n")) == "a: dna'CAATCAAC'\n"
    assert loads("a: hex'6869'\nb: y\"{a}\"\n")["b"] == "b'hi'"
    assert loads_record("a: c32'D1MG'\n") == {"a": b"hi"}
