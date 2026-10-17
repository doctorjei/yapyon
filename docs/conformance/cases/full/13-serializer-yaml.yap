# §5.1.2: block style, declaration order, scalars quoted when YAML would
# guess at them.
cfg:
  GOOSE_MODEL: "nav-m1"
  flag: "no"
out: y"{cfg.__AS_YAML__()}"
