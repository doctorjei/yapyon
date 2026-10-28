item: "outer"
left: ["a", "same"]
right: ["same", "b"]
rows:
  item: {side: "left", bound: (item)}
  for item in left
  |
  item: {side: "right", bound: (item)}
  for item in right
outside: (item)
