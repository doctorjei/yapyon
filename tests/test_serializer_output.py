"""SPEC §14: the exact text each serializer writes.

Expected strings are written from the spec's tables, and every output is
also read back by an independent reader — `json`, `tomllib`, PyYAML — so a
writer bug cannot hide behind an expectation copied from its own output.
"""

import json
import tomllib

import pytest

from yapyon import loads

yaml = pytest.importorskip("yaml")


def out(doc, call, name="s"):
    seen = []
    text = loads(f"{doc}u: y\"{{{name}.{call}}}\"\n", warn=seen.append)["u"]
    return text, seen


# --------------------------------------------------------------------------- #
# JSON (§14.3)
# --------------------------------------------------------------------------- #
def test_json_scalars_and_no_trailing_newline():
    text, _ = out('s:\n  t: True\n  n: None\n  i: -7\n  f: 1e16\n  g: 1e-5\n'
                  '  z: -0.0\n  big: 9007199254740993\n', "__AS_JSON__()")
    assert text == ('{"t": true, "n": null, "i": -7, "f": 1e+16, "g": 1e-05, '
                    '"z": -0.0, "big": 9007199254740993}')
    assert json.loads(text)["big"] == 9007199254740993


@pytest.mark.parametrize("value,written", [
    ('"q\\"b\\\\s"', r'"q\"b\\s"'),
    ('"\\x00\\x1f\\x7f"', '"\\u0000\\u001f\x7f"'),     # DEL as itself
    ('"\\b\\f\\n\\r\\t"', r'"\b\f\n\r\t"'),
    ('"café 日本 \\u2028"', '"café 日本 \u2028"'),     # everything else itself
])
def test_json_string_escapes(value, written):
    text, _ = out(f"s: {value}\n", "__AS_JSON__()")
    assert text == written


def test_a_broken_json_container():
    long = '"' + "x" * 90 + '"'
    text, _ = out(f's:\n  a: {long}\n  b:\n    c: [1, 2]\n', "__AS_JSON__()")
    assert text == ('{\n  "a": ' + long + ',\n  "b": {"c": [1, 2]}\n}')


def test_breaking_is_outermost_first_and_closers_sit_at_the_opening_indent():
    long = '"' + "y" * 95 + '"'
    text, _ = out(f's:\n  a:\n    b: {long}\n', "__AS_JSON__()")
    assert text == '{\n  "a": {\n    "b": ' + long + '\n  }\n}'


def test_width_counts_wide_characters_twice():
    narrow = "x" * 40                                 # {"a": [...]} is 95 wide
    wide = "中" * 40                                  # same length, 175 wide
    assert out(f's:\n  a: ["{narrow}", "{narrow}"]\n', "__AS_JSON__()")[0] \
        .count("\n") == 0
    assert out(f's:\n  a: ["{wide}", "{wide}"]\n', "__AS_JSON__()")[0] \
        .count("\n") > 0


def test_lexemes_are_the_last_member_keyed_by_path():
    text, _ = out("s:\n  port: 0xff\n  ports: [0x50, 443]\n"
                  "  matrix: [[1, 0b11]]\n  data: hex'6869'\n", "__AS_JSON__()")
    data = json.loads(text)
    assert list(data)[-1] == "@_lexemes"
    assert data["@_lexemes"] == {"port": "0xff", "ports/0": "0x50",
                                 "matrix/0/1": "0b11", "data": "hex'6869'"}
    assert data["data"] == "aGk=" and data["port"] == 255


def test_bytes_are_padded_base64url_with_a_lexeme_or_a_canonical_form():
    text, _ = out("s:\n  a: b\"\\xfb\\xff\"\n", "__AS_JSON__()")
    assert json.loads(text) == {"a": "-_8=",
                                "@_lexemes": {"a": 'b"\\xfb\\xff"'}}
    # a call's result has no lexeme: its canonical spelling is recorded
    text, _ = out("x: b64'aGk='\ns:\n  a: y\"{x}\"\n", "__AS_JSON__()")
    assert json.loads(text)["a"] == "b'hi'"            # a y-string is text


def test_a_multimap_node_is_json_ld_and_keys_its_lexemes_by_entry():
    text, _ = out("s:\n  + k: [1, 0x02]\n  + j: 0x03\n", "__AS_JSON__()")
    assert json.loads(text) == {
        "@type": "multimap",
        "entries": {"@list": [{"k": [1, 2]}, {"j": 3}]},
        "@_lexemes": {"entries/0/1": "0x02", "entries/1": "0x03"}}


