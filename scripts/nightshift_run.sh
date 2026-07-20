#!/usr/bin/env bash
# launchd target for Nightshift's unattended runs (see SPEC.md EDD:
# "Nightshift execution mechanism: launchd"). Propose-never-commit: writes
# only to the staging inbox, never live vault pages or code.
set -euo pipefail

cd "$(dirname "$0")/.."

# TODO: invoke the nightshift subagent roster against each mode's declared
# "slack surface" per SPEC.md EDD, with the tool allowlist (staging-inbox
# writes only, minimal bash, no network by default). Not a scaffolding task.
echo "nightshift_run.sh: not yet implemented"
