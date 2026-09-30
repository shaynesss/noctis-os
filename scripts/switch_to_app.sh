#!/usr/bin/env bash
# Move from the dev window (`make dev`) to the packaged Noctis.app, v2.0.
#
# Run it on purpose, once, when nothing in a terminal is mid-reply: it quits
# the dev window, and every terminal in it ends. Each tab comes back in the
# app, resumed (the backend keeps the tab list, /v2/sessions/arrangement).
#
#   make switch
#
# It must outlive the window it closes, so `make switch` hands it to launchd
# as a one-off job rather than running it in a terminal Noctis hosts. Its
# own record is backend/runtime/switch.log.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
say() { echo "$(date '+%H:%M:%S') switch: $*"; }

# Run from a terminal, hand the real work to launchd and return: the dev
# window's terminals end in step 3, and this must not end with them.
if [ "${1:-}" != "--detached" ]; then
  label="com.noctis-os.switch"
  plist="${TMPDIR:-/tmp}/$label.plist"
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$REPO/scripts/switch_to_app.sh</string><string>--detached</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>AbandonProcessGroup</key><true/>
  <key>StandardOutPath</key><string>$REPO/backend/runtime/switch.log</string>
  <key>StandardErrorPath</key><string>$REPO/backend/runtime/switch.log</string>
</dict></plist>
PLIST
  plutil -lint "$plist" >/dev/null || { echo "switch: could not write $plist"; exit 1; }
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
  echo "switch: handed to launchd; the dev window will close and Noctis.app open. Log: backend/runtime/switch.log"
  exit 0
fi

say "start ($REPO)"

# 1. The app, built from this checkout if it is not installed yet.
if [ ! -d /Applications/Noctis.app ]; then
  say "building and installing Noctis.app"
  make -C "$REPO" app || { say "FAILED: the app did not build; nothing else was changed"; exit 1; }
fi

# 2. The backend as its login service. bootstrap stops any supervisor that
#    `make dev` or `make reload` started, then loads com.noctis-os.backend.
say "installing the backend login service"
"$REPO/bootstrap/bootstrap.sh" || say "bootstrap reported a problem (see above); continuing only if the backend answers"
for _ in $(seq 1 30); do
  curl -s -o /dev/null http://127.0.0.1:8000/health && break
  sleep 1
done
if ! curl -s -o /dev/null http://127.0.0.1:8000/health; then
  say "FAILED: the backend is not answering under launchd; the dev window was left open"
  exit 1
fi
say "backend up under launchd: $(launchctl print "gui/$(id -u)/com.noctis-os.backend" 2>/dev/null | grep -m1 'state =' | xargs)"

# 3. The dev window: `make dev` and everything under it (vite, tsc --watch,
#    `tauri dev`, the debug shell). Its own trap ends the group.
dev="$(pgrep -a -f '^/Library/Developer/CommandLineTools/usr/bin/make dev$|^make dev$' | head -1)"
if [ -n "$dev" ]; then
  pgid="$(ps -o pgid= -p "$dev" | tr -d ' ')"
  say "quitting the dev window (make dev pid $dev, group $pgid)"
  kill -TERM -- "-$pgid" 2>/dev/null || kill -TERM "$dev"
fi
pkill -a -f 'target/debug/noctis$' 2>/dev/null || true
for _ in $(seq 1 20); do
  pgrep -a -f 'target/debug/noctis$' >/dev/null || break
  sleep 0.5
done

# 4. The app. Its first launch restores the tabs from the backend and turns
#    on open-at-login once.
say "opening /Applications/Noctis.app"
open /Applications/Noctis.app
say "done"
