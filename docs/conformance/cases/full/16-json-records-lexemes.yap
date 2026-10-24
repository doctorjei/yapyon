# §14.2, §14.3: bytes become padded base64url text and a non-decimal
# integer its value; what the plain value cannot say is recorded beside it
# in @_lexemes, the object's last member. The one-line form is over 100
# columns, so the object breaks (§14.1).
s:
  b: b64"aGk="
  h: hex'6869'
  port: 0xff
out: y"{s.__as_json__()}"
