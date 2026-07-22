import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

import vault_io
from nightshift import apply

router = APIRouter(prefix="/nightshift", tags=["nightshift"])

STATE_PATH = "modes/nightshift/state.md"

# Matches _log_decision's own format below -- log.md is the durable record
# (vault CLAUDE.md's write discipline), this is a read-back of exactly what
# that function writes, not a separate schema to keep in sync by hand.
_DECISION_LINE = re.compile(
    r"^- (?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \[nightshift\] "
    r"(?P<decision>accepted|rejected)(?: \((?P<detail>[^)]*)\))?: "
    r"(?P<slug>\S+) \(from (?P<origin_mode>\S+)\) — (?P<description>.*)$"
)


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
    """Apply + verify's Apply half (settings.md stage 3): a deterministic
    git-diff-shaped apply, not session judgment. Applies before removing
    from the inbox -- a failed apply must leave the item still pending
    review rather than silently losing it.
    """
    state, _ = vault_io.read_frontmatter(STATE_PATH)
    item = _find_item(state.get("inbox", []), item_id)

    proposal_path = f"modes/nightshift/inbox/{item_id}.md"
    proposal_text = vault_io.read_file(proposal_path) if vault_io.file_exists(proposal_path) else ""

    try:
        applied_target = apply.apply_proposal(proposal_text)
    except apply.DiffApplyError as exc:
        raise HTTPException(status_code=422, detail=f"Diff apply failed, item still pending: {exc}") from exc

    cursor_advance = apply.parse_cursor_advance(proposal_text)
    if cursor_advance:
        apply.advance_lessons_cursor(*cursor_advance)

    _remove_from_inbox(item_id)
    _archive_proposal(item_id)
    _log_decision(item, "accepted" + (f" (applied to {applied_target})" if applied_target else ""))
    return {"accepted": True, "item": item, "applied_to": applied_target}


@router.post("/inbox/{item_id}/reject")
def reject_inbox_item(item_id: str):
    item = _remove_from_inbox(item_id)
    _archive_proposal(item_id)
    _log_decision(item, "rejected")
    return {"rejected": True, "item": item}


@router.get("/history")
def get_decision_history(limit: int = 50):
    """Past accept/reject decisions, most recent first -- read back out of
    log.md rather than a separate store, since log.md already is the
    durable record and _log_decision below already writes one line per
    decision in a fixed, parseable shape. Echo's card had no way to see
    what happened to an item after it left the inbox; this is that view.
    """
    lines = vault_io.read_file("log.md").splitlines()
    entries = [m.groupdict() for line in lines if (m := _DECISION_LINE.match(line))]
    entries.reverse()
    return entries[:limit]


@router.get("/archive/{item_id}")
def get_archived_proposal(item_id: str):
    """The full proposal text for a past decision -- accept/reject move the
    file to archive/ rather than deleting it (see _archive_proposal),
    specifically so this stays readable after the decision is made.
    """
    proposal_path = f"modes/nightshift/archive/{item_id}.md"
    if not vault_io.file_exists(proposal_path):
        raise HTTPException(status_code=404, detail=f"No archived proposal for: {item_id}")
    return {"slug": item_id, "proposal": vault_io.read_file(proposal_path)}


def _log_decision(item: dict, decision: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    entry = (
        f"- {timestamp} [nightshift] {decision}: {item.get('slug')} "
        f"(from {item.get('origin_mode')}) — {item.get('description')}\n"
    )
    existing = vault_io.read_file("log.md")
    vault_io.write_file("log.md", existing + entry)
