mm:
  + k: 1
  + k: 0x02
w:
  mm:
    + k: 1
    + k: 2
j: "{\n  \"@type\": \"multimap\",\n  \"entries\": {\"@list\": [{\"k\": 1}, {\"k\": 2}]},\n  \"@_lexemes\": {\"entries/1\": \"0x02\"}\n}"
t: "mm.\"@type\" = \"multimap\"\nmm.entries = [{k = 1}, {k = 2}]\n"
y: "%TAG !multimap! tag:yaml.org,2002:\n%TAG !x! tag:yaml.org,2002:\n---\n!multimap!pairs\n- k: 1\n- k: !x!int 0x02\n"
