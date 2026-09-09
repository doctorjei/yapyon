"""yapyon — YAMLちゃうで。やぴょんやぴょん。

Python-style typed literals with YAML-like block structure.
See SPEC.md; CLAUDE.md holds the design rationale.
"""

from .lexer import Lexer, Token, tokenize, AkanError, Yakamashiwa

__version__ = "0.1.0.dev0"
__all__ = ["Lexer", "Token", "tokenize", "AkanError", "Yakamashiwa"]
