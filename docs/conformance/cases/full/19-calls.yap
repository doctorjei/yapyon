# GRAMMAR §G5, SPEC §13.1: calls in holes. The receiver form is sugar for
# the call form; calls nest inside-out and chain left to right; a built-in
# takes keyword arguments; a hole may reuse its literal's quote (PEP 701).
cfg:
  name: "gw"
  port: 0x50
a: y"{cfg.__AS_JSON__()}"
b: y"{__AS_JSON__(cfg)}"
plain: y"{ cfg.__AS_JSON__( lexemes = False , ) }"
nested: y"{__AS_JSON__(cfg.__AS_JSON__(lexemes=False))}"
key: y"{__AS_JSON__("k\"q")}"
me: y"{__AS_JSON__(__KEY__)}"
