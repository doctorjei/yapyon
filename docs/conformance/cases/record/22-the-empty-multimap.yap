# GRAMMAR §G6 / SPEC §7.1: {+} is the empty multimap and {} the empty mapping;
# the two are never equal. Whitespace between the three tokens is layout.
mm: { + }
map: {}
nested:
  + k: {+}
