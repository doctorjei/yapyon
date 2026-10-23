# SPEC §5.6: the value is resolved where it is written, then copied, so
# nothing in the copy depends on where it lands.
host: "example.com"
base:
  name: y"{__PARENT__.__KEY__}"
  url: y"https://{host}/{name}"
sites:
  host: "elsewhere.org"
  prod: (base)
