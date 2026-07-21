.PHONY: setup dev app

setup:
	./scripts/setup.sh

dev:
	@trap 'kill 0' EXIT; \
	(cd backend && .venv/bin/uvicorn main:app --reload --port $${PORT:-8000}) & \
	(cd frontend && npm run dev) & \
	wait

app:
	backend/.venv/bin/python desktop/app.py
