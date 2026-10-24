# SPEC §5.1.5, §13.1, §5.6: __get__ is dict.get for mappings and lists and
# the list view for a multimap; ?. skips the rest of a chain on None; a
# value ending in a call may stand bare.
models: ["kimi-k3.1-pro", "kimi-k2.6"]
empty: []
mind: {model: "m"}
mm:
  + k: 1
  + k: 2
first: models.__get__(0)
last: models.__get__(-1)
missing: models.__get__(5, "none-yet")
ctx: mind.__get__("context", 8192)
view: mm.__get__("k")
nothing: empty.__get__(0)?.__str__()
