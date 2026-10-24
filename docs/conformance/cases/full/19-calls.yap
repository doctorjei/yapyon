# GRAMMAR §G5, SPEC §13.1: calls in holes. The receiver form is sugar for
# the call form; calls nest inside-out and chain left to right; a built-in
# takes keyword arguments; a hole may reuse its literal's quote (PEP 701).
cfg:
  name: "gw"
  port: 0x50
a: y"{cfg.__as_json__()}"
b: y"{__as_json__(cfg)}"
plain: y"{ cfg.__as_json__( lexemes = False , ) }"
nested: y"{__as_json__(cfg.__as_json__(lexemes=False))}"
key: y"{__as_json__("k\"q")}"
me: y"{__as_json__(__KEY__)}"
