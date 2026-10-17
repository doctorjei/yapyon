"""Named serializers — SPEC §5.1.2, the format's built-in functions.

`{cfg.__AS_JSON__()}` is the author naming a container's encoding, exactly as
`b64"..."` names bytes→text: ehmon 5's bridge, for containers.

**Serializers are the format's built-in functions** (SPEC §5.1.2, §13.1):
called like any function, type-checked against the signatures declared in
`SERIALIZERS` below, and applied on the resolver's one call path. The set
belongs to the *format*, which is what makes them dunders: a contract
declares a consumer's functions, and no contract declares these.

This module is the **declaration**; the writers are `writers.py` (JSON,
YAML, TOML, §14) and `emitter.py` (yapyon, §14.6). Every writer reads the
resolved AST, because a lexeme decides what each format records beside a
value — and every writer is stdlib-only, by the rule the core keeps.

**Approximate, never refuse** (§5.1.2): a multimap, bytes, a non-decimal
integer, TOML's `None` — each is written as plain data the target format
can carry, with what it cannot say recorded beside it by that format's own
means. **yapyon does not prune**: dropping a key because its value is `None`
or `""` would be a silent reinterpretation (ehmon 7), so a consumer wanting
that prunes its own tree first. TOML's `None` is the one omission, and it is
recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .emitter import emit
from .writers import to_json, to_toml, to_yaml


def to_yapyon(node, *, warn=None) -> str:
    """**Record** text (SPEC §14.6, §12) for a resolved subtree: each
    value's lexeme, or its canonical form where it has none.

    This is `emitter.emit`, unchanged, and that is the point: the emitter
    already renders a record from the AST, and a second yapyon writer would
    be the next thing to drift. The caller has checked the subtree is fully
    resolved and holds no `yt` — the emitter's own refusal speaks of loading
    a record, which is the wrong problem to name from inside a hole.
    """
    return emit(node)


@dataclass(frozen=True)
class Builtin:
    """One built-in function (SPEC §5.1.2, §13.1): its writer, the §13.3
    type of its one positional parameter, and its keyword parameters as
    `name -> (type, default)`. A writer takes the resolved node, a `warn`
    callable for shiran, and the keywords."""
    write: Callable[..., str]
    takes: str
    keywords: dict = field(default_factory=dict)
    #: said after a mismatch on the argument itself, where the signature
    #: alone would not explain the refusal
    note: str = ""


SERIALIZERS = {
    "__AS_JSON__": Builtin(to_json, "Any", {"lexemes": ("bool", True)}),
    "__AS_TOML__": Builtin(to_toml, "dict[str, Any] | multimap[str, Any]",
                           {"lexemes": ("bool", True)},
                           note="a TOML document is a table, with no "
                                "top-level form for a list or a single value"),
    "__AS_YAML__": Builtin(to_yaml, "Any"),
    "__AS_YAPYON__": Builtin(to_yapyon, "Any"),
}

#: §5.1.2's one message for a `yt` reaching a record writer — every
#: serializer and `expand_record` alike, so they cannot come to disagree.
YEETED_YT = ("yeeted yt; a record cannot hold a template's unjoined parts. "
             "Use a y-string to join them.")

#: The names the grammar accepts (SPEC §5.1.2). **Derived** from `SERIALIZERS`
#: rather than restated: the two used to be written out separately, so a fourth
#: serializer could be added to one and missed in the other, and the comment
#: promising there was no second list sat directly above one. `lexer.parse_ref`
#: imports this rather than keeping a further list, and
#: `tools/check_ref_grammar.py` checks it against SPEC §5.1.2's table.
SERIALIZER_NAMES = tuple(SERIALIZERS)
