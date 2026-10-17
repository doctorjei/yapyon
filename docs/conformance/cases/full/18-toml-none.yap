# §14.5: TOML has no null, so a None in a table leaves its key out and is
# recorded; in an array a stand-in keeps every later index in place.
s:
  a: None
  b: 1
  xs: [None, 2]
out: y"{s.__AS_TOML__()}"
