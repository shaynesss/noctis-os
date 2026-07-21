#!/usr/bin/env python3
"""Claude Code Stop hook -- the other half of the staleness-flagging
mechanism (backend/staleness.py). Appends a SESSION_END sentinel to the
job's runtime log on a clean exit, exactly the way log_action.py appends
action lines (same job-identity resolution: NOCTIS_MODE/NOCTIS_JOB_ID env
vars for Terminal.app, --mode/--job-id baked in for VS Code). A job whose
log ends in SESSION_END was closed on purpose, not abandoned mid-session --
staleness.py must never flag it regardless of how old that sentinel gets.
"""
import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

RUNTIME_DIR = Path(__file__).parent.parent / "runtime"


def mark_session_end(mode: str | None, job_id: str | None) -> None:
    if not mode:
        return  # not a Noctis-launched session, nothing to mark

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RUNTIME_DIR / f"{mode}__{job_id or 'general'}.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()} SESSION_END\n")


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
