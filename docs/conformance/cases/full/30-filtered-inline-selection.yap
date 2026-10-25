supported: ["responses", "chat"]
persona: {mind: {dialects: {responses: None, chat: {}}}}
protocol: [dialect for dialect in supported if persona.mind.dialects.__get__(dialect) is not None][0]
optional: [dialect for dialect in []].__get__(0)
