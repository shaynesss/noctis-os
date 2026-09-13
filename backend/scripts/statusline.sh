#!/bin/bash
# Claude Code runs this on every render of an interactive session and passes a
# JSON payload on stdin: the 5h/7d windows, context occupancy, effort, model,
# session id and transcript path. Forwarding it is how the shell's status bar
# learns those things without a `stream-json` turn in flight.
#
# Prints one short line back, because whatever this writes to stdout becomes
# the CLI's own status line inside the terminal.
#
# Never fails loudly: a status line that errors would put its stderr in the
# middle of a session. If the backend is down the numbers simply do not update.
PORT="${1:-8000}"
PAYLOAD=$(cat)
TOKEN="${NOCTIS_API_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f "$HOME/Developer/noctis-os/.env" ]; then
  TOKEN=$(grep '^NOCTIS_API_TOKEN' "$HOME/Developer/noctis-os/.env" | cut -d= -f2 | tr -d ' "')
fi
printf '%s' "$PAYLOAD" | curl -s -m 2 -o /dev/null \
  -X POST "http://127.0.0.1:${PORT}/v2/sessions/statusline" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" --data-binary @- 2>/dev/null || true
echo "noctis"
