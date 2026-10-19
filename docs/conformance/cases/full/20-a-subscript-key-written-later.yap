# §5.1, §5.3: a subscript's key may be a y-string written further down.
# Forward references work, so the order of keys must not change the answer.
dialects:
  chat: {uri: "/chat"}
  responses: {uri: "/responses"}
chosen: y"{dialects[protocol].uri}"
protocol: y"{default}"
default: "chat"
