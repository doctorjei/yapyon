# SPEC §5.1.4: a variable outside the exposed set is indistinguishable from
# an unset one. API_KEY is in the environment, and not a standard variable.
key: y"{__env__('API_KEY', 'hidden')}"
home: y"{$HOME}"
