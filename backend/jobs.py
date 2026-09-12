"""Job lookup — which job is this session sitting in, and what does it need to know.

A mode session is launched with a working directory, not a job id. The job
is inferred from that directory: each job context carries a `project_path`
in its frontmatter, and the one matching the session's cwd is the job the
session is about to work on. No new field on the launch request, no picker
to keep in sync, and the mapping is the one the person already made when
they opened that directory.

**This module owns the mode-name → vault-directory mapping.** It had been
inline in `mcp/server.py`, and the moment a second caller needed it the
choice was extract or duplicate. Duplicating it is how the two drift: a
mode renamed in one place and not the other fails by returning "no jobs"
rather than by raising, which reads as an empty backlog instead of a bug.
`mcp/server.py` imports it from here now.
"""
from __future__ import annotations

import logging
from pathlib import Path

import vault_io

log = logging.getLogger(__name__)

# Mode names are the interface's; vault directories are the methodology's,
# and they predate the rename. `general` is absent deliberately — it has no
# jobs, and mapping it to something would invent a backlog it never has.
MODE_VAULT_DIR = {
    "faber": "dev",
    "noctua": "learn",
    "vesper": "research",
}

# Maintenance is not under `modes/`. Settings and Nightshift collapsed into
# root-level `maintenance/` on 2026-09-07 as infrastructure rather than a
# mode; only the methodology moved then, because v1's pipeline still read the
# old state paths. The state followed at the Stage 2 cutover (2026-09-12) and
# the two MOVED.md markers are gone with it.
#
# Every vault path for it is named here rather than written as a literal at
# each call site. There were eleven such literals across six files, and the
# mapping had already been restated three times and disagreed twice.
MAINTENANCE = "maintenance"
MAINTENANCE_STATE = f"{MAINTENANCE}/state.md"
MAINTENANCE_LESSONS = f"{MAINTENANCE}/lessons.md"
MAINTENANCE_INBOX = f"{MAINTENANCE}/inbox"
MAINTENANCE_ARCHIVE = f"{MAINTENANCE}/archive"
MAINTENANCE_JOBS = f"{MAINTENANCE}/jobs"

# The prompt gets orientation, not the archive. A job context grows without
# bound — noctis-os's is already ~20KB of prose — and pasting all of it into
# every launch spends tokens on history the session can fetch when it wants
# it. The tail is what is current, so the tail is what is carried, and the
# `job_context` MCP tool remains there for the whole thing.
BRIEF_MAX_CHARS = 2600


# Where a mode's *methodology* lives, which is not always beside its state.
#
# Ordinarily `modes/<dir>/<dir>.md`. Maintenance is the exception, and after
# the 2026-09-12 cutover it is the exception in both directions: its
# methodology and its state both live at root-level `maintenance/`, outside
# `modes/` entirely, because it is infrastructure rather than a mode.
#
# Stated once, here, because it had been restated three times -- jobs.py,
# orchestrator/modes.py and mcp/server.py each carried a copy, and two of
# them disagreed about maintenance before anything called them.
METHODOLOGY_OVERRIDE = {"maintenance": f"{MAINTENANCE}/audit.md"}


def jobs_dir(mode: str) -> str | None:
    """Vault-relative jobs directory for a mode, or None if it has no jobs."""
    if mode == "maintenance":
        return MAINTENANCE_JOBS
    vault_dir = MODE_VAULT_DIR.get(mode)
    return f"modes/{vault_dir}/jobs" if vault_dir else None


def methodology_path(mode: str) -> str | None:
    """Vault-relative path to a mode's methodology, or None if it has none.

    `general` has none by design: it is the mode without a method.
    """
    if override := METHODOLOGY_OVERRIDE.get(mode):
        return override
    vault_dir = MODE_VAULT_DIR.get(mode)
    return f"modes/{vault_dir}/{vault_dir}.md" if vault_dir else None


def find_job_for_cwd(mode: str, cwd: str | Path) -> str | None:
    """The slug whose `project_path` is the session's working directory.

    Exact directory match after resolution, not a prefix test: a session
    opened in a subdirectory of a project is a deliberate scoping choice,
    and `~/Developer` — which is a parent of every project — would match
    all of them under a prefix rule. Wrong job context is worse than none,
    because none is visibly absent and wrong is quietly believed.
    """
    base = jobs_dir(mode)
    if not base or not cwd:
        return None
    try:
        target = Path(cwd).expanduser().resolve()
    except (OSError, RuntimeError):
        return None

    for slug in vault_io.list_subdirs(base):
        try:
            meta, _ = vault_io.read_frontmatter(f"{base}/{slug}/context.md")
        except (FileNotFoundError, ValueError):
            continue
        project_path = meta.get("project_path")
        if not project_path:
            continue
        try:
            if Path(str(project_path)).expanduser().resolve() == target:
                return slug
        except (OSError, RuntimeError):
            continue
    return None


def job_brief(mode: str, cwd: str | Path) -> str | None:
    """Orientation for the job at `cwd`, or None if there isn't one.

    Frontmatter first — stage and status are the two things a session needs
    before it does anything — then the tail of the prose, cut at a paragraph
    boundary so the block never opens mid-sentence.
    """
    slug = find_job_for_cwd(mode, cwd)
    if not slug:
        return None
    base = jobs_dir(mode)
    try:
        meta, body = vault_io.read_frontmatter(f"{base}/{slug}/context.md")
    except (FileNotFoundError, ValueError) as exc:
        log.warning("job context unreadable for %s/%s: %s", mode, slug, exc)
        return None

    lines = [f"**{meta.get('name') or slug}** (`{slug}`)"]
    for field in ("stage", "status"):
        if meta.get(field):
            lines.append(f"- {field}: {meta[field]}")
    if meta.get("flagged"):
        lines.append("- flagged: this job was left stale and has not been cleared")

    body = body.strip()
    if body:
        if len(body) > BRIEF_MAX_CHARS:
            body = body[-BRIEF_MAX_CHARS:]
            # Cut forward to a paragraph break so the excerpt starts at the
            # top of an entry rather than halfway through a sentence that
            # reads as though it were the beginning of one.
            split = body.find("\n\n")
            body = body[split + 2:] if split != -1 else body.lstrip()
            lines.append("\n*(most recent entries; call `job_context` for the full record)*")
        lines.append(f"\n{body}")

    return "\n".join(lines)
