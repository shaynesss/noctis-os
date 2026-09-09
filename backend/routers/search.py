"""Cross-mode search — one query over conversations and the vault.

A v1 deferral the spec restores, and nearly free: FTS5 over the transcript
and BM25 over the vault both already existed with nothing reading them.

The two are returned as separate lists rather than one merged ranking. Their
scores are not comparable -- different corpora, different lengths, different
index -- so interleaving them would produce an order that looks meaningful
and is not. Which kind of result you want is also usually known before you
search: "what did I say about X" and "what does the vault say about X" are
different questions.
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Query

import vault_io
from orchestrator.store import ConversationStore
from retrieval.index import VaultIndex

router = APIRouter(prefix="/v2/search", tags=["search"])

_store = ConversationStore()

# The vault index is a derived cache, rebuilt on first use in this process.
# Built lazily rather than at import because it walks the whole vault, and
# paying that on every backend reload would make development miserable.
_index: VaultIndex | None = None
_index_lock = threading.Lock()


def _vault_index() -> VaultIndex:
    global _index
    with _index_lock:
        if _index is None:
            idx = VaultIndex(vault_io.get_vault_path())
            idx.rebuild()
            _index = idx
        return _index


@router.get("")
def search(q: str = Query(min_length=2), limit: int = 12) -> dict:
    """Conversations and vault documents matching `q`."""
    conversations = []
    seen_sessions: set[int] = set()
    for row in _store.search(q, limit=limit * 3):
        # One hit per conversation. Several matching messages in the same
        # session are one result to a person looking for that conversation,
        # and letting a long session flood the list buries everything else.
        if row["session_id"] in seen_sessions:
            continue
        seen_sessions.add(row["session_id"])
        conversations.append({
            "session_id": row["session_id"],
            "mode": row["mode"],
            "role": row["role"],
            "excerpt": _excerpt(row["content"], q),
            "at": row["created_at"],
        })
        if len(conversations) >= limit:
            break

    documents = [
        {"path": h.path, "heading": h.heading, "excerpt": h.excerpt, "score": h.score}
        for h in _vault_index().search(q, k=limit)
    ]
    return {"conversations": conversations, "documents": documents}


def _excerpt(content: str, query: str, width: int = 180) -> str:
    """A window around the first matching term, not the opening characters.

    A prefix of the message is very often the least useful part of it -- the
    match is why the row is here, so it is what should be visible.
    """
    text = " ".join((content or "").split())
    lowered = text.lower()
    at = -1
    for term in sorted(query.split(), key=len, reverse=True):
        if len(term) > 2 and (at := lowered.find(term.lower())) != -1:
            break
    if at == -1:
        return text[:width] + ("…" if len(text) > width else "")

    start = max(0, at - width // 3)
    end = min(len(text), start + width)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")
