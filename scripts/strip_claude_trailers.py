import re
lines = message.split(b"\n")
keep = [l for l in lines if not re.match(rb"^\s*(Co-Authored-By:.*|Claude-Session:.*|.*Generated with \[Claude Code\].*)$", l, re.I)]
while keep and keep[-1].strip() == b"": keep.pop()
return b"\n".join(keep) + b"\n"
