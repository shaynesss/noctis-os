"""Deterministic staleness -> flagged mechanism for job-holding modes
(CLAUDE.md's "Deterministic-where-possible" rule: staleness checks are
backend code, never left to session judgment). Every mode whose methodology
says "session death marks the job context stale-and-flagged" -- dev, learn,
research, and maintenance's own jobs.

A job is flagged when it looks like a session died mid-build: no activity
(runtime log or last_touched) for longer than STALE_THRESHOLD, and no
SESSION_END sentinel (backend/hooks/mark_session_end.py, a SessionEnd hook --
deliberately not Stop, which fires after every turn rather than on real
session termination) ever closed it cleanly. A job someone paused on purpose
for a day is not "stale" in this sense as long as it closed cleanly last
time -- only an abrupt, never-closed session counts. A job already at Ship
or Done did not die mid-build and is never flagged.

Runs as nightshift's first step (`nightshift/runner.py`), so the flag is
set the night after a session died and the flagged-job scan that follows
has something to find. It ran on v1's `GET /mode/{name}` poll until the
2026-09-12 cutover deleted the route, and nothing called it for four days.

Jobs are read from their folders -- `modes/<folder>/jobs/<slug>/context.md`,
`maintenance/jobs/<slug>/context.md` -- which is where the launcher, the MCP
server and the Repo view read them. The `jobs` array in each `state.md` was
v1's mirror of those folders, kept in step by the deleted router; nothing
writes it now, so it is not read here either.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import vault_io
from jobs import MAINTENANCE_JOBS

RUNTIME_DIR = Path(__file__).parent / "runtime"

# A judgment call, not a spec-locked number: long enough that a normal
# working break doesn't false-positive, short enough that a genuinely dead
# session shows up the same day rather than waiting for a nightly sweep.
STALE_THRESHOLD = timedelta(hours=6)

# Vault folder -> where its jobs live.
FLAGGABLE = {
    "dev": "modes/dev/jobs",
    "learn": "modes/learn/jobs",
    "research": "modes/research/jobs",
    "maintenance": MAINTENANCE_JOBS,
}

# The runtime log is named by whoever launched the session. A hosted session
# logs under its mode's name (`faber__<slug>.log`, from NOCTIS_MODE); a
# project's own `.claude/settings.local.json` hooks log under the vault
# folder (`dev__<slug>.log`, from `--mode dev`). Both are the same job, so
# both are read and the newest line wins.
LOG_NAMES = {
    "dev": ("dev", "faber"),
    "learn": ("learn", "noctua"),
    "research": ("research", "vesper"),
    "maintenance": ("maintenance",),
}

SHIPPED_STAGES = ("Ship", "Done")


def _parse_last_touched(last_touched: object) -> datetime | None:
    """`last_touched` is vault-authored YAML -- a session writing a job's
    frontmatter by hand (via its own Edit/Write tool calls, not through
    vault_io's typed API) can leave it as a bare, unquoted date (`2026-07-22`,
    which PyYAML resolves to a `date` object) or an unquoted full timestamp
    (which PyYAML's implicit timestamp resolver turns into a `datetime`
    directly), not just the quoted ISO string every hand-written example so
    far has used. `datetime.fromisoformat` raises TypeError (not ValueError)
    on a non-str input, which previously crashed this function -- and every
    GET /mode/<name> poll for that mode -- the moment such a value landed
    (found 2026-07-22 via a research job's `last_touched: 2026-07-22`).
    Normalizing every real type PyYAML can hand back here, rather than
    trusting the file to always match the convention, closes the class
    rather than just this one instance.
    """
    if last_touched is None:
        return None
    if isinstance(last_touched, datetime):
        return last_touched
    if isinstance(last_touched, date):
        return datetime(last_touched.year, last_touched.month, last_touched.day, tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(last_touched))
    except ValueError:
        return None


def _log_tail(log_path: Path) -> tuple[datetime | None, bool]:
    """(time of the last line, whether it is the clean-close sentinel)."""
    lines = log_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None, False
    last_line = lines[-1]
    # Anchored, not a bare substring match: a real tool-call line is
    # "<timestamp> <tool_name> <summary...>", where <summary> could itself
    # happen to contain the literal text "SESSION_END" (e.g. editing
    # mark_session_end.py) and would previously have been misread as a
    # clean close. The sentinel mark_session_end.py actually writes is
    # exactly two tokens: "<timestamp> SESSION_END". Found in the 2026-07-21
    # ship-gate review.
    parts = last_line.split(" ")
    closed = len(parts) == 2 and parts[1] == "SESSION_END"
    try:
        return datetime.fromisoformat(parts[0]), closed
    except ValueError:
        return None, closed


def _job_last_activity(folder: str, slug: str, last_touched: object) -> tuple[datetime | None, bool]:
    """Returns (last_activity_time, closed_cleanly). Runtime log activity
    (if present) is a more precise signal than last_touched -- it reflects
    real tool calls, not just whenever the job context happened to be
    written. With two logs for one job, the newest line decides both.
    """
    closed_cleanly = False
    last_activity = _parse_last_touched(last_touched)
    newest_log: datetime | None = None

    for name in LOG_NAMES.get(folder, (folder,)):
        log_path = RUNTIME_DIR / f"{name}__{slug}.log"
        if not log_path.exists():
            continue
        log_time, closed = _log_tail(log_path)
        if log_time is None:
            continue
        if newest_log is None or log_time > newest_log:
            newest_log, closed_cleanly = log_time, closed

    if newest_log is not None and (last_activity is None or newest_log > last_activity):
        last_activity = newest_log
    return last_activity, closed_cleanly


def flag_stale_jobs(folder: str, now: datetime | None = None) -> list[str]:
    """Scans a mode's job folders, flags any that look abandoned
    mid-session. Returns the slugs newly flagged this pass. Writes
    `flagged: true` into the job's own context.md, which is the one place
    the flag is read from.
    """
    now = now or datetime.now(timezone.utc)
    base = FLAGGABLE.get(folder)
    if not base or not vault_io.file_exists(base):
        return []
    newly_flagged = []

    for slug in vault_io.list_subdirs(base):
        job_path = f"{base}/{slug}/context.md"
        if not vault_io.file_exists(job_path):
            continue
        try:
            metadata, content = vault_io.read_frontmatter(job_path)
        except ValueError:
            continue
        if metadata.get("flagged") or metadata.get("stage") in SHIPPED_STAGES:
            continue

        last_activity, closed_cleanly = _job_last_activity(folder, slug, metadata.get("last_touched"))
        if closed_cleanly or last_activity is None:
            continue
        if now - last_activity <= STALE_THRESHOLD:
            continue

        metadata["flagged"] = True
        vault_io.write_frontmatter(job_path, metadata, content)
        newly_flagged.append(slug)

    return newly_flagged


def flag_pass(now: datetime | None = None) -> dict[str, list[str]]:
    """Every flaggable folder, once. What nightshift runs before its scan."""
    return {folder: flag_stale_jobs(folder, now) for folder in FLAGGABLE}
