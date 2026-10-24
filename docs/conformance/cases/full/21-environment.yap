# SPEC §5.1.3: {$NAME} is strict, __env__ falls back, and both are one
# lookup. The environment this loads in is 21-environment.env.json.
home: y"{$HOME}"
config: y"{__env__('XDG_CONFIG_HOME', default_config)}/app"
default_config: y"{$HOME}/.config"
cache: y"{__env__('XDG_CACHE_HOME', '/tmp')}"
lang: y"[{$LANG}]"               # set, and empty: a value, not unset
zone: y"{__env__('TZ')}"         # unset, one argument: None, spliced
json: y"{$LOGNAME.__as_json__()}"
shells:
  ana: "zsh"
  bo: "fish"
shell: y"{shells[$LOGNAME]}"
