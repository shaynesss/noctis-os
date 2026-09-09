"""v2 session routes — the shell's connection to the orchestrator.

Separate from `session.py`, which launches v1's fire-and-forget terminal
surfaces and is still live. v2 sessions are *hosted*: the orchestrator owns
the process and streams its output here, which is what makes live monitoring
possible at all (a v1 deferral the spec restores for exactly this reason).

**Transport: SSE over POST, not EventSource.** Every route carries mandatory
bearer auth, and `EventSource` cannot set an Authorization header -- the
alternative would be a token in the query string, which lands in logs and
process listings. A POST whose response is a stream keeps the token in a
header, and the frontend reads it with fetch + a ReadableStream.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from orchestrator.driver import (
    MODE_MODELS, PERMISSION_CYCLE, Image, SessionSpec, one_shot,
)
from orchestrator.events import EngineError
from orchestrator.manager import SessionManager
from orchestrator.store import ConversationStore
from orchestrator.wire import blocks_from_messages, to_sse

router = APIRouter(prefix="/v2/sessions", tags=["sessions"])

# One manager per process: it owns the concurrency budget, and two of them
# would each independently believe they may run the cap.
_manager = SessionManager()

# History outlives the window: the shell can be closed and reopened, and the
# transcript is still there. Also what Stats reads -- every number on that
# page comes from rows written here, never from an in-memory tally that a
# restart would reset to zero.
_store = ConversationStore()

# A session's cwd becomes a subprocess working directory, so it is a path
# from the client reaching exec -- the same class of input as the job_slug
# traversal found in the 2026-07-21 review. Confined to the home directory:
# broad enough for any real project, closed to `/etc` and friends.
_HOME = Path.home().resolve()


def _safe_cwd(raw: str) -> Path:
    """Resolve and confine a client-supplied working directory."""
    path = Path(raw).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=400, detail=f"No such directory: {raw}")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {raw}")
    # `resolve` first, so a symlink pointing out of home cannot smuggle a
    # path past this check.
    if resolved != _HOME and _HOME not in resolved.parents:
        raise HTTPException(status_code=403, detail="Working directory must be inside the home directory")
    return resolved


class InlineImage(BaseModel):
    media_type: str
    data: str          # base64, no data: prefix

    @field_validator("media_type")
    @classmethod
    def _supported(cls, v: str) -> str:
        if v not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
            raise ValueError(f"Unsupported image type: {v}")
        return v


class LaunchRequest(BaseModel):
    mode: str
    prompt: str = Field(min_length=1)
    cwd: str
    permission_mode: str = "manual"
    resume_id: str | None = None
    # Sent with the turn rather than written to disk first. The engine takes
    # them in a stream-json message, so there is no file to keep, no path in
    # the transcript, and no Read call standing between the picture and the
    # answer.
    images: list[InlineImage] = Field(default_factory=list, max_length=8)
    # Overrides the mode's default model for this session only.
    model: str | None = None


@router.post("")
async def launch(req: LaunchRequest) -> StreamingResponse:
    """Start (or resume) a session, streaming its events as they arrive."""
    if req.mode not in MODE_MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {req.mode}")
    if req.permission_mode not in PERMISSION_CYCLE:
        # bypassPermissions is deliberately absent from the cycle, so this
        # also refuses it over the wire rather than only in the UI. A guard
        # that exists only in the client is not a guard.
        raise HTTPException(status_code=400, detail=f"Invalid permission mode: {req.permission_mode}")

    try:
        spec = SessionSpec(
            mode=req.mode,
            prompt=req.prompt,
            permission_mode=req.permission_mode,
            resume_id=req.resume_id,
            cwd=_safe_cwd(req.cwd),
            images=[Image(media_type=i.media_type, data=i.data) for i in req.images],
            model=req.model,
        )
    except ValueError as exc:
        # An unknown model, refused where it is named rather than at spawn.
        raise HTTPException(status_code=400, detail=str(exc))

    # A `sessions` row is the *conversation*, not the turn.
    #
    # Opening a new row per turn meant the second turn of a resumed session
    # tried to claim an engine id the first row already held, and
    # engine_session_id is UNIQUE -- so every follow-up message failed with a
    # constraint error. It also scattered one conversation's transcript
    # across a row per turn, which would have made history unreadable long
    # after the crash stopped being the obvious symptom.
    #
    # Opened before the stream either way, so a session that dies on spawn is
    # still recorded: that is something that happened, and hiding it would
    # make the failure invisible in history.
    row_id = _store.find_by_engine_id(req.resume_id) if req.resume_id else None
    if row_id is not None:
        _store.reopen(row_id)
    else:
        row_id = _store.open_session(req.mode, cwd=str(spec.cwd), title=req.prompt[:120])

    # The prompt is recorded here because nothing else does: `record()` folds
    # engine *events*, and the user's own message is not one of them. Without
    # this every stored transcript is a column of answers with no questions.
    _store.add_message(row_id, "user", req.prompt)

    async def stream():
        state = "done"
        try:
            async for _handle, event in _manager.start(spec):
                _store.record(row_id, req.mode, event)
                if getattr(event, "fatal", False):
                    state = "failed"
                yield to_sse(event)
        except asyncio.CancelledError:
            # The window closed or the tab went away. Let it unwind: the
            # manager's `finally` still marks the handle, so a disconnect
            # cannot leave a session looking permanently "running".
            state = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 - must reach the transcript
            # An orchestrator bug would otherwise end the stream with no
            # explanation, which the UI cannot distinguish from a session
            # that finished silently.
            state = "failed"
            yield to_sse(EngineError(message=f"orchestrator failure: {exc}", fatal=True))
        finally:
            # In `finally` so a disconnect or a crash still closes the row.
            # A session left as 'running' forever is the silently-frozen
            # state CLAUDE.md's failure containment exists to prevent.
            _store.close_session(row_id, state)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # no proxy buffering; a buffered stream is not a stream
        },
    )


@router.get("")
def list_sessions() -> dict:
    """Live and finished sessions. The shell reads this on start so tabs
    survive a window reload -- the process outlives the web view."""
    return {
        "sessions": [
            {
                "local_id": h.local_id,
                "mode": h.mode,
                "state": h.state,
                "session_id": h.session_id,
                "resumable": h.resumable,
                "cwd": str(h.spec.cwd) if h.spec.cwd else None,
                "started_at": h.started_at.isoformat() if h.started_at else None,
                "ended_at": h.ended_at.isoformat() if h.ended_at else None,
            }
            for h in _manager.sessions.values()
        ],
        "running": len(_manager.running),
        "queued": len(_manager.queued),
        "max_concurrent": _manager.max_concurrent,
    }


@router.get("/limits")
def limits() -> dict:
    """The rolling windows, or nulls before any session has reported them.

    Nulls rather than zeros: zero utilisation and "not yet known" would
    otherwise render identically, and the difference decides whether there
    is room to start another session.
    """
    lim = _manager.limits
    if lim is None:
        return {"known": False, "five_hour": None, "seven_day": None,
                "using_overage": False}
    return {
        "known": True,
        "five_hour": {"used": lim.five_hour_used, "resets_at": lim.five_hour_resets_at},
        "seven_day": {"used": lim.seven_day_used, "resets_at": lim.seven_day_resets_at},
        "using_overage": lim.using_overage,
    }


@router.get("/stats")
def stats() -> dict:
    """Everything the Stats page shows, from recorded rows.

    Read from the store rather than from the manager's memory: a restart
    would zero an in-process tally, and a lifetime figure that resets when
    the backend reloads is worse than no figure at all.
    """
    life = _store.lifetime_tokens()
    return {
        # Totals include the CLI's background tier. Leaving it out is exactly
        # the undercount the parser had until 2026-09-08 -- ~900 input tokens
        # a turn -- and "what have I used" is the question these answer.
        "lifetime": {
            "input": life["input"],
            "output": life["output"],
            "cached": life["cached"],
            "turns": life["turns"],
            "since": life["since"],
            # Kept separate so the page can show what the background tier
            # cost rather than burying it inside a larger number.
            "aux_input": life["input"] - life["primary_input"],
            "aux_output": life["output"] - life["primary_output"],
            # API list price for everything run so far. Named list_cost, not
            # cost or spend, because it is what these turns WOULD have cost
            # on the API and not what anything charged — the subscription's
            # marginal cost per turn is zero. See events.Usage.
            "list_cost": round(life["list_cost"], 2),
        },
        "by_mode": [
            {"mode": r["mode"], "input": r["input"], "output": r["output"], "turns": r["turns"]}
            for r in _store.usage_by_mode()
        ],
        # Sessions per day for the contribution grid. Only days with activity
        # are returned; the grid fills the gaps, which keeps the payload
        # proportional to what happened rather than to the window.
        "activity": [
            {"day": r["day"], "sessions": r["sessions"]}
            for r in _store.daily_activity(days=365)
        ],
    }


@router.get("/history")
def history(limit: int = 25) -> dict:
    """Past conversations, newest first.

    The shell reads this on launch, so closing the window stops losing work.
    Sessions the engine can still resume are marked: a conversation whose
    engine id we never learned (it died on spawn) is history you can read but
    not continue, and the two must not look alike.
    """
    return {
        "sessions": [
            {
                "id": r["id"],
                "mode": r["mode"],
                "title": r["title"] or "(untitled)",
                "cwd": r["cwd"],
                "state": r["state"],
                "engine_id": r["engine_session_id"],
                "resumable": bool(r["engine_session_id"]) and r["state"] != "failed",
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
            }
            for r in _store.recent_sessions(limit=limit)
        ]
    }


@router.get("/history/{session_id}")
def transcript(session_id: int) -> dict:
    """One conversation, as the blocks the shell renders.

    Rendered server-side into the same shapes the live stream produces, so a
    restored transcript is indistinguishable from one just streamed -- the UI
    has one way to draw a conversation, not two that can drift.
    """
    row = _store.db.execute(
        "SELECT * FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No session {session_id}")
    return {
        "id": row["id"],
        "mode": row["mode"],
        "title": row["title"] or "(untitled)",
        "cwd": row["cwd"],
        "engine_id": row["engine_session_id"],
        "resumable": bool(row["engine_session_id"]) and row["state"] != "failed",
        "blocks": blocks_from_messages(_store.transcript(session_id)),
    }


@router.delete("/history/{session_id}")
def delete_conversation(session_id: int) -> dict:
    """Delete a conversation and everything recorded under it.

    Real deletion, not a hidden flag: the store exists so history is
    trustworthy, and a list that quietly withholds rows it still holds is
    worse than one that forgets. The vault keeps anything promoted out of a
    session, so this destroys the transcript, not the work.

    Usage rows go too. Leaving them would keep a deleted conversation's
    tokens in the lifetime totals, so Stats would disagree with History about
    what happened.
    """
    row = _store.db.execute("SELECT id FROM sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No session {session_id}")

    # messages_fts is an external-content table with a delete trigger on
    # messages, so removing the rows keeps the search index in step.
    _store.db.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    _store.db.execute("DELETE FROM usage WHERE session_id=?", (session_id,))
    _store.db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    _store.db.commit()
    return {"deleted": session_id}


# Regenerate once the conversation has moved this far past the recap it has.
# A recap describing the first third of a long session is worse than none,
# because it reads as current.
RECAP_STALE_AFTER = 6

RECAP_PROMPT = """Summarise this conversation in ONE sentence, for the person who was in it,
as a reminder of where they left off. Present tense. Name what is being worked on and what
came last. No preamble, no quotes, no markdown — output only the sentence.

