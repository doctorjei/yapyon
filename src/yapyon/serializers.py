"""Named serializers — SPEC §5.1.2.

`{cfg.__AS_JSON__()}` is the author naming a container's encoding, exactly as
`b64"..."` names bytes→text. Law 5's bridge, for containers.

**A serializer is an encoding, not a function.** No arguments, no composition,
and this set belongs to the *format* — which is the boundary between these and
consumer-registered functions. Naming an encoding is not computing a value.

Stdlib only, by the same rule as the rest of the core. `tomllib` reads TOML and
cannot write it, and there is no YAML in the stdlib at all, so the TOML and
YAML writers here are ours. That is not a hardship: emitting a plain data tree
is a small job, and it keeps yapyon dependency-free.

**yapyon does not prune.** persona-grata's engine — whose serializers this
follows, GPL-3.0-or-later both sides — drops `None`, `""` and emptied
containers on the way out, implementing its own schema's "not sent if unset"
convention. That is a *consumer policy* and yapyon must not adopt it: dropping
a key the document wrote is a silent reinterpretation (law 7), and "the same
bytes mean the same data" has to survive the trip through a serializer. A
consumer wanting that behaviour prunes its own tree first.

Where a format cannot carry a value **faithfully**, the encoding is akan
rather than approximate — TOML has no null, JSON has no bytes, no format here
can hold a multimap's repeated keys. Law 1: refuse rather than pick a reading.
"""

from __future__ import annotations

import json
import re

#: Serializers are declared once, at the foot of this module: `SERIALIZERS` maps
#: each name to its writer, and `SERIALIZER_NAMES` is derived from it. Declared
#: there rather than here because the values are the writers, which must exist
#: first.


class NotEncodable(Exception):
    """This value has no faithful encoding in that format, and why."""


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #
def to_json(value) -> str:
    """Indented JSON, keys in document order.

    Indented rather than compact because the use these exist for is writing a
    config file that something else will read — and, often, that a person will
    open. Key order is the document's and never sorted: order is data here.
    """
    _refuse_bytes(value, "JSON")
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)


# --------------------------------------------------------------------------- #
# TOML
# --------------------------------------------------------------------------- #
_TOML_BARE = re.compile(r"[A-Za-z0-9_-]+")


def to_toml(value) -> str:
    """TOML, nesting mappings into tables.

    A TOML document *is* a table, so the top level must be a mapping. `None`
    is akan: TOML has no null, and persona-grata only avoids meeting one
    because it prunes first.
    """
    if not isinstance(value, dict):
        raise NotEncodable(f"a TOML document is a table, so __AS_TOML__() "
                           f"needs a mapping, not a "
                           f"{type(value).__name__}")
    out: list[str] = []
    _toml_table(value, [], out)
    return "\n".join(out).strip() + "\n"


def _toml_table(data: dict, prefix: list, out: list) -> None:
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    # A super-table holding nothing but sub-tables needs no header of its own.
    if prefix and (scalars or not tables):
        out.append("[" + ".".join(_toml_key(k) for k in prefix) + "]")
    for key, val in scalars.items():
        out.append(f"{_toml_key(key)} = {_toml_value(val)}")
    for key, val in tables.items():
        if out and out[-1] != "":
            out.append("")
        _toml_table(val, prefix + [key], out)


def _toml_key(key: str) -> str:
    return key if _TOML_BARE.fullmatch(key) else _toml_str(key)


def _toml_str(text: str) -> str:
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _toml_value(value) -> str:
    if value is None:
        raise NotEncodable("TOML has no null, so None cannot be written "
                           "faithfully; give the key a value or leave it out "
                           "of the subtree you serialize")
    if isinstance(value, bool):            # before int: bool subclasses int
        return "true" if value else "false"
    if isinstance(value, (bytes, bytearray)):
        raise NotEncodable("TOML has no bytes and names no encoding for them "
                           "(law 5); spell the text you want")
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return _toml_str(value)


