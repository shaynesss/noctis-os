from fastapi import APIRouter

router = APIRouter(prefix="/session", tags=["session"])


@router.post("/launch")
def launch_session():
    # TODO: construct the mode's invocation (methodology file + working
    # context + model flag) and open it in that mode's launch surface
    # (Terminal.app via osascript, or VS Code for Dev) per SPEC.md EDD
    # "Session launch surfaces, per mode".
    raise NotImplementedError
