"""Key text and loaded mapping provenance — SPEC §7.

A key's value and whether it is a name are independent. Plain Python dicts
have no spelling; loaded mappings retain that one bit for `lookup`.
"""

import copy

from .lexer import KEYWORDS, is_dunder, is_identifier, reserved_fold


def name_key(key) -> bool:
    return (isinstance(key, str) and is_identifier(key)
            and key not in KEYWORDS and reserved_fold(key) is None
            and not is_dunder(key))


def key_error(key) -> str:
    if not isinstance(key, str):
        return "a key must be a string"
    if not key:
        return "an empty key is reserved; write a nonempty string"
    if key.startswith("@"):
        return "keys beginning with '@' are reserved for serializer metadata"
    if is_dunder(key):
        return (f"{key!r} cannot be a key: dunder names are reserved for "
                "yapyon; drop the leading and trailing '__'")
    try:
        key.encode("utf-8")
    except UnicodeEncodeError:
        return "a key cannot contain a lone surrogate"
    return ""


def is_named(mapping, key) -> bool:
    test = getattr(mapping, "_is_named", None)
    return test(key) if test is not None else name_key(key)


class KeyMap(dict):
    """A dict with key-kind provenance. Equality and indexing stay dict's.

    Replacing a value keeps its key's kind. New Python-added keys use the
    same rule as function results: writable identifiers are names. `copy`
    and unions preserve provenance; explicitly calling `dict` discards it.
    """

    def __init__(self, *args, **kwargs):
        if not hasattr(self, "_non_names"):
            self._non_names = set()
        self.update(*args, **kwargs)

    def _is_named(self, key):
        return key in self and key not in self._non_names and name_key(key)

    def _put(self, key, value, named):
        dict.__setitem__(self, key, value)
        if named:
            self._non_names.discard(key)
        else:
            self._non_names.add(key)

    def __setitem__(self, key, value):
        if not hasattr(self, "_non_names"):
            self._non_names = set()           # dict's pickle reconstruction
        self._put(key, value, key not in self._non_names and name_key(key))

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self._non_names.discard(key)

    def update(self, *args, **kwargs):
        if len(args) > 1:
            raise TypeError(f"update expected at most 1 argument, got {len(args)}")
        if args:
            other = args[0]
            if hasattr(other, "keys"):
                for key in other.keys():
                    named = self._is_named(key) if key in self else is_named(other, key)
                    self._put(key, other[key], named)
            else:
                for key, value in other:
                    self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def pop(self, key, *default):
        value = dict.pop(self, key, *default)
        self._non_names.discard(key)
        return value

    def popitem(self):
        key, value = dict.popitem(self)
        self._non_names.discard(key)
        return key, value

    def clear(self):
        dict.clear(self)
        self._non_names.clear()

    def copy(self):
        return type(self)(self)

    def __copy__(self):
        return self.copy()

    def __deepcopy__(self, memo):
        out = type(self)()
        memo[id(self)] = out
        for key, value in self.items():
            out._put(copy.deepcopy(key, memo), copy.deepcopy(value, memo),
                     self._is_named(key))
        return out

    @classmethod
    def fromkeys(cls, keys, value=None):
        return cls((key, value) for key in keys)

    def __ior__(self, other):
        self.update(other)
        return self

    def __or__(self, other):
        if not isinstance(other, dict):
            return NotImplemented
        out = self.copy()
        out.update(other)
        return out

    def __ror__(self, other):
        if not isinstance(other, dict):
            return NotImplemented
        out = type(self)(other)
        out.update(self)
        return out
