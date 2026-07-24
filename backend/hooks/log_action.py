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

sys.path.insert(0, str(Path(__file__).parent.parent))
import busy_marker  # noqa: E402


def _summarize(tool_input: dict) -> str:
    for key in ("file_path", "command", "path", "pattern", "url"):
        if key in tool_input:
            value = str(tool_input[key])
            return value if len(value) <= 100 else value[:97] + "..."
    return ""


def log_action(mode: str | None, job_id: str | None, payload: dict) -> None:
    if not mode:
        return  # not a Noctis-launched session, nothing to log

    # Refreshes the busy marker's mtime on every tool call, not just once at
    # launch -- is_busy() self-heals (deletes) any marker older than
    # STALE_THRESHOLD (6h) on the assumption that age alone means abandoned,
    # which is right for a crashed session but wrong for one that's simply
    # been running a long time. A session left open overnight blows past 6h
    # while genuinely active, so the marker expired and the card read idle
    # out from under a live session (found live 2026-07-24, an overnight
    # settings session with no SessionEnd ever logged). Touching here means
    # the marker's age reflects "time since last activity," not "time since
    # launch" -- a session truly abandoned still goes stale within 6h of its
    # last real tool call.
    busy_marker.set_busy(mode)

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

    # Env wins over baked args, not the other way around: a non-dev session
    # whose cwd happens to sit inside a dev project's directory still picks
    # up that project's --mode/--job-id-baked hooks (Claude Code applies
    # project-local settings.local.json by cwd, regardless of which mode
    # actually launched the session) -- found live 2026-07-23, a settings
    # session's SessionEnd firing dev's hook at the identical microsecond
    # as its own. A real launch always exports NOCTIS_MODE/NOCTIS_JOB_ID
    # for its own session (see launch_terminal / the dev task's export
    # line); baked args only exist as VS Code's fallback for when no shell
    # env carries through, so they should lose to a live env value, never
    # win over one.
    mode = os.environ.get("NOCTIS_MODE") or args.mode
    job_id = os.environ.get("NOCTIS_JOB_ID") or args.job_id

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
