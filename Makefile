.PHONY: setup dev app open-app

setup:
	./scripts/setup.sh

dev:
	@trap 'kill 0' EXIT; \
	(cd backend && .venv/bin/uvicorn main:app --reload --port $${PORT:-8000}) & \
	(cd frontend && npm run dev) & \
	wait

app:
	backend/.venv/bin/python desktop/app.py

# desktop/NoctisOS.app is a thin double-click wrapper around `make app`
# (real Dock/Finder icon, no terminal needed) -- always runs the live
# source, not a frozen build, so code changes just need the app's own
# Refresh command (Cmd+R), never a rebuild of this target.
open-app:
	open desktop/NoctisOS.app
