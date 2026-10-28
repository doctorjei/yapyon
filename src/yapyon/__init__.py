"""yapyon — YAMLちゃうで。やぴょんやぴょん。

Python-style typed literals with YAML-like block structure.
Home: https://github.com/doctorjei/yapyon

    >>> import yapyon
    >>> yapyon.loads('name: "gw"\\nbanner: y"{name} v1"\\n')
    {'name': 'gw', 'banner': 'gw v1'}

**Conformance (SPEC §12.5): this is an assembly implementation**, so it
loads every tier, records included — `loads_record`, `load_record` and
`is_record` are the record surface.

**Identifier tables (GRAMMAR §G4.1): pinned to Unicode 14.0.0.** yapyon
ships its own table rather than asking `str.isidentifier()`, whose answer
depends on the interpreter, so a key means the same thing on every install.
`UNICODE_VERSION` is that pinned version.
"""

from ._xid import UNICODE_VERSION as _XID_UNICODE_VERSION
from .lexer import AkanError, Yakamashiwa
from .multimap import Entry, KeyView, OrderedMultimap
from .template import Hole, Template
from .loader import (is_record, load, load_record, loads, loads_record,
                    lookup, tier_of)
from .tree import Handle, Key, Tree, merge, parse, parse_file
from .emitter import emit
from .expand import expand_record
from .contract import Contract, load_contract, loads_contract
from .environment import (ENV_ALL, POSIX_STANDARD_ENV, STANDARD_ENV,
                          WINDOWS_STANDARD_ENV)

__version__ = "0.6.0.dev0"

#: GRAMMAR §G4.1 asks every implementation to document where its identifier
#: tables come from. yapyon's are generated from this Unicode version by
#: tools/gen_xid_table.py, and do not vary with the interpreter.
UNICODE_VERSION = _XID_UNICODE_VERSION

__all__ = [
    # what this install's identifier tables are (GRAMMAR §G4.1)
    "UNICODE_VERSION",
    # the everyday API
    "load", "loads", "Template", "Hole", "OrderedMultimap",
    # records — the fixed, literal-only form
    "load_record", "loads_record", "is_record",
    # a document read but not resolved: walk, merge, fill, resolve (SPEC §15)
    "parse", "parse_file", "Tree", "Handle", "Key", "merge",
    # §5.2's scope search over a loaded tree, for consumers that assemble one
    "lookup",
    # the environment a document may read (SPEC §5.1.3, §5.1.4)
    "STANDARD_ENV", "POSIX_STANDARD_ENV", "WINDOWS_STANDARD_ENV", "ENV_ALL",
    # contracts: the functions a document may call (SPEC §13.2)
    "load_contract", "loads_contract", "Contract",
    # the level a document needs to mean itself (python -m yapyon tier)
    "tier_of",
    # a record back to yapyon source (python -m yapyon record)
    "emit",
    # a full document resolved down to a record (python -m yapyon expand)
    "expand_record",
    # diagnostics
    "AkanError", "Yakamashiwa",
    # multimap internals
    "Entry", "KeyView",
]
