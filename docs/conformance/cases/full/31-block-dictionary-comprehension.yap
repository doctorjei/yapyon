persona: {name: "example", models: ["m1", "M/2"]}
rows:
  target:
    provider: (persona.name)
    remote: (target)
  for target in persona.models
