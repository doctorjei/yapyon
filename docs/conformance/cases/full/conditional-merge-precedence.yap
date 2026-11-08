# Merge remains lowest precedence, outside conditional selection.
output: {base: 1} | {yes: 2} if False else {no: 3}
grouped: ({base: 1} | {yes: 2}) if False else {no: 3}
