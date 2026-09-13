"""yapyon — YAMLちゃうで。やぴょんやぴょん。

Python-style typed literals with YAML-like block structure.
Home: https://github.com/doctorjei/yapyon

    >>> import yapyon
    >>> yapyon.loads('name: "gw"\\nbanner: y"{name} v1"\\n')
    {'name': 'gw', 'banner': 'gw v1'}

**Conformance (SPEC §12.5): this implementation provides the full form**,
and therefore also loads yapyon records — `loads_record`, `load_record` and
`is_record` are the record surface.

**Identifier tables (SPEC §7): Unicode 14.0.0 is the guaranteed floor.**
yapyon uses `str.isidentifier()`, so the tables are the host interpreter's;
the floor is Python 3.11's, 3.11 being the oldest supported. A newer Python
additionally accepts codepoints assigned after Unicode 14.
"""

from .lexer import Lexer, Token, tokenize, AkanError, Yakamashiwa
from .parser import (Mapping, MultiMap, Node, Pair, Parser, Scalar, Sequence,
                     YString, dump, parse, parse_tokens)
from .resolver import Resolver, resolve
from .multimap import Entry, KeyView, OrderedMultimap
from .template import Template
from .loader import build, is_record, load, load_record, loads, loads_record

__version__ = "0.1.0a2"
__all__ = [
    # the everyday API
    "load", "loads", "build", "Template", "OrderedMultimap",
    # records — the fixed, literal-only form
    "load_record", "loads_record", "is_record",
    # diagnostics
    "AkanError", "Yakamashiwa",
    # the stages, for tools that want them
    "Lexer", "Token", "tokenize",
    "Parser", "parse", "parse_tokens", "dump",
    "Resolver", "resolve",
    # AST
    "Node", "Scalar", "YString", "Pair", "Mapping", "Sequence", "MultiMap",
    # multimap internals
    "Entry", "KeyView",
]
