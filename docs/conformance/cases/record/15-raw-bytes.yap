# §4.3: rb"..." takes the escape table's raw reading — the backslashes are
# literal, which is what makes regex and Windows paths writable without
# doubling them.
pat: rb"\d\w+"
also: b"\\d\\w+"
win: rb"C:\Users\me"
same: b"C:\\Users\\me"
