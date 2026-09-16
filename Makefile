.PHONY: setup bootstrap dev browser doctor reload test open-app

setup:
	./scripts/setup.sh

# setup.sh installs this repo's dependencies; bootstrap configures the
# machine (symlinks, launchd, config dirs, tooling). Different concerns.
bootstrap:
	./bootstrap/bootstrap.sh

# The browser fallback. Same backend and frontend, no native window -- useful
# when you are changing backend code and do not want to pay for a Rust build,
# and as the way in if the Rust toolchain is ever broken.
#
# Three processes, and the third is the one worth explaining.
#
# **Vite never typechecks.** It transforms and serves whatever is on disk, so
# a type error is not caught at all -- it reaches the browser and becomes a
# runtime crash. `Can't find variable: effort` with a React stack is what a
# missing const looks like when nothing checked first, and the editor's own
# squiggle is the only other place it would have shown.
#
# The binary directly, not through `npx`. npx runs an `npm exec` wrapper with
# the real compiler as its child, and the wrapper is what the exit trap
# reaches -- killing it orphans the node process, which then survives every
# restart. Two such pairs had accumulated before the machine ran short of
# memory and killed the dev loop outright.
#
# `tsc -b --watch` closes that: the error appears in this terminal the moment
# it is written, named and located, whether or not an editor is open on the
# file. It never blocks anything -- it only reports.
#
# Prefixed through `awk` with an explicit `fflush()`, not `sed`. sed writing
# to anything but a terminal is fully buffered, so its output sits in a 4KB
# block until the process exits -- fine when you run `make dev` yourself and
# invisible everywhere else, which is how this shipped silent and looked like
# a watcher that was not running. It was running and saying nothing.
browser:
	@trap 'kill 0' EXIT; \
	(cd backend && .venv/bin/uvicorn main:app --reload --reload-exclude 'runtime/*' --reload-exclude 'data/*' --port $${PORT:-8000}) & \
	(cd frontend && npm run dev) & \
	(cd frontend && ./node_modules/.bin/tsc -b --watch --preserveWatchOutput 2>&1 | awk '{print "[tsc] " $$0; fflush()}') & \
	wait

# The suite has always been run by typing the venv's interpreter path out in
# full, which is unmemorable and -- since it is an absolute path under a home
# directory -- not something a permission rule can name portably.
#
# The frontend halves are here because they were not, and a missing React
# import reached a running app as a white screen: tsc catches that outright,
# oxlint does not (it has no no-undef), and nothing was running tsc. Note
# `npm run typecheck`, never `tsc --noEmit -p tsconfig.json` -- that config is
# a solution file with "files": [], so the obvious form checks nothing and
# exits 0 on a broken tree.
test:
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npm run typecheck
	cd frontend && npm run test

# What is up, what is down, and what to type about it.
#
# `make dev` starts uvicorn and vite under one `trap 'kill 0' EXIT`, but that
# trap only fires when make itself exits. If the backend dies on its own, vite
# survives and keeps serving a UI that talks to nothing -- so the symptom is a
# dead-looking app with a healthy-looking browser tab, and the natural reading
# ("the backend is broken") is usually wrong. It is normally just absent.
doctor:
	@printf 'backend  '
	@curl -sf -m 2 -o /dev/null http://127.0.0.1:$${PORT:-8000}/health \
		&& echo "up    http://127.0.0.1:$${PORT:-8000}" \
		|| echo "DOWN  -> make dev   (or: make reload)"
	@printf 'frontend '
	@curl -sf -m 2 -o /dev/null http://localhost:5180 \
		&& echo 'up    http://localhost:5180' \
		|| echo 'DOWN  -> make dev'
	@printf 'imports  '
	@cd backend && .venv/bin/python -c 'import main' >/dev/null 2>&1 \
		&& echo 'ok    (if backend is DOWN it is absent, not broken)' \
		|| echo 'FAIL  -> cd backend && .venv/bin/python -c "import main"'
# A hook may never break the session it observes, so both end in a swallow.
# This is where the swallowed faults surface: without it a hook that stops
# firing looks identical to a session that used no tools, and the action feed
# just goes quiet.
	@printf 'hooks    '
	@cd backend && .venv/bin/python -c \
		'from hooks import failure_log as f; r = f.recent(3); \
		 print("ok    no swallowed failures recorded") if not r else \
		 print("FAIL  " + str(len(r)) + " recent:\n    " + "\n    ".join(r))' \
		2>/dev/null || echo 'could not probe -- is the venv built?'
	@echo
	@echo 'capabilities  (what each mode needs vs what this harness has)'
	@cd backend && .venv/bin/python -m capabilities 2>/dev/null | sed 's/^/  /' \
		|| echo '  could not probe -- is the venv built?'

# Pick up a backend change without restarting the window.
#
# Kill it and the supervisor notices within a poll and starts it again on the
# new code -- so a deliberate restart and a crash take the same path, which is
# the point of crash-only design rather than a special case bolted beside it.
#
# This replaces `make backend`, which started a *second* uvicorn. That was
# right when nothing supervised the first one and is a port clash now.
#
# Two cases, and the second is the one that used to need a person: the
# supervisor is running, so killing uvicorn is enough and it comes back in
# seconds; or the supervisor itself is gone (it exited, or `make dev` was
# never run), so it is started here, detached, logging to runtime/dev.log.
reload:
	@if pgrep -f 'python[0-9.]* supervise\.py$$' >/dev/null 2>&1; then \
		pkill -f "uvicorn main:app" >/dev/null 2>&1 || true; \
		echo "backend killed; the supervisor brings it back within a few seconds"; \
	else \
		mkdir -p backend/runtime; \
		(cd backend && nohup .venv/bin/python supervise.py >> runtime/dev.log 2>&1 < /dev/null &); \
		echo "supervisor was not running; started it (log: backend/runtime/dev.log)"; \
	fi
	@echo "(if you are on 'make browser', its reloader has already done it)"

dev:
	@trap 'kill 0' EXIT; \
	PATH="$$HOME/.cargo/bin:$$PATH"; \
	(cd backend && .venv/bin/python supervise.py) & \
	(cd frontend && ./node_modules/.bin/tsc -b --watch --preserveWatchOutput 2>&1 | awk '{print "[tsc] " $$0; fflush()}') & \
	(cd frontend && PATH="$$HOME/.cargo/bin:$$PATH" npm run app) & \
	wait

# desktop/NoctisOS.app is a thin double-click wrapper around `make dev`
# (real Dock/Finder icon, no terminal needed) -- always runs the live
# source, not a frozen build, so code changes just need the app's own
# Refresh command (Cmd+R), never a rebuild of this target.
open-app:
	open desktop/NoctisOS.app
