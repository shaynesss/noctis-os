from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import launch_surfaces
import vault_io

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
        launch_surfaces.launch_dev(project_path, prompt, model=request.model)
        surface = "vscode"
    else:
        job_label = request.job_slug or "no active job"
        launch_surfaces.launch_terminal(request.mode, job_label, prompt, model=request.model)
        surface = "terminal"

    return {"launched": True, "mode": request.mode, "surface": surface}