CONVERSATION:
"""


@router.get("/history/{session_id}/recap")
async def recap(session_id: int) -> dict:
    """A one-line reminder of what a conversation is about.

    Generated on the cheap tier and cached on the row, so reopening the same
    conversation does not pay for it again. Regenerated only once the
    conversation has moved on enough that the stored line would mislead.

    Returns recap: null rather than erroring when there is nothing to
    summarise or the engine is unavailable — a missing recap should quietly
    not appear, never break the transcript it sits above.
    """
    row = _store.db.execute(
        "SELECT id, recap, recap_at FROM sessions WHERE id=?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No session {session_id}")

    count = _store.message_count(session_id)
    if count < 2:
        return {"recap": None}          # nothing has happened worth recapping
    if row["recap"] and count - row["recap_at"] < RECAP_STALE_AFTER:
        return {"recap": row["recap"], "cached": True}

    # Newest messages, not oldest: the reminder you want is where the
    # conversation got to, and the tail is also what a long transcript would
    # otherwise lose to truncation.
    rows = _store.transcript(session_id)[-40:]
    body = "\n".join(f"{r['role']}: {(r['content'] or '')[:600]}" for r in rows)
    if not body.strip():
        return {"recap": None}

    try:
        text = await one_shot(RECAP_PROMPT + body[-8000:])
    except Exception:  # noqa: BLE001 - a recap must never break the transcript
        return {"recap": None}

    line = " ".join(text.split())
    if not line:
        return {"recap": None}
    _store.save_recap(session_id, line, count)
    return {"recap": line, "cached": False}
