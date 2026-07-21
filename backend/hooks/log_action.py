#!/usr/bin/env python3
"""Claude Code PostToolUse hook — appends one action line per tool call to
this job's runtime status file (SPEC.md EDD: "hook-driven action-feed logs
... live in a gitignored backend runtime folder", explicitly NOT the vault).

Job identity comes from env vars NOCTIS_MODE/NOCTIS_JOB_ID (set by the
Terminal.app launch command — see launch_surfaces.launch_terminal) or, when
those aren't inherited, from --mode/--job-id baked into the hook command
itself at launch time (VS Code's URI handler doesn't carry shell env, so Dev
launches register a per-project hook with these args already filled in —
see launch_surfaces._ensure_dev_hooks).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

RUNTIME_DIR = Path(__file__).parent.parent / "runtime"


def _summarize(tool_input: dict) -> str:
    for key in ("file_path", "command", "path", "pattern", "url"):
        if key in tool_input:
            value = str(tool_input[key])
            return value if len(value) <= 100 else value[:97] + "..."
    return ""


def log_action(mode: str | None, job_id: str | None, payload: dict) -> None:
    if not mode:
        return  # not a Noctis-launched session, nothing to log

    tool_name = payload.get("tool_name", "unknown")
    summary = _summarize(payload.get("tool_input") or {})
    line = f"{datetime.now(timezone.utc).isoformat()} {tool_name} {summary}".rstrip()

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RUNTIME_DIR / f"{mode}__{job_id or 'general'}.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


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

    log_action(mode, job_id, payload)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a hook must never break the session it's observing
