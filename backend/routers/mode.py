from fastapi import APIRouter

router = APIRouter(prefix="/mode", tags=["mode"])


@router.get("/{name}")
def get_mode_state(name: str):
    # TODO: read mode's ambient state from the vault (job-context frontmatter,
    # hook-driven status files) per SPEC.md PRD "Ambient state per character".
    raise NotImplementedError
