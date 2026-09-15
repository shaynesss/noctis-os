#!/usr/bin/env bash
# launchd target for Nightshift's unattended runs (see SPEC.md EDD:
# "Nightshift execution mechanism: launchd"). Propose-never-commit: writes
# only to the staging inbox, never live vault pages or code -- see
# backend/nightshift/runner.py for the actual Scan -> Advance -> Stage loop.
set -euo pipefail

# launchd runs this with a bare PATH (/usr/bin:/bin:/usr/sbin:/sbin), and
# `claude` lives in Homebrew's bin. Every nightly run from the first
# (2026-08-05) to 2026-09-15 failed its advance step with "No such file or
# directory: 'claude'" and logged a quiet night -- 47 failures over 41
# nights, and not one lessons distillation ever ran. Found 2026-09-15 while
# checking whether anything was scheduled at all.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

cd "$(dirname "$0")/.."

exec backend/.venv/bin/python3 backend/nightshift/runner.py
