# §5.1.2: __as_yapyon__ writes a record, and a yt has no record form --
# its parts are delivered unjoined (§6), and joining them here would make
# yt silently mean y.
who: "x"
cfg:
  t: yt"hi {who}"
out: y"{cfg.__as_yapyon__()}"
