"""yapyon — YAMLちゃうで。やぴょんやぴょん。

Python-style typed literals with YAML-like block structure.
See SPEC.md; CLAUDE.md holds the design rationale.

    >>> import yapyon
    >>> yapyon.loads('name: "gw"\\nbanner: y"{name} v1"\\n')
    {'name': 'gw', 'banner': 'gw v1'}
"""

from .lexer import Lexer, Token, tokenize, AkanError, Yakamashiwa
from .parser import (Mapping, MultiMap, Node, Pair, Parser, Scalar, Sequence,
                     YString, dump, parse, parse_tokens)
from .resolver import Resolver, resolve
from .multimap import Entry, KeyView, OrderedMultimap
from .template import Template
from .loader import build, load, loads

__version__ = "0.1.0.dev0"
__all__ = [
    # the everyday API
    "load", "loads", "build", "Template", "OrderedMultimap",
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