def test_a_root_list_is_never_wrapped_and_its_lexemes_are_dropped_with_shiran():
    text, seen = out("s: [0xff, 1]\n", "__AS_JSON__()")
    assert text == "[255, 1]"
    assert len(seen) == 1 and "lexemes=False" in seen[0] and "0xff" in seen[0]


def test_lexemes_false_writes_none_and_says_nothing():
    text, seen = out("s: [0xff]\n", "__AS_JSON__(lexemes=False)")
    assert text == "[255]" and seen == []
    text, _ = out("s:\n  a: 0xff\n  b: {c: hex'68'}\n", "__AS_JSON__(lexemes=False)")
    assert "@_lexemes" not in text


def test_a_value_beside_no_lexemes_needs_no_record():
    text, _ = out("s:\n  a: 1_000\n  b: 3.10\n  c: 'x'\n", "__AS_JSON__()")
    assert text == '{"a": 1000, "b": 3.1, "c": "x"}'


# --------------------------------------------------------------------------- #
# YAML (§14.4)
# --------------------------------------------------------------------------- #
def test_yaml_with_no_marker_has_no_header():
    text, _ = out('s:\n  a: 1\n  b: "x"\n', "__AS_YAML__()")
    assert text == "a: 1\nb: x\n"


def test_yaml_handles_are_declared_in_order_of_first_use():
    text, _ = out("s:\n  data: hex'6869'\n  port: 0xff\n  bits: 0b101\n"
                  "  raw: b\"hi\"\n  mm:\n    + registry: \"a\"\n",
                  "__AS_YAML__()")
    assert text == ("%TAG !hex! tag:yaml.org,2002:\n"
                    "%TAG !x! tag:yaml.org,2002:\n"
                    "%TAG !b! tag:yaml.org,2002:\n"
                    "%TAG !multimap! tag:yaml.org,2002:\n"
                    "---\n"
                    'data: !hex!str "6869"\n'
                    "port: !x!int 0xff\n"
                    "bits: !b!int 0b101\n"            # one handle, two suffixes
                    'raw: !b!str "hi"\n'
                    "mm: !multimap!pairs\n"
                    "  - registry: a\n")
    data = yaml.safe_load(text)
    assert data == {"data": "6869", "port": 255, "bits": 5, "raw": "hi",
                    "mm": [("registry", "a")]}


@pytest.mark.parametrize("literal,written,read", [
    ("1e16", "1.0e+16", 1e16),          # the held bug: YAML 1.1 read 1e+16 as str
    ("1e-5", "1.0e-05", 1e-5),
    ("1.5e300", "1.5e+300", 1.5e300),
    ("-0.0", "-0.0", -0.0),
    ("0q33", "!q!int 15", 15),          # the value: YAML cannot read 0q
    ("0z7Z", "!z!int 255", 255),
    ("-0xff", "!x!int -0xff", -255),    # the lexeme, negatives included
    ("0XFF", "!x!int 0xFF", 255),       # prefix letter lowercased for readers
    ("b64'aGk='", '!!binary "aGk="', b"hi"),
    ("rb'\\d'", '!rb!str "\\\\d"', "\\d"),
])
def test_yaml_scalars(literal, written, read):
    text, _ = out(f"s:\n  a: {literal}\n", "__AS_YAML__()")
    assert text.splitlines()[-1] == f"a: {written}"
    assert yaml.safe_load(text)["a"] == read


def test_bytes_with_no_lexeme_are_binary():
    text, _ = out("x: b\"hi\"\ns:\n  a: y\"{x}\"\n  b: yb\"{x}\"\n", "__AS_YAML__()")
    assert text == 'a: "b\'hi\'"\nb: !!binary "aGk="\n'


@pytest.mark.parametrize("value", ["no", "Yes", "ON", "null", "~", "3", "1e3",
                                   "", "a b", "a: b", "-x", "#x", "日本",
                                   "tab\there", "line\nbreak", "\x85"])
def test_yaml_quotes_what_any_reader_might_misread(value):
    text, _ = out(f"s:\n  a: {json.dumps(value)}\n", "__AS_YAML__()")
    assert text.startswith('a: "')
    assert yaml.safe_load(text)["a"] == value


def test_a_flow_sequence_quotes_flow_indicators():
    text, _ = out('s:\n  a: ["x", "a,b", "c]", "d:e"]\n', "__AS_YAML__()")
    assert text == 'a: [x, "a,b", "c]", "d:e"]\n'
    assert yaml.safe_load(text)["a"] == ["x", "a,b", "c]", "d:e"]


def test_yaml_sequences_holding_mappings_are_block():
    text, _ = out('s:\n  a: [{x: 1}, 2]\n  b: [[1, 2], [3]]\n', "__AS_YAML__()")
    assert text == "a:\n  - x: 1\n  - 2\nb: [[1, 2], [3]]\n"


