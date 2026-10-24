# §5.1.2, §14.4: block style, declaration order, and a scalar is plain
# only if every YAML 1.1 and 1.2 reader reads it as a string.
cfg:
  GOOSE_MODEL: "nav-m1"
  flag: "no"
out: y"{cfg.__as_yaml__()}"
