from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import vault_io

router = APIRouter(prefix="/mode", tags=["mode"])

VALID_MODES = {"dev", "learn", "research", "settings", "nightshift"}

# Hook-driven action-feed logs — high-churn, ephemeral, explicitly NOT vault
# content (SPEC.md EDD "State files ... Runtime scratch"). Same directory
# backend/hooks/log_action.py writes to.
RUNTIME_DIR = Path(__file__).parent.parent / "runtime"


@router.get("/{name}")
def get_mode_state(name: str):
    if name not in VALID_MODES:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {name}")

    # state.md is the lightweight index the profile overlay and world ambient
    # badges read — not every job file individually (SPEC.md EDD "State files
    # and the state-schema contract").
    metadata, _ = vault_io.read_frontmatter(f"modes/{name}/state.md")
    return metadata


class JobUpdate(BaseModel):
    stage: str | None = None
    status: str | None = None
    track: str | None = None


@router.patch("/{name}/jobs/{slug}")
def update_job(name: str, slug: str, update: JobUpdate):
    """Job-context frontmatter rewrites at stage/track transitions (SPEC.md
    EDD "Hooks"). Updates the job's own context.md and syncs the mirrored
    entry in the mode's state.md — the file the interface actually reads.
    """
    if name not in VALID_MODES:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {name}")

    job_path = f"modes/{name}/jobs/{slug}/context.md"
    if not vault_io.file_exists(job_path):
        raise HTTPException(status_code=404, detail=f"Unknown job: {slug}")

    metadata, content = vault_io.read_frontmatter(job_path)
    for field in ("stage", "status", "track"):
        value = getattr(update, field)
        if value is not None:
            metadata[field] = value
    metadata["last_touched"] = datetime.now(timezone.utc).isoformat()
    vault_io.write_frontmatter(job_path, metadata, content)

    _sync_state_job_entry(name, slug, metadata)
    return metadata


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
    """
    if name not in VALID_MODES:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {name}")

    log_path = RUNTIME_DIR / f"{name}__{slug}.log"
    if not log_path.exists():
        return {"lines": []}
    content = log_path.read_text(encoding="utf-8").splitlines()
    return {"lines": content[-lines:]}
