import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import busy_marker
import staleness
import triggers
import vault_io

router = APIRouter(prefix="/mode", tags=["mode"])

VALID_MODES = {"dev", "learn", "research", "settings", "nightshift"}

# Hook-driven action-feed logs — high-churn, ephemeral, explicitly NOT vault
# content (SPEC.md EDD "State files ... Runtime scratch"). Same directory
# backend/hooks/log_action.py writes to.
RUNTIME_DIR = Path(__file__).parent.parent / "runtime"

# Faber Plan-stage scratch directories for brand-new builds -- dev.md's
# Stage 1 no longer locks a project name/path before Setup, but
# POST /session/launch still hard-requires project_path to exist on the
# job. A new build gets a real, disposable directory here at creation time;
# Setup's first checklist item renames it to the real project location via
# PATCH .../jobs/{slug} with a new project_path (see below).
# NOCTIS_SCRATCH_ROOT override exists so tests (and the vault fixture) don't
# write scratch job directories into the real home directory -- same
# env-var-override pattern as vault_io's VAULT_PATH.
def _scratch_root() -> Path:
    override = os.environ.get("NOCTIS_SCRATCH_ROOT")
    return Path(override) if override else Path.home() / "Developer" / ".scratch"


@router.get("/{name}")
def get_mode_state(name: str):
    if name not in VALID_MODES:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {name}")

    if name in staleness.FLAGGABLE_MODES:
        # Deterministic staleness -> flagged check runs inline here rather
        # than only in a nightly sweep -- this endpoint is already polled
        # every 15s by the World screen, so a dead session shows up live
        # instead of waiting for nightshift's 03:00 run (staleness.py:
        # "Deterministic-where-possible"). Applies to every mode whose own
        # Failure Behavior text promises this (dev/learn/research/settings);
        # nightshift is excluded by design, see staleness.py's docstring.
        staleness.flag_stale_jobs(name)

    # state.md is the lightweight index the profile overlay and world ambient
    # badges read — not every job file individually (SPEC.md EDD "State files
    # and the state-schema contract").
    metadata, content = vault_io.read_frontmatter(f"modes/{name}/state.md")

    # `busy` is a runtime marker (busy_marker.py), not vault content -- always
    # overridden here regardless of whatever value happens to be sitting in
    # state.md's frontmatter, since a session's own direct edits to that file
    # have no way to know the field exists and can silently drop it (found
    # 2026-07-22). This is the only source of truth for busy from this point
    # on; any stale `busy` key still present in a state.md file is inert.
    metadata["busy"] = busy_marker.is_busy(name)

    if name == "settings":
        # Same live-on-every-poll pattern as dev's staleness check --
        # settings.md itself flagged trigger thresholds as an open
        # backend-logic question until this pass (triggers.py).
        computed = triggers.compute_triggers()
        computed_modes = triggers.compute_trigger_modes()
        computed_diffs = triggers.compute_diffs_awaiting_review()
        if (
            metadata.get("triggers") != computed
            or metadata.get("trigger_modes") != computed_modes
            or metadata.get("diffs_awaiting_review") != computed_diffs
        ):
            metadata["triggers"] = computed
            metadata["trigger_modes"] = computed_modes
            metadata["diffs_awaiting_review"] = computed_diffs
            vault_io.write_frontmatter(f"modes/{name}/state.md", metadata, content)

    return metadata


class JobCreate(BaseModel):
    slug: str
    name: str
    project_path: str | None = None
    notes: str = ""


@router.post("/{name}/jobs")
def create_job(name: str, job: JobCreate):
    """Registers a new job — the missing half of "launch stays available
    even idle, since that's how a new build starts" (Interface.md): until
    now nothing ever created a job, so Faber's card stayed idle regardless
    of real work happening, and dev's slack-surface scan had nothing to
    ever find flagged.

    `notes` becomes the job context.md's prose body — the part
    POST /session/launch actually injects into the launch prompt
    (job-context frontmatter is metadata, not prompt content). Without
    it, a scoped launch (e.g. Custos "address this trigger") would open a
    session with no more direction than a bare methodology dump.
    """
    if name not in VALID_MODES:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {name}")
    if not vault_io.is_safe_slug(job.slug):
        raise HTTPException(status_code=400, detail=f"Invalid slug: {job.slug!r}")

    job_path = f"modes/{name}/jobs/{job.slug}/context.md"
    if vault_io.file_exists(job_path):
        raise HTTPException(status_code=409, detail=f"Job already exists: {job.slug}")

    metadata = {
        "name": job.name,
        "stage": "Plan",
        "status": "just started",
        "last_touched": datetime.now(timezone.utc).isoformat(),
    }
    if job.project_path:
        metadata["project_path"] = job.project_path
    elif name == "dev":
        # Brand-new Faber build, no path supplied -- give it a real scratch
        # directory so the launch endpoint's project_path requirement is
        # met from the first session, before a project name is locked.
        scratch_path = _scratch_root() / job.slug
        scratch_path.mkdir(parents=True, exist_ok=True)
        metadata["project_path"] = str(scratch_path)

    vault_io.write_frontmatter(job_path, metadata, job.notes)
    _sync_state_job_entry(name, job.slug, metadata)
    return {"slug": job.slug, **metadata}


