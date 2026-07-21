#!/usr/bin/env python3
"""Claude Code SessionEnd hook -- does two things on a clean session exit.

Registered on SessionEnd, not Stop: Stop fires after every agent turn
(Claude finishes one response, waits for the next prompt), which isn't
session termination at all -- that bug shipped briefly and was caught live
when busy expressions flipped back to idle mid-session, well before the
terminal actually closed. SessionEnd fires exactly once, when the CLI
process itself exits.

1. The other half of the staleness-flagging mechanism (backend/staleness.py):
   appends a SESSION_END sentinel to the job's runtime log, exactly the way
   log_action.py appends action lines (same job-identity resolution:
   NOCTIS_MODE/NOCTIS_JOB_ID env vars for Terminal.app, --mode/--job-id
   baked in for VS Code). A job whose log ends in SESSION_END was closed on
   purpose, not abandoned mid-session -- staleness.py must never flag it
   regardless of how old that sentinel gets.

2. Clears the mode's `busy` ambient flag (added 2026-07-21) -- found live
   that nothing in the system ever set `busy` at all: POST /session/launch
   sets it true (deterministic, the backend just performed the launch),
   and this is the other end, the one place that actually knows the
   session ended. Needs vault_io, hence launch_surfaces.py now invokes
   this hook with the venv's own python3 rather than bare `python3` (which
   resolves to whatever's on PATH in the launched shell, not necessarily
   anything with python-frontmatter installed).

Gated on the payload's `reason` field (found live 2026-07-22, chasing
Custos showing idle mid-session): SessionEnd fires with reason "clear" or
"resume" when a running CLI process recycles its logical session (a plain
/clear, or the auto-compact-driven internal resume that happens when a long
conversation's context gets summarized) -- the terminal is still open and
the user is still actively in it. Only "logout", "prompt_input_exit",
"bypass_permissions_disabled", and "other" indicate the process itself is
actually going away. Treating every SessionEnd as a real close made a busy
mode flip to idle -- and a job eligible for staleness flagging -- mid-use.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

RUNTIME_DIR = Path(__file__).parent.parent / "runtime"

# Reasons that mean the session was recycled in place, not actually closed --
# see the module docstring.
NON_TERMINAL_REASONS = {"clear", "resume"}

sys.path.insert(0, str(Path(__file__).parent.parent))
# The launched Terminal/VS Code shell doesn't necessarily have VAULT_PATH
# exported (same reason main.py and nightshift/runner.py both load it
# explicitly) -- can't assume the launching session's environment.
load_dotenv(Path(__file__).parent.parent.parent / ".env")


def mark_session_end(mode: str | None, job_id: str | None, reason: str | None) -> None:
    if not mode:
        return  # not a Noctis-launched session, nothing to mark
    if reason in NON_TERMINAL_REASONS:
        return  # session was recycled in place -- still in active use

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RUNTIME_DIR / f"{mode}__{job_id or 'general'}.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} SESSION_END\n")

    import vault_io

    state, content = vault_io.read_frontmatter(f"modes/{mode}/state.md")
    state["busy"] = False
    vault_io.write_frontmatter(f"modes/{mode}/state.md", state, content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode")
    parser.add_argument("--job-id")
    args = parser.parse_args()

    mode = args.mode or os.environ.get("NOCTIS_MODE")
    job_id = args.job_id or os.environ.get("NOCTIS_JOB_ID")

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}
    reason = payload.get("reason")

    mark_session_end(mode, job_id, reason)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a hook must never break session shutdown
