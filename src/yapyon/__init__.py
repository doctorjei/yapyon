"""yapyon — YAMLちゃうで。やぴょんやぴょん。

Python-style typed literals with YAML-like block structure.
See SPEC.md; CLAUDE.md holds the design rationale.
"""

from .lexer import Lexer, Token, tokenize, AkanError, Yakamashiwa
from .parser import (Mapping, MultiMap, Node, Pair, Parser, Scalar, Sequence,
                     YString, dump, parse, parse_tokens)
from .resolver import Resolver, resolve

__version__ = "0.1.0.dev0"
__all__ = [
    "Lexer", "Token", "tokenize", "AkanError", "Yakamashiwa",
    "Parser", "parse", "parse_tokens", "dump",
    "Node", "Scalar", "YString", "Pair", "Mapping", "Sequence", "MultiMap",
    "Resolver", "resolve",
]
