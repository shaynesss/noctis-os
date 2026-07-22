from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import busy_marker
import launch_surfaces
import vault_io
from session_prompt import extract_session_start_callout

router = APIRouter(prefix="/session", tags=["session"])

VALID_MODES = {"dev", "learn", "research", "settings", "nightshift"}


class LaunchRequest(BaseModel):
    mode: str
    job_slug: str | None = None
    model: str | None = None  # per-job launcher override, Claude family only


@router.post("/launch")
def launch_session(request: LaunchRequest):
    if request.mode not in VALID_MODES:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {request.mode}")
    if request.job_slug is not None and not vault_io.is_safe_slug(request.job_slug):
        # job_slug flows into hook scripts' runtime-log filenames
        # (NOCTIS_JOB_ID / --job-id) -- an unsanitized value here was a path
        # traversal into arbitrary log writes, found in the 2026-07-21
        # ship-gate security review.
        raise HTTPException(status_code=400, detail=f"Invalid job_slug: {request.job_slug!r}")

    methodology = vault_io.read_file(f"modes/{request.mode}/{request.mode}.md")
    lessons = vault_io.read_file(f"modes/{request.mode}/lessons.md")

    job_context = ""
    job_metadata: dict = {}
    if request.job_slug:
        job_metadata, job_context = vault_io.read_frontmatter(
            f"modes/{request.mode}/jobs/{request.job_slug}/context.md"
        )

    prompt = f"{methodology}\n\n---\n\n{lessons}\n\n---\n\n{job_context}"

    if request.mode == "dev":
        project_path = job_metadata.get("project_path")
        if not project_path:
            raise HTTPException(
                status_code=400,
                detail="Dev launches require a job context with a project_path field",
            )
        # Job-context frontmatter (stage/status) never reaches the prompt --
        # only the freeform prose body does (see create_job's docstring).
        # But whether a job's already shipped is exactly a `stage` check,
        # and per this project's own deterministic-where-possible rule that
        # shouldn't be left to the session to infer from prose that's often
        # empty (found live 2026-07-22: portfolio-platform's job context has
        # stage: Ship but zero prose, so dev.md's Patch/Overhaul callout had
        # nothing to condition on and silently skipped). Stamping this one
        # deterministic fact onto the prompt lets the mode file's callout
        # branch on a literal marker instead of guessing from text.
        if job_metadata.get("stage") in ("Ship", "Done"):
            marker = (
                f"[RESUMED-SHIPPED-BUILD stage={job_metadata['stage']} "
                f"status={job_metadata.get('status', '')!r}]"
            )
            prompt = f"{marker}\n\n{prompt}"
        launch_surfaces.launch_dev(
            project_path, prompt, job_slug=request.job_slug, model=request.model
        )
        surface = "vscode"
    else:
        job_label = request.job_slug or "no active job"
        # Delivered as a genuine system-level instruction (--append-system-
        # prompt), not just relying on it sitting at the top of the huge
        # user-turn message below -- found live 2026-07-22 that an ordinary
        # message, however explicit, doesn't reliably carry the same
        # instruction-following weight once thousands more characters of
        # reference material follow it (see session_prompt.py). The full
        # methodology text (callout included) still goes into `prompt`
        # unchanged, for context and the in-doc cross-references to it.
        system_prompt = extract_session_start_callout(methodology)
        launch_surfaces.launch_terminal(
            request.mode,
            job_label,
            prompt,
            job_slug=request.job_slug,
            model=request.model,
            system_prompt=system_prompt,
        )
        surface = "terminal"

    # A runtime marker, not a state.md write -- see busy_marker.py's module
    # docstring for why (a running session's own vault edits to state.md
    # can silently clobber a plain frontmatter field, and did in practice).
    # Setting it true here is deterministic (the backend just performed the
    # launch, no need to infer it); clearing it on the other end is the
    # SessionEnd hook's job (mark_session_end.py), since that's the point
    # that actually knows the session ended (not Stop, which fires after
    # every agent turn -- found live as a second bug, see
    # launch_surfaces.py's _ensure_nondev_hooks docstring).
    busy_marker.set_busy(request.mode)

    return {"launched": True, "mode": request.mode, "surface": surface}
