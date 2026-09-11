.PHONY: setup bootstrap dev test app open-app

setup:
	./scripts/setup.sh

# setup.sh installs this repo's dependencies; bootstrap configures the
# machine (symlinks, launchd, config dirs, tooling). Different concerns.
bootstrap:
	./bootstrap/bootstrap.sh

dev:
	@trap 'kill 0' EXIT; \
	(cd backend && .venv/bin/uvicorn main:app --reload --reload-exclude 'runtime/*' --reload-exclude 'data/*' --reload-exclude 'launch_config/*' --port $${PORT:-8000}) & \
	(cd frontend && npm run dev) & \
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

app:
	backend/.venv/bin/python desktop/app.py

# desktop/NoctisOS.app is a thin double-click wrapper around `make app`
# (real Dock/Finder icon, no terminal needed) -- always runs the live
# source, not a frozen build, so code changes just need the app's own
# Refresh command (Cmd+R), never a rebuild of this target.
open-app:
	open desktop/NoctisOS.app