def test_a_root_multimap_in_yaml():
    text, _ = out("s:\n  + k: 1\n  + k: 2\n", "__AS_YAML__()")
    assert text == ("%TAG !multimap! tag:yaml.org,2002:\n---\n"
                    "!multimap!pairs\n- k: 1\n- k: 2\n")
    assert yaml.safe_load(text) == [("k", 1), ("k", 2)]


# --------------------------------------------------------------------------- #
# TOML (§14.5)
# --------------------------------------------------------------------------- #
def toml(doc):
    text, _ = out(doc, "__AS_TOML__()")
    return text, tomllib.loads(text)


def test_toml_reads_as_json_s_tree_but_for_null_and_64_bits():
    doc = ("s:\n  a: 1\n  n: None\n  big: 0x8000000000000000\n"
           "  sub:\n    b: hex'6869'\n")
    text, data = toml(doc)
    tree = json.loads(out(doc, "__AS_JSON__()")[0])
    del tree["n"]
    tree["big"] = str(tree["big"])
    tree["@_lexemes"]["n"] = "None"
    assert data == tree | {"@_lexemes": data["@_lexemes"]}
    assert data["@_lexemes"] == {"big": "0x8000000000000000", "n": "None"}


def test_an_integer_outside_64_bits_is_a_string_recorded_as_an_integer():
    text, data = toml(f"s:\n  a: {2 ** 64}\n  b: -9223372036854775808\n")
    assert data == {"a": str(2 ** 64), "b": -2 ** 63,
                    "@_lexemes": {"a": str(2 ** 64)}}


def test_lexemes_go_inline_when_they_fit_and_as_a_section_when_not():
    text, _ = toml("s:\n  a: 0xff\n")
    assert text == 'a = 255\n"@_lexemes" = {a = "0xff"}\n'
    keys = "".join(f"    k{i:02}: 0x{i:02x}\n" for i in range(8))
    text, data = toml(f"s:\n  srv:\n{keys}")
    assert '[srv."@_lexemes"]\nk00 = "0x00"' in text
    assert data["srv"]["@_lexemes"]["k07"] == "0x07"


def test_a_long_array_breaks_one_element_per_line():
    items = ", ".join(f'"value-{i:02}"' for i in range(10))
    text, data = toml(f"s:\n  xs: [{items}]\n")
    assert text.startswith('xs = [\n  "value-00",\n  "value-01",\n')
    assert text.endswith('  "value-09"\n]\n')       # no trailing comma
    assert len(data["xs"]) == 10


def test_an_inline_table_never_breaks():
    long = "z" * 120
    text, data = toml(f's:\n  xs: [{{a: "{long}"}}, 1]\n')   # mixed: inline
    assert '{a = "' + long + '"}' in text
    assert data["xs"][0]["a"] == long


def test_own_keys_come_before_sub_tables():
    text, _ = toml('s:\n  sub:\n    x: 1\n  a: 1\n  more:\n    - y: 2\n')
    assert text == 'a = 1\n\n[sub]\nx = 1\n\n[[more]]\ny = 2\n'


def test_a_multimap_in_a_table_is_dotted_and_at_the_root_is_top_level():
    text, data = toml('s:\n  mm:\n    + a: 1\n    + a: 0x2\n')
    assert text == ('mm."@type" = "multimap"\nmm.entries = [{a = 1}, {a = 2}]\n'
                    'mm."@_lexemes" = {"entries/1" = "0x2"}\n')
    text, data = toml('s:\n  + a: 1\n  + a: None\n')
    assert data == {"@type": "multimap", "entries": [{"a": 1}, {}],
                    "@_lexemes": {"entries/1": "None"}}


def test_keys_are_bare_only_when_toml_allows():
    text, data = toml('s:\n  ok_key1: 1\n  日本: 2\n')
    assert text == 'ok_key1 = 1\n"日本" = 2\n'


def test_toml_lexemes_false():
    text, _ = out("s:\n  a: 0xff\n  n: None\n", "__AS_TOML__(lexemes=False)")
    assert text == "a = 255\n"


# --------------------------------------------------------------------------- #
# yapyon (§14.6)
# --------------------------------------------------------------------------- #
def test_yapyon_output_keeps_every_lexeme_and_lays_out_by_14_1():
    text, _ = out("s:\n  v: 3.10\n  xs:\n    - 0xff\n    - 'q'\n  mm:\n    + k: 1\n",
                  "__AS_YAPYON__()")
    assert text == "v: 3.10\nxs: [0xff, 'q']\nmm:\n  + k: 1\n"