class JobUpdate(BaseModel):
    stage: str | None = None
    status: str | None = None
    track: str | None = None
    # staleness.py sets this true, but nothing could ever clear it -- found
    # 2026-07-21 when a real job (this repo's own) got flagged because all
    # the actual work happened via direct file edits rather than a launched
    # session, so the telemetry hooks that would prove it alive never fired.
    # Resuming a flagged job is the natural point to clear it (World.tsx).
    flagged: bool | None = None
    # Setup's first checklist item: rename the Plan-stage scratch directory
    # to the locked project name. A real filesystem move, not just a label
    # change -- see _relocate_project_path below.
    project_path: str | None = None


@router.patch("/{name}/jobs/{slug}")
def update_job(name: str, slug: str, update: JobUpdate):
    """Job-context frontmatter rewrites at stage/track transitions (SPEC.md
    EDD "Hooks"). Updates the job's own context.md and syncs the mirrored
    entry in the mode's state.md — the file the interface actually reads.
    """
    if name not in VALID_MODES:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {name}")
    if not vault_io.is_safe_slug(slug):
        raise HTTPException(status_code=400, detail=f"Invalid slug: {slug!r}")

    job_path = f"modes/{name}/jobs/{slug}/context.md"
    if not vault_io.file_exists(job_path):
        raise HTTPException(status_code=404, detail=f"Unknown job: {slug}")

    metadata, content = vault_io.read_frontmatter(job_path)
    for field in ("stage", "status", "track", "flagged"):
        value = getattr(update, field)
        if value is not None:
            metadata[field] = value
    if update.project_path is not None and update.project_path != metadata.get("project_path"):
        _relocate_project_path(metadata.get("project_path"), update.project_path)
        metadata["project_path"] = update.project_path
    metadata["last_touched"] = datetime.now(timezone.utc).isoformat()
    vault_io.write_frontmatter(job_path, metadata, content)

    _sync_state_job_entry(name, slug, metadata)
    return metadata


def _relocate_project_path(old_path: str | None, new_path: str) -> None:
    """Moves the job's working directory on disk when project_path changes
    via PATCH -- the deterministic half of Setup's "rename the scratch
    directory" checklist item (dev.md Stage 2). Only actually moves
    anything when the old path is a real scratch directory that still
    exists; a job created with an explicit project_path (not a scratch
    dir) or already-renamed job is left untouched.
    """
    if not old_path:
        return
    old = Path(old_path)
    new = Path(new_path)
    if old == new or not old.is_dir() or new.exists():
        return
    new.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old), str(new))


def _sync_state_job_entry(mode: str, slug: str, job_metadata: dict) -> None:
    state_path = f"modes/{mode}/state.md"
    state_meta, state_content = vault_io.read_frontmatter(state_path)
    jobs = state_meta.get("jobs", [])
    entry = {
        "slug": slug,
        "name": job_metadata.get("name", slug),
        "stage": job_metadata.get("stage"),
        "status": job_metadata.get("status"),
        "last_touched": job_metadata.get("last_touched"),
        "flagged": job_metadata.get("flagged", False),
    }
    for i, existing in enumerate(jobs):
        if existing.get("slug") == slug:
            jobs[i] = entry
            break
    else:
        jobs.append(entry)
    state_meta["jobs"] = jobs
    vault_io.write_frontmatter(state_path, state_meta, state_content)


@router.get("/{name}/jobs/{slug}/log")
def get_job_log(name: str, slug: str, lines: int = 50):
    """The interface's poll target for a job's live action feed — one line
    per tool call, written by backend/hooks/log_action.py. Not vault
    content; returns [] rather than 404 for a job with no session run yet.

    Falls back to `{name}__general.log` when the job's own log doesn't
    exist: a session launched with no job bound yet (NOCTIS_JOB_ID defaults
    to "general") logs there, but if it then creates a job mid-session
    (POST /mode/{name}/jobs, e.g. Vesper filing a question as a job partway
    through), the terminal is already running and can't retroactively bind
    to the new slug -- its activity keeps landing in general.log even
    though a job row with a different slug now exists for it. Without this
    fallback that job's action-feed line is permanently empty despite a
    session actively working on it (found 2026-07-22, Vesper's
    brunei-ai-smb-consulting job). Only used when the job-specific log is
    entirely absent, not merged with it, so a job that DOES have its own
    log (a fresh launch with the slug already bound) is unaffected.
    """
    if name not in VALID_MODES:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {name}")
    if not vault_io.is_safe_slug(slug):
        raise HTTPException(status_code=400, detail=f"Invalid slug: {slug!r}")

    log_path = RUNTIME_DIR / f"{name}__{slug}.log"
    if not log_path.exists():
        log_path = RUNTIME_DIR / f"{name}__general.log"
    if not log_path.exists():
        return {"lines": []}
    content = log_path.read_text(encoding="utf-8").splitlines()
    return {"lines": content[-lines:]}
