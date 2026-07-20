from fastapi import APIRouter, HTTPException

import vault_io

router = APIRouter(prefix="/mode", tags=["mode"])

VALID_MODES = {"dev", "learn", "research", "settings", "nightshift"}


@router.get("/{name}")
def get_mode_state(name: str):
    if name not in VALID_MODES:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {name}")

    # state.md is the lightweight index the profile overlay and world ambient
    # badges read — not every job file individually (SPEC.md EDD "State files
    # and the state-schema contract").
    metadata, _ = vault_io.read_frontmatter(f"modes/{name}/state.md")
    return metadata
