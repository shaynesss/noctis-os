#!/usr/bin/env bash
# launchd target for Nightshift's unattended runs (see SPEC.md EDD:
# "Nightshift execution mechanism: launchd"). Propose-never-commit: writes
# only to the staging inbox, never live vault pages or code -- see
# backend/nightshift/runner.py for the actual Scan -> Advance -> Stage loop.
set -euo pipefail

cd "$(dirname "$0")/.."

exec backend/.venv/bin/python3 backend/nightshift/runner.py
