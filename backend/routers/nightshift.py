from fastapi import APIRouter

router = APIRouter(prefix="/nightshift", tags=["nightshift"])


@router.get("/inbox")
def get_staged_inbox():
    # TODO: read staged proposals from the nightshift inbox directory per
    # SPEC.md PRD "Nightshift inbox review lives inside Echo's profile".
    raise NotImplementedError


@router.post("/inbox/{item_id}/accept")
def accept_inbox_item(item_id: str):
    # TODO: git-diff apply on accept, per SPEC.md user flow 4.
    raise NotImplementedError


@router.post("/inbox/{item_id}/reject")
def reject_inbox_item(item_id: str):
    raise NotImplementedError
