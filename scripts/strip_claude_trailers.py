# The body of a git filter-repo message callback, not a script to run:
#   git filter-repo --message-callback "$(cat scripts/strip_claude_trailers.py)"
# Removes the same lines the Repo tab's push refuses (backend/routers/panels.py,
# _ATTRIBUTION), so a history this has cleaned always passes that check.
import re
lines = message.split(b"\n")
keep = [l for l in lines if not re.match(rb"^\s*(Co-Authored-By\s*:.*|Claude-Session\s*:.*|\W*Generated with \[?Claude Code\]?(\([^)\s]*\))?[\s.]*)$", l, re.I)]
while keep and keep[-1].strip() == b"": keep.pop()
return b"\n".join(keep) + b"\n"
