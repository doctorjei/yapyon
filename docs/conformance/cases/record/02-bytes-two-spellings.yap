# b"..." and b64"..." denote the SAME bytes (§3, §4.3). Spelling one side
# each way means a reader that mishandles either prefix fails the pair.
raw: b"hi"
also: b64"aGk="
same: b"hi"
again: b64"aGk="
