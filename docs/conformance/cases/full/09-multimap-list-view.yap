# §5.2: a multimap key names the whole list view, in order — 0, 1 or N
# entries. Indexing the view is how you get one.
mm:
  + registry: "one"
  + registry: "two"
first: y"{mm.registry[0]}"
second: y"{mm.registry[1]}"
both: y"{mm.registry[0]}|{mm.registry[1]}"
