# Collection construction, local bindings, and explicit availability checks.
persona:
  name: "example"
  mind:
    model_list: ["m1", "M/2"]
    dialects: {responses: None, chat: {}}
supported_dialects: ["responses", "chat"]

model_rows:
  target:
    provider: (persona.name)
    remote_model_id: (target)
  for target in persona.mind.model_list

protocol: [dialect for dialect in supported_dialects if persona.mind.dialects.__get__(dialect) is not None][0]

by_provider: {+ persona.name: target for target in persona.mind.model_list}
