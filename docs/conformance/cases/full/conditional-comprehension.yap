# A conditional head is distinct from the comprehension's optional filter.
input: [True, False, None]
output: ["yes" if item else "no" for item in input]
filtered: [item for item in input if item is not None]
