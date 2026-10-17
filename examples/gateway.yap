# yapyon example — most of the format in one document.

name: "api-gateway"
version: "3.10"                # a string: a version is not a float
port: 8080
debug: False
owner: None

limits: {burst: 100, sustained: 25}
weights: [0.5, 0.3, 0.2]
allowed:
  - "https://example.com"
  - "https://app.example.com"

paths:
  root: "/srv/gateway"
  logs: y"{root}/logs"                    # nearest wins: sibling `root`
  banner: y"{name} v{version}"            # outer scope; splices the value
  pattern: ry"^{name}-\d+$"               # raw: backslash literal, hole live
  greeting: yt"{name} v{version}"         # same holes as `banner`, NOT joined:
                                          # the consumer gets the parts and
                                          # escapes each value itself (§6)

magic:
  png: b"\x89PNG\r\n\x1a\n"
  token: b64"aGVsbG8gd29ybGQ="
  frame: yb"*{port}\r\n"                  # the ASCII of 8080 into bytes

# Ordered multimap: keys may repeat, and the order of entries is the data.
changes:
  + registry:
      set: [["LabConfig", "BypassTPMCheck", 1]]
  + file:
      delete: ["Program Files/Edge"]
  + registry:                             # repeating is the point, not a typo
      remove: ["Uninstall/Edge"]

# A bare marker puts the body in the block beneath — layout, not meaning.
retries:
  -
    attempts: 3
    backoff: 1.5
  - "give up"

note: """He said "hi" — inline, no escaping needed"""
inline_block: """First line sits after the delimiter; the anchor comes
              from this line, so aligning either way is clean."""

motd:
  """
  Welcome to the gateway.

  The newline after the delimiter is dropped, blank lines are exempt,
  and lines indented deeper than the anchor keep the extra:
      like this one.
  Please behave."""
