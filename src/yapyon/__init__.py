"""yapyon — YAMLちゃうで。やぴょんやぴょん。

Python-style typed literals with YAML-like block structure.
Home: https://github.com/doctorjei/yapyon

    >>> import yapyon
    >>> yapyon.loads('name: "gw"\\nbanner: y"{name} v1"\\n')
    {'name': 'gw', 'banner': 'gw v1'}

**Conformance (SPEC §12.5): this implementation provides the full form**,
and therefore also loads yapyon records — `loads_record`, `load_record` and
`is_record` are the record surface.

**Identifier tables (GRAMMAR §G4.1): pinned to Unicode 14.0.0.** yapyon
ships its own table rather than asking `str.isidentifier()`, whose answer
depends on the interpreter, so a key means the same thing on every install.
`UNICODE_VERSION` is that pinned version.
"""

from ._xid import UNICODE_VERSION as _XID_UNICODE_VERSION
from .lexer import Lexer, Token, tokenize, AkanError, Yakamashiwa
from .parser import (Mapping, MultiMap, Node, Pair, Parser, Scalar, Sequence,
                     ResolvedTemplate, YString, dump, parse,
                     parse_tokens)
from .resolver import Resolver, resolve
from .multimap import Entry, KeyView, OrderedMultimap
from .template import Hole, Template
from .loader import build, is_record, load, load_record, loads, loads_record
from .emitter import emit

__version__ = "0.1.0a4"

#: GRAMMAR §G4.1 asks every implementation to document where its identifier
#: tables come from. yapyon's are generated from this Unicode version by
#: tools/gen_xid_table.py, and do not vary with the interpreter.
UNICODE_VERSION = _XID_UNICODE_VERSION

__all__ = [
    # what this install's identifier tables are (GRAMMAR §G4.1)
    "UNICODE_VERSION",
    # the everyday API
    "load", "loads", "build", "Template", "Hole", "OrderedMultimap",
    # records — the fixed, literal-only form
    "load_record", "loads_record", "is_record",
    # a record AST back to canonical yapyon source (python -m yapyon.record)
    "emit",
    # diagnostics
    "AkanError", "Yakamashiwa",
    # the stages, for tools that want them
    "Lexer", "Token", "tokenize",
    "Parser", "parse", "parse_tokens", "dump",
    "Resolver", "resolve",
    # AST
    "Node", "Scalar", "YString", "ResolvedTemplate", "Pair", "Mapping",
    "Sequence", "MultiMap",
    # multimap internals
    "Entry", "KeyView",
]
