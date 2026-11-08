# Conditions use bool/None; only the selected typed branch is evaluated.
flag: True
primary: {port: 443}
chosen: primary if flag else missing
none_condition: 1 if None else 2
right_associated: 1 if True else 2 if False else 3
