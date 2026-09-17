"""Deterministic staleness -> flagged mechanism for job-holding modes
(CLAUDE.md's "Deterministic-where-possible" rule: staleness checks are
backend code, never left to session judgment). Every mode whose methodology
says "session death marks the job context stale-and-flagged" -- dev, learn,
research, and maintenance's own jobs.

A job is flagged when a session worked it, stopped without writing the
SESSION_END sentinel (backend/hooks/mark_session_end.py, a SessionEnd hook,
deliberately not Stop, which fires after every turn rather than on real
session termination), that was longer ago than STALE_THRESHOLD, and nobody
has written the job's own record since.

Those are four separate facts and the last two carry the weight. The
runtime log is the record of *sessions*; `last_touched` is the record of
the *job*, written by whoever last looked at it. A job whose session died in
August and whose status was updated in September to say it is deliberately
on hold has been seen, and is not news. A job already at Ship or Done did
not die mid-build and is never flagged either.

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
from jobs import JOB_FOLDERS

RUNTIME_DIR = Path(__file__).parent / "runtime"

# A judgment call, not a spec-locked number: long enough that a normal
# working break doesn't false-positive, short enough that a genuinely dead
# session shows up the same day rather than waiting for a nightly sweep.
STALE_THRESHOLD = timedelta(hours=6)

# Every folder that holds jobs. Shared with the Inbox and the acknowledge
# route, so what can be flagged is exactly what can be seen and cleared.
FLAGGABLE = JOB_FOLDERS

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


def _last_session(folder: str, slug: str) -> tuple[datetime | None, bool]:
    """When a session last did anything on this job, and whether it closed
    cleanly. `None` when no session ever has.

    Only the runtime log, deliberately. It is the record of sessions, and
    `last_touched` is the record of the job: mixing them was the bug. With
    two logs for one job, the newest line decides both answers.
    """
    closed_cleanly = False
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

    return newest_log, closed_cleanly


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

        # The log is the session; `last_touched` is you. Keeping them apart
        # is the whole mechanism.
        #
        # No log means no session we can see ever worked this job, so there
        # is no death to report: `last_touched` alone cannot tell a job
        # parked in July from one abandoned in July.
        died_at, closed_cleanly = _last_session(folder, slug)
        if died_at is None or closed_cleanly:
            continue
        if now - died_at <= STALE_THRESHOLD:
            continue
        # Written since: whoever wrote the job's own record after the
        # session stopped has already dealt with it, whatever the session
        # did. On its first run (2026-09-17) this pass flagged two jobs
        # whose sessions had ended without a clean close in July and
        # August, and whose status had been updated in September to say
        # they were deliberately on hold. Taking the later of the two
        # timestamps hid exactly the fact that answers this.
        seen = _parse_last_touched(metadata.get("last_touched"))
        if seen and seen >= died_at:
            continue
        # Or acknowledged from the Inbox, which is the same statement made
        # by a button rather than by an edit.
        acknowledged = _parse_last_touched(metadata.get("flag_acknowledged_at"))
        if acknowledged and acknowledged >= died_at:
            continue

        metadata["flagged"] = True
        vault_io.write_frontmatter(job_path, metadata, content)
        newly_flagged.append(slug)

    return newly_flagged


def flag_pass(now: datetime | None = None) -> dict[str, list[str]]:
    """Every flaggable folder, once. What nightshift runs before its scan."""
    return {folder: flag_stale_jobs(folder, now) for folder in FLAGGABLE}
