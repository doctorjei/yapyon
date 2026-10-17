# §5.1.2: __AS_YAPYON__ writes the block as a record, each value as written
# (§4.4): its lexeme, so 3.10 stays 3.10, b"hi" keeps its prefix, and 'single'
# keeps its quotes. None and a multimap's repeated keys survive too.
cfg:
  v: 3.10
  raw: b"hi"
  unset: None
  mm:
    + k: 1
    + k: 2
  who: 'single'
out: y"{cfg.__AS_YAPYON__()}"