# --------------------------------------------------------------------------- #
# YAML
# --------------------------------------------------------------------------- #
# A plain (unquoted) YAML scalar is only safe when nothing else could read it
# as a different type. yapyon exists partly because YAML guesses here, so the
# emitter is deliberately conservative: quote unless provably inert. Over-
# quoting costs a reader nothing; under-quoting is the Norway problem.
_YAML_PLAIN = re.compile(r"[A-Za-z_][A-Za-z0-9_.@/+:-]*")
_YAML_RESERVED = {
    "y", "n", "yes", "no", "true", "false", "on", "off", "null", "none",
    "nan", "inf", "infinity", "~",
}


def to_yaml(value) -> str:
    """Block-style YAML, keys in declaration order, scalars never wrapped.

    Order is preserved rather than sorted so a rendered config reads in the
    order its document declares it, and a long scalar stays on one line — a
    folded URL is valid YAML but is no longer greppable in the file it lands
    in.
    """
    lines: list[str] = []
    _yaml_node(value, 0, lines)
    return "\n".join(lines) + "\n"


def _yaml_node(value, indent: int, lines: list) -> None:
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            lines.append(pad + "{}")
            return
        for key, val in value.items():
            if isinstance(val, (dict, list)) and val:
                lines.append(f"{pad}{_yaml_key(key)}:")
                _yaml_node(val, indent + 1, lines)
            else:
                lines.append(f"{pad}{_yaml_key(key)}: {_yaml_scalar(val)}")
        return
    if isinstance(value, list):
        if not value:
            lines.append(pad + "[]")
            return
        for item in value:
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}-")
                _yaml_node(item, indent + 1, lines)
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
        return
    lines.append(pad + _yaml_scalar(value))


def _yaml_key(key: str) -> str:
    return _yaml_scalar(key)


def _yaml_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):            # before int: bool subclasses int
        return "true" if value else "false"
    if isinstance(value, (bytes, bytearray)):
        raise NotEncodable("YAML has no bytes and names no encoding for them "
                           "(law 5); spell the text you want")
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (dict, list)):    # only reachable when empty
        return "{}" if isinstance(value, dict) else "[]"
    return _yaml_str(value)


def _yaml_str(text: str) -> str:
    # `:` is admitted inside a plain scalar but never before a space or at the
    # end, where YAML reads it as the key separator. That is what keeps a URL
    # unquoted -- and an unwrapped, unquoted endpoint is the whole point of
    # emitting block style for a config file someone will grep.
    if (_YAML_PLAIN.fullmatch(text)
            and ": " not in text and not text.endswith(":")
            and text.lower() not in _YAML_RESERVED
            and not _looks_numeric(text)):
        return text
    return "'" + text.replace("'", "''") + "'"


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- #
def _refuse_bytes(value, fmt: str) -> None:
    if isinstance(value, (bytes, bytearray)):
        raise NotEncodable(f"{fmt} has no bytes and names no encoding for "
                           f"them (law 5); spell the text you want")
    if isinstance(value, dict):
        for val in value.values():
            _refuse_bytes(val, fmt)
    elif isinstance(value, list):
        for val in value:
            _refuse_bytes(val, fmt)


SERIALIZERS = {
    "__AS_JSON__": to_json,
    "__AS_TOML__": to_toml,
    "__AS_YAML__": to_yaml,
}

#: The names the grammar accepts (SPEC §5.1.2). **Derived** from `SERIALIZERS`
#: rather than restated: the two used to be written out separately, so a fourth
#: serializer could be added to one and missed in the other, and the comment
#: promising there was no second list sat directly above one. `lexer.parse_ref`
#: imports this rather than keeping a further list, and
#: `tools/check_ref_grammar.py` checks it against GRAMMAR §G5's production.
SERIALIZER_NAMES = tuple(SERIALIZERS)
