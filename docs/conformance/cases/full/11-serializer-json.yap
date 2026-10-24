# §5.1.2, §14.3: keys in document order and never sorted; a container
# that fits in 100 columns is written on one line (§14.1).
cfg:
  name: "gw"
  port: 8080
  on: True
out: y"{cfg.__as_json__()}"
