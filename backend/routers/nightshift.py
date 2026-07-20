from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

import vault_io

router = APIRouter(prefix="/nightshift", tags=["nightshift"])

STATE_PATH = "modes/nightshift/state.md"


def _find_item(inbox: list, item_id: str) -> dict:
    for item in inbox:
        if item.get("slug") == item_id:
            return item
    raise HTTPException(status_code=404, detail=f"No staged item: {item_id}")


def _remove_from_inbox(item_id: str) -> dict:
    metadata, content = vault_io.read_frontmatter(STATE_PATH)
    inbox = metadata.get("inbox", [])
    item = _find_item(inbox, item_id)
    metadata["inbox"] = [i for i in inbox if i.get("slug") != item_id]
    vault_io.write_frontmatter(STATE_PATH, metadata, content)
    return item


def _archive_proposal(item_id: str) -> None:
    proposal_path = f"modes/nightshift/inbox/{item_id}.md"
    if vault_io.file_exists(proposal_path):
        vault_io.move_file(proposal_path, f"modes/nightshift/archive/{item_id}.md")


@router.get("/inbox")
def get_staged_inbox():
    """Lightweight index — one row per staged item, what Echo's card
    actually renders. Full content lives per-item, see GET /inbox/{item_id}.
    """
    metadata, _ = vault_io.read_frontmatter(STATE_PATH)
    return metadata.get("inbox", [])


@router.get("/inbox/{item_id}")
def get_inbox_item(item_id: str):
    metadata, _ = vault_io.read_frontmatter(STATE_PATH)
    item = _find_item(metadata.get("inbox", []), item_id)
    proposal_path = f"modes/nightshift/inbox/{item_id}.md"
    if not vault_io.file_exists(proposal_path):
        raise HTTPException(status_code=404, detail=f"No proposal file for: {item_id}")
    return {**item, "proposal": vault_io.read_file(proposal_path)}


@router.post("/inbox/{item_id}/accept")
def accept_inbox_item(item_id: str):
    item = _remove_from_inbox(item_id)

    # NOTE: applying the item's actual content (a settings methodology diff,
    # a research verdict, etc.) is mode-specific and depends on each mode's
    # own proposal-generation existing first — not yet built. This endpoint
    # covers the generic accept mechanism (remove from inbox, archive the
    # proposal file, log the decision); mode-specific apply logic is a
    # follow-up once a real producer exists.
    _archive_proposal(item_id)
    _log_decision(item, "accepted")
    return {"accepted": True, "item": item}


@router.post("/inbox/{item_id}/reject")
def reject_inbox_item(item_id: str):
    item = _remove_from_inbox(item_id)
    _archive_proposal(item_id)
    _log_decision(item, "rejected")
    return {"rejected": True, "item": item}


def _log_decision(item: dict, decision: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    entry = (
        f"- {timestamp} [nightshift] {decision}: {item.get('slug')} "
        f"(from {item.get('origin_mode')}) — {item.get('description')}\n"
    )
    existing = vault_io.read_file("log.md")
    vault_io.write_file("log.md", existing + entry)
