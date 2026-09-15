"""What nightshift did last night, on record.

The runner ran every night from 2026-08-05 and failed every night until
2026-09-15 -- launchd's PATH could not find `claude` -- and nothing said
so: each item's failure was caught, printed to a log nobody opens, and the
run ended "quiet night, nothing staged", which reads as success. This file
is the answer. Every run writes one entry -- when, what staged, what failed
and why -- and Settings' Maintenance section reads the newest, so a failing
night is a sentence in the app rather than a line in a log, and a run of
them is a count.

Kept in `backend/data/` beside the history store: machine state,
gitignored, reload-excluded.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.store import DATA_DIR

PATH = DATA_DIR / "nightshift.json"
KEEP = 60           # nights of history; the digest only needs the newest and the streak


def _load(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def record(staged: list[str], failed: list[dict], seen: int, path: Path | None = None,
           now: datetime | None = None) -> dict:
    """Append one run. `failed` entries are `{slug, kind, error}`. The
    entry's `error` is the one reason when every failure shares it -- the
    signal that distinguishes a broken machine from one bad item."""
    path = path or PATH
    errors = {f["error"] for f in failed}
    entry = {
        "ran_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "seen": seen,
        "staged": list(staged),
        "failed": len(failed),
        "error": errors.pop() if len(errors) == 1 and failed and len(failed) == seen else None,
        "failures": failed[:20],
    }
    runs = _load(path)
    runs.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(runs[-KEEP:], indent=1), encoding="utf-8")
    return entry


def summary(path: Path | None = None) -> dict | None:
    """The newest run, plus how many nights in a row have ended the same
    way: `streak` counts consecutive runs whose outcome matches the newest
    (all failed with one error, or staged nothing while seeing nothing,
    or staged something). None when nightshift has never recorded a run."""
    runs = _load(path or PATH)
    if not runs:
        return None
    last = runs[-1]
    kind = _kind(last)
    streak = 0
    for run in reversed(runs):
        if _kind(run) != kind:
            break
        streak += 1
    return {
        "ran_at": last["ran_at"],
        "staged": len(last["staged"]),
        "failed": last["failed"],
        "seen": last["seen"],
        "error": last["error"],
        "kind": kind,
        "streak": streak,
    }


def _kind(run: dict) -> str:
    if run["error"]:
        return "broken"                       # every item failed the same way
    if run["failed"]:
        return "partial"
    return "staged" if run["staged"] else "quiet"
