foo: {}
items: [1, (foo.x!), 3]
rows: [{keep: 1, drop: (foo.x!)}, {}]
text: __str__(foo.x!)
test: foo.x! is None
selected: (foo[selector!]!)
keep: None
