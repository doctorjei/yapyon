# SPEC §5.1.5: the casters, with yapyon's own parsing. Text must be the
# whole number or word; leading zeros in text are fine; a float truncates
# to an int; bools are 1 and 0.
port_text: "0080"
ratio_text: "2.5e+3"
flag_text: "Yes"
whole: 3.7
port: (port_text.__int__())
ratio: (ratio_text.__float__())
flag: (flag_text.__bool__())
truncated: (whole.__int__())
one: (__int__(True))
back: (port.__str__())
