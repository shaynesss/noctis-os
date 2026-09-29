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

# One dated line per run. The log had no timestamps at all, so which night a
# line belonged to could only be guessed from the dated slugs beside it.
echo "nightshift: started $(date '+%Y-%m-%d %H:%M %Z')"

# Held awake for the run. Three nights of timeouts (2026-09-21, 09-26, 09-29)
# were the laptop sleeping mid-draft, and the drafter's timer counts only
# awake time. `-i` holds off idle sleep; `-s` holds off system sleep, which
# macOS honours on AC power only, so on battery with the lid shut the
# runner's own retry-on-waking is what covers it.
exec /usr/bin/caffeinate -i -s backend/.venv/bin/python3 backend/nightshift/runner.py
