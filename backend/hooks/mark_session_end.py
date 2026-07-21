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
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

RUNTIME_DIR = Path(__file__).parent.parent / "runtime"

sys.path.insert(0, str(Path(__file__).parent.parent))
# The launched Terminal/VS Code shell doesn't necessarily have VAULT_PATH
# exported (same reason main.py and nightshift/runner.py both load it
# explicitly) -- can't assume the launching session's environment.
load_dotenv(Path(__file__).parent.parent.parent / ".env")


def mark_session_end(mode: str | None, job_id: str | None) -> None:
    if not mode:
        return  # not a Noctis-launched session, nothing to mark

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
    mark_session_end(mode, job_id)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a hook must never break session shutdown
