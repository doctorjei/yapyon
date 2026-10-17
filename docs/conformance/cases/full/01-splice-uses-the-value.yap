# §5.4: a hole splices its VALUE, as Python's str() writes it -- never the
# lexeme. Equal values splice as equal text, whatever their spelling, and
# bytes splice as their repr, the b'...' marking the crossing.
pi: 3.140
mask: 0xFF
big: 1_000
tiny: 1e-5
huge: 1e16
raw: b"hi"
enc: b64"aGk="
yes: True
version: "3.10"
line: y"{pi} {mask} {big} {tiny} {huge} {yes}"
bytes: y"{raw}={enc}"
banner: y"v{version}"
