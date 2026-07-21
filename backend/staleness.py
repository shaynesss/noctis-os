"""Deterministic staleness -> flagged mechanism for dev jobs (CLAUDE.md's
"Deterministic-where-possible" rule: staleness checks are backend code,
never left to session judgment). This is dev mode's own domain, not
nightshift's -- nightshift only ever *reads* the `flagged` field (see
modes/dev/state.md's frontmatter docs); this module is what actually sets
it.

A job is flagged when it looks like a session died mid-build: no activity
(runtime log or last_touched) for longer than STALE_THRESHOLD, and no
SESSION_END sentinel (backend/hooks/mark_session_end.py, a Stop hook) ever
closed it cleanly. A job someone just paused on purpose for a day is not
"stale" in this sense as long as it closed cleanly last time -- only an
abrupt, never-closed session counts.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import vault_io

RUNTIME_DIR = Path(__file__).parent / "runtime"

# A judgment call, not a spec-locked number: long enough that a normal
# working break doesn't false-positive, short enough that a genuinely dead
# session shows up the same day rather than waiting for a nightly sweep.
STALE_THRESHOLD = timedelta(hours=6)


def _job_last_activity(mode: str, slug: str, last_touched: str | None) -> tuple[datetime | None, bool]:
    """Returns (last_activity_time, closed_cleanly). Runtime log activity
    (if present) is a more precise signal than last_touched -- it reflects
    real tool calls, not just whenever the job context happened to be
    written.
    """
    closed_cleanly = False
    last_activity = None
    if last_touched:
        try:
            last_activity = datetime.fromisoformat(last_touched)
        except ValueError:
            last_activity = None

    log_path = RUNTIME_DIR / f"{mode}__{slug}.log"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").splitlines()
        if lines:
            last_line = lines[-1]
            # Anchored, not a bare substring match: a real tool-call line
            # is "<timestamp> <tool_name> <summary...>", where <summary>
            # could itself happen to contain the literal text "SESSION_END"
            # (e.g. editing mark_session_end.py) and would previously have
            # been misread as a clean close. The sentinel mark_session_end.py
            # actually writes is exactly two tokens: "<timestamp> SESSION_END".
            # Found in the 2026-07-21 ship-gate review.
            parts = last_line.split(" ")
            closed_cleanly = len(parts) == 2 and parts[1] == "SESSION_END"
            timestamp_str = last_line.split(" ", 1)[0]
            try:
                log_time = datetime.fromisoformat(timestamp_str)
                if last_activity is None or log_time > last_activity:
                    last_activity = log_time
            except ValueError:
                pass

    return last_activity, closed_cleanly


def flag_stale_dev_jobs(now: datetime | None = None) -> list[str]:
    """Scans modes/dev/state.md's jobs, flags any that look abandoned
    mid-session. Returns the slugs newly flagged this pass. Mutates both
    the job's own context.md and the mirrored entry in state.md -- the
    two must never drift (see mode.py's _sync_state_job_entry, which this
    reuses).
    """
    now = now or datetime.now(timezone.utc)
    state, _ = vault_io.read_frontmatter("modes/dev/state.md")
    newly_flagged = []

    for job in state.get("jobs", []):
        slug = job.get("slug")
        if not slug or job.get("flagged"):
            continue

        last_activity, closed_cleanly = _job_last_activity("dev", slug, job.get("last_touched"))
        if closed_cleanly or last_activity is None:
            continue
        if now - last_activity <= STALE_THRESHOLD:
            continue

        job_path = f"modes/dev/jobs/{slug}/context.md"
        if not vault_io.file_exists(job_path):
            continue

        metadata, content = vault_io.read_frontmatter(job_path)
        metadata["flagged"] = True
        vault_io.write_frontmatter(job_path, metadata, content)
        newly_flagged.append(slug)

    if newly_flagged:
        _sync_flags_into_state(newly_flagged)

    return newly_flagged


def _sync_flags_into_state(flagged_slugs: list[str]) -> None:
    state, content = vault_io.read_frontmatter("modes/dev/state.md")
    for job in state.get("jobs", []):
        if job.get("slug") in flagged_slugs:
            job["flagged"] = True
    vault_io.write_frontmatter("modes/dev/state.md", state, content)
