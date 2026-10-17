# §14.3-§14.5: a multimap is approximated in every format by that format's
# own means, never refused: a JSON-LD node, TOML dotted keys, a YAML %TAG
# handle onto !!pairs. Its lexemes live in the node's own table, keyed by
# entry (entries/1), not by key.
mm:
  + k: 1
  + k: 0x02
w:
  mm:
    + k: 1
    + k: 2
j: y"{mm.__AS_JSON__()}"
t: y"{__ROOT__.w.__AS_TOML__()}"
y: y"{mm.__AS_YAML__()}"
