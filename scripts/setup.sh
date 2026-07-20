#!/usr/bin/env bash
# Fresh-Mac setup: backend venv + deps, frontend deps. Target: under 10 minutes.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Backend: creating venv + installing dependencies"
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip >/dev/null
backend/.venv/bin/pip install -r backend/requirements.txt

echo "==> Frontend: installing dependencies"
(cd frontend && npm install)

if [ ! -f .env ]; then
  echo "==> Copying .env.example to .env (fill in real values before running)"
  cp .env.example .env
fi

echo "==> Setup complete"
