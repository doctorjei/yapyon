# SPEC §5.6: a copy is the value its reference names, kept as what it is.
wanted: ["responses", "chat"]
supported_dialects: (wanted)
mind:
  dialects:
    codex: {api: "responses"}
  protocol: "codex"
  chosen: (dialects[protocol])
port: (mind.dialects.codex.api)
