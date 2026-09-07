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
from pydantic import BaseModel, Field

from orchestrator.driver import MODE_MODELS, PERMISSION_CYCLE, SessionSpec
from orchestrator.events import EngineError
from orchestrator.manager import SessionManager
from orchestrator.wire import to_sse

router = APIRouter(prefix="/v2/sessions", tags=["sessions"])

# One manager per process: it owns the concurrency budget, and two of them
# would each independently believe they may run the cap.
_manager = SessionManager()

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


class LaunchRequest(BaseModel):
    mode: str
    prompt: str = Field(min_length=1)
    cwd: str
    permission_mode: str = "manual"
    resume_id: str | None = None


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

    spec = SessionSpec(
        mode=req.mode,
        prompt=req.prompt,
        permission_mode=req.permission_mode,
        resume_id=req.resume_id,
        cwd=_safe_cwd(req.cwd),
    )

    async def stream():
        try:
            async for _handle, event in _manager.start(spec):
                yield to_sse(event)
        except asyncio.CancelledError:
            # The window closed or the tab went away. Let it unwind: the
            # manager's `finally` still marks the handle, so a disconnect
            # cannot leave a session looking permanently "running".
            raise
        except Exception as exc:  # noqa: BLE001 - must reach the transcript
            # An orchestrator bug would otherwise end the stream with no
            # explanation, which the UI cannot distinguish from a session
            # that finished silently.
            yield to_sse(EngineError(message=f"orchestrator failure: {exc}", fatal=True))

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
        return {"known": False, "five_hour": None, "seven_day": None}
    return {
        "known": True,
        "five_hour": {"used": lim.five_hour_used, "resets_at": lim.five_hour_resets_at},
        "seven_day": {"used": lim.seven_day_used, "resets_at": lim.seven_day_resets_at},
        "using_overage": lim.using_overage,
    }
