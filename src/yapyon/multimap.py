"""An ordered multimap — keyed entries, repeats allowed, timeline preserved.

Two indexes over the same `Entry` objects: `_seq` (id -> Entry) holds the
document order, `_by_key` (key -> {id: Entry}) holds each key's entries in
that same order.  Ids are monotonic, so a bucket sorted by id is sorted by
time; `rekey` re-sorts the destination bucket for exactly that reason.

**Conversions differ in how coupled they stay.**  `dict(mm)` and `{**mm}` go
through the mapping protocol (`keys()` + `__getitem__`), so they yield
**live** `KeyView`s: a view holds a key, not a value, and re-resolves its
bucket on every read.  It therefore tracks later inserts *and* replacements
in `mm` — including `mm[k] = v`, which plain shallow-copy intuition files
under "safe", since `dict(d)` does not notice `d[k] = v`.  `grouped()`
returns plain tuples of values and is decoupled; reach for it by default.
"""

from itertools import count


class Entry:
    __slots__ = ("_id", "_key", "value")

    def __init__(self, id, key, value):
        self._id, self._key, self.value = id, key, value

    @property
    def id(self): return self._id

    @property
    def key(self): return self._key  # read-only outside; only the container rekeys

    def __iter__(self): # lets `for k, v in mm:` work
        yield self._key; yield self.value

    def __repr__(self):
        return f"Entry({self._key!r}, {self.value!r})"


class KeyView:
    """Live view of one key's entries, in timeline order."""
    __slots__ = ("_mm", "_key")

    def values(self):
        return tuple(e.value for e in self)

    def _bucket(self):
        return self._mm._by_key.get(self._key, {})

    def __bool__(self):
        return bool(self._bucket())

    def __init__(self, mm, key):
        self._mm, self._key = mm, key

    def __iadd__(self, value):
        self._mm.insert(self._key, value)
        return self

    def __iter__(self):
        return iter(tuple(self._bucket().values()))   # snapshot, mutation-safe

    def __len__(self):
        return len(self._bucket())

    def __repr__(self):
        return f"KeyView({self._key!r}: {[e.value for e in self]})"


class OrderedMultimap:
    def __init__(self):
        self._ids = count()
        self._seq = {}  # id -> Entry
        self._by_key = {}  # key -> {id: Entry}

    def entry(self, i):
        return self._seq[i]

    def get(self, key, default=()):
        bucket = self._by_key.get(key)
        return default if bucket is None else tuple(bucket.values())

    def grouped(self):
        return {k: self[k].values() for k in self._by_key}

    def insert(self, key, value):
        e = Entry(next(self._ids), key, value)
        self._seq[e._id] = e
        self._by_key.setdefault(key, {})[e._id] = e
        return e

    def keys(self):  # with __getitem__, this is what routes dict(mm) through
        return tuple(self._by_key)  # the mapping protocol — see module docstring

    def remove(self, e):
        del self._seq[e._id]
        self._unindex(e._id, e._key)

    def rekey(self, e, new_key):
        if new_key == e._key:
            return
        self._unindex(e._id, e._key)
        e._key = new_key
        bucket = self._by_key.setdefault(new_key, {})
        bucket[e._id] = e
        if len(bucket) > 1:
            self._by_key[new_key] = dict(sorted(bucket.items()))

    def _unindex(self, i, key):
        bucket = self._by_key[key]
        del bucket[i]
        if not bucket:
            del self._by_key[key]

    def __delitem__(self, key):  # erase all entries for key
        bucket = self._by_key.pop(key)
        for i in bucket:
            del self._seq[i]

    def __getitem__(self, key):
        return KeyView(self, key)

    def __iter__(self):
        return iter(tuple(self._seq.values()))

    def __len__(self):
        return len(self._seq)

    def __contains__(self, key):
        return key in self._by_key

    def count(self, key):
        return len(self._by_key.get(key, ()))

    def __setitem__(self, key, value):
        if isinstance(value, KeyView):
            if value._mm is self and value._key == key:
                return                      # tail of `mm[key] += x`; already applied
            raise TypeError("cannot assign a KeyView of a different key")
        bucket = self._by_key.get(key)
        if bucket is None:
            self.insert(key, value)         # new key: appends, like a dict
            return
        first, *rest = bucket.values()      # existing key: keep first entry's slot,
        first.value = value                 # update it in place, drop the rest
        for e in rest:
            self.remove(e)

