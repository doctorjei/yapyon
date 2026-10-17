# §5.1.2: __AS_YAPYON__ writes the block as a record in canonical spelling
# (§4.4). It keeps the lexeme (3.10, not 3.1), the bytes prefix the document
# chose, None, and a multimap's repeated keys -- each of which at least one
# of the other three serializers refuses. 'single' comes out double-quoted.
cfg:
  v: 3.10
  raw: b"hi"
  unset: None
  mm:
    + k: 1
    + k: 2
  who: 'single'
out: y"{cfg.__AS_YAPYON__()}"
