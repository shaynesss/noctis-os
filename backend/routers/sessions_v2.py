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
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

import interactive
import jobs
import vault_io
from permissions import registry as permission_registry
from orchestrator.driver import (
    EFFORT_CYCLE, MODE_MODELS, OPENING_PROMPT, PERMISSION_CYCLE, Image, SessionSpec,
    one_shot,
)
from orchestrator import jsonl
from orchestrator.events import EngineError, Limits
from orchestrator.manager import SessionManager
from orchestrator.store import ConversationStore
from orchestrator.wire import blocks_from_messages, to_sse

log = logging.getLogger(__name__)

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
    # Empty only when `opener` is set, in which case the server supplies the
    # text. Checked below rather than by min_length, which rejected the
    # opener before the handler could substitute anything.
    prompt: str = ""
    cwd: str
    permission_mode: str = "manual"
    resume_id: str | None = None
    # True when the shell opened a mode session with nothing typed. The
    # server supplies the opener and titles the conversation for what it is,
    # rather than titling it with the opener's own text.
    opener: bool = False
    # Sent with the turn rather than written to disk first. The engine takes
    # them in a stream-json message, so there is no file to keep, no path in
    # the transcript, and no Read call standing between the picture and the
    # answer.
    images: list[InlineImage] = Field(default_factory=list, max_length=8)
    # Overrides the mode's default model for this session only.
    model: str | None = None
    # How hard the engine thinks on this turn. The chip that used to set the
    # permission mode sets this instead: every mode now spawns with the same
    # tools and one shared allowlist, so the permission mode changes little a
    # person would notice, while effort changes the answer.
    effort: str = "high"


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
    if req.effort not in EFFORT_CYCLE:
        # Same reasoning as above: refused over the wire, not only in the UI.
        raise HTTPException(status_code=400, detail=f"Invalid effort: {req.effort}")

    # The server supplies the opener, so the conversation can be titled for
    # what it is rather than with the opener's own text.
    if not req.opener and not req.prompt.strip():
        raise HTTPException(status_code=422, detail="A prompt is required")
    prompt = OPENING_PROMPT if req.opener else req.prompt

    # The job whose `project_path` is this directory is the job this session
    # is about to work on. Resolved here rather than sent as a request field:
    # no new parameter to keep in sync, and the mapping is the one already
    # made by opening that directory.
    #
    # It travels in the spawn's argv, not through a file. `render()` used to
    # write the composed prompt into a per-mode config dir and was called
    # here for exactly that; those dirs are gone, and for a few hours after
    # the cutover this still resolved the job context correctly and then
    # composed it into a directory nothing read.
    cwd = _safe_cwd(req.cwd)
    job_context = jobs.job_brief(req.mode, cwd)

    try:
        spec = SessionSpec(
            mode=req.mode,
            prompt=prompt,
            permission_mode=req.permission_mode,
            effort=req.effort,
            job_context=job_context,
            resume_id=req.resume_id,
            cwd=cwd,
            images=[Image(media_type=i.media_type, data=i.data) for i in req.images],
            model=req.model,
            # The vault, always, as a second allowed directory.
            #
            # The engine sandboxes file access to the working directory, so a
            # Faber session in a repo could not read its own methodology, job
            # context or lessons — all of which live in the vault. The flag
            # existed and nothing set it, so every session ran with the half
            # of the system it is supposed to think with out of reach.
            #
            # It is the only directory added. Widening further would trade
            # away the sandbox, which is doing real work: the failures you
            # see when a session reaches into the home folder are it
            # refusing, and that is correct.
            vault_path=vault_io.get_vault_path(),
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
        title = f"{req.mode} session" if req.opener else req.prompt[:120]
        row_id = _store.open_session(req.mode, cwd=str(spec.cwd), title=title)

    # The prompt is recorded here because nothing else does: `record()` folds
    # engine *events*, and the user's own message is not one of them. Without
    # this every stored transcript is a column of answers with no questions.
    # The opener is not something you said, so it is not recorded as such.
    if not req.opener:
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
        # Live counts first: this is what the status bar reads, and the spec
        # puts live/max sessions on the same row as the limit windows because
        # they answer one question together -- whether there is room to start
        # something now.
        "running": len(_manager.running),
        "queued": len(_manager.queued),
        "max_concurrent": _manager.max_concurrent,
        "live": [
            {
                "local_id": h.local_id,
                "mode": h.mode,
                "cwd": str(h.spec.cwd) if h.spec.cwd else None,
                "model": h.spec.resolved_model,
                "state": h.state,
                # Seconds the turn has been running, so the UI shows a
                # duration without needing a clock the backend does not have.
                "elapsed": (
                    (datetime.now(timezone.utc) - h.started_at).total_seconds()
                    if h.started_at else 0.0
                ),
            }
            for h in [*_manager.running, *_manager.queued]
        ],
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
    }


@router.get("/interactive-args")
def interactive_args(mode: str, cwd: str, resume_id: str | None = None,
                     slot: str | None = None) -> dict:
    """The argv for a session the shell hosts in a pseudo-terminal.

    The Rust side owns the terminal and knows nothing about modes; this owns
    the mode and knows nothing about terminals. See `interactive.py` for why
    this is not `build_command` with a flag. `slot` is the shell's name for
    the terminal, baked into the status-line command so reports come back
    labelled with it.
    """
    try:
        return interactive.spawn_args(mode, cwd, resume_id, slot=slot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# The most recent status-line payload, and the session it came from.
#
# In memory rather than stored: it is a live reading, worth nothing once it is
# stale, and a restart should show "unknown" rather than yesterday's number.
# Keyed by session so several open terminals do not overwrite each other.
_statusline: dict[str, dict] = {}


# Which Noctis mode launched which interactive session. The transcript on disk
# does not say -- its `mode` is the CLI's permission mode -- so the indexer
# reads this when it files a terminal session into history. Filled by the
# statusLine, which is the first thing a session says about itself.
_mode_of: dict[str, str] = {}


@router.post("/index")
def index_transcripts() -> dict:
    """File every transcript history has not seen.

    The second door into the `sessions` table. `store.record` only sees
    sessions Noctis streams; a terminal session, or one started in VS Code,
    exists on disk and nowhere in the interface until this runs. The shell
    calls it when a terminal session ends; Stats calls it on each visit so
    the count is current. Idempotent by engine id.
    """
    taken = jsonl.index_new(_store, _mode_of)
    return {"indexed": taken, "count": len(taken)}


@router.post("/statusline")
async def statusline(payload: dict, mode: str | None = None,
                     slot: str | None = None) -> dict:
    """Where an interactive session reports what the stream used to.

    Claude Code runs the configured `statusLine` command on every render and
    hands it this on stdin: `rate_limits.five_hour`/`seven_day`,
    `context_window`, `effort`, `cost`, `session_id` and `transcript_path`.
    Forwarding it is what lets the status bar know the 5h and 7d windows
    without a `stream-json` turn in flight -- and unlike the stream, it
    survives a page reload, because the numbers live here rather than in
    React state.

    Accepts whatever shape arrives. This is a hot path on every render of
    every open terminal, and a validation error here would put a traceback in
    the middle of somebody's session.
    """
    sid = str(payload.get("session_id") or "unknown")
    # Stamped here rather than trusted from the payload: the CLI reports what
    # it last learned from an API response, and the bar shows how old that is.
    payload["reported_at"] = time.time()
    # Keyed by the shell's slot name when it gave one, so the strip can ask
    # for its own terminal's reading; the session id is the fallback for a
    # session the shell did not start.
    _statusline[slot if slot and slot != "-" else sid] = payload
    if mode in MODE_MODELS and sid != "unknown":
        _mode_of[sid] = mode

    # The rolling windows are a property of the account, not of one session,
    # so the newest report from any terminal is the right answer for all of
    # them -- the same "newest wins" the manager applies to Limits events.
    rl = payload.get("rate_limits") or {}
    five, seven = rl.get("five_hour"), rl.get("seven_day")
    if five and seven:
        _manager.limits = Limits(
            five_hour_used=float(five.get("used_percentage", 0)) / 100,
            five_hour_resets_at=int(five.get("resets_at", 0)),
            seven_day_used=float(seven.get("used_percentage", 0)) / 100,
            seven_day_resets_at=int(seven.get("resets_at", 0)),
            using_overage=bool(payload.get("using_overage", False)),
        )
    return {"ok": True}


@router.get("/statusline")
def statusline_read(session_id: str | None = None, slot: str | None = None) -> dict:
    """The newest status-line reading, for the bar.

    By slot when the shell asks for one of its own terminals; by session id
    for anything else; the newest of all when neither is given.
    """
    if slot:
        return {"payload": _statusline.get(slot)}
    if session_id:
        return {"payload": _statusline.get(session_id)}
    newest = max(_statusline.values(), key=lambda p: p.get("cost", {}).get(
        "total_duration_ms", 0), default=None)
    return {"payload": newest, "sessions": len(_statusline)}


@router.get("/limits")
def limits() -> dict:
    """The rolling windows, or nulls before any session has reported them.

    Nulls rather than zeros: zero utilisation and "not yet known" would
    otherwise render identically, and the difference decides whether there
    is room to start another session.
    """
    global _limits_seen
    lim = _manager.limits
    if lim is None:
        return {"known": False, "five_hour": None, "seven_day": None,
                "using_overage": False}
    # When this reading arrived, tracked by identity so it is right whichever
    # door it came through -- a stream event replaces the object, a status
    # line replaces the object, and either way a new object is a new reading.
    # The bar shows the age, because a hosted session only learns the windows
    # from its own API responses: an idle terminal reports the same figure
    # for as long as it sits there while other sessions move the account on.
    # "33%, 4m ago" is honest; "33%" beside a CLI showing 36% looks broken.
    if _limits_seen is None or _limits_seen[0] is not lim:
        _limits_seen = (lim, time.time())
    return {
        "known": True,
        "five_hour": {"used": lim.five_hour_used, "resets_at": lim.five_hour_resets_at},
        "seven_day": {"used": lim.seven_day_used, "resets_at": lim.seven_day_resets_at},
        "using_overage": lim.using_overage,
        "reported_at": _limits_seen[1],
    }


_limits_seen: tuple[object, float] | None = None


@router.get("/stats")
def stats() -> dict:
    """Everything the Stats page shows, from recorded rows.

    Read from the store rather than from the manager's memory: a restart
    would zero an in-process tally, and a lifetime figure that resets when
    the backend reloads is worse than no figure at all.
    """
    # File anything new first, so a terminal session that just ended is in
    # the lifetime figure and the history list by the time Stats renders.
    jsonl.index_new(_store, _mode_of)
    life = _store.lifetime_tokens()
    return {
        # Totals include the CLI's background tier. Leaving it out is exactly
        # the undercount the parser had until 2026-09-08 -- ~900 input tokens
        # a turn -- and "what have I used" is the question these answer.
        "lifetime": {
            "input": life["input"],
            "output": life["output"],
            "cached": life["cached"],
            "cache_write": life["cache_write"],
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
        # Sessions per day for the contribution grid. Only days with activity
        # are returned; the grid fills the gaps, which keeps the payload
        # proportional to what happened rather than to the window.
        "activity": [
            {"day": r["day"], "sessions": r["sessions"]}
            for r in _store.daily_activity(days=365)
        ],
        # The same number read from the CLI's own transcripts, beside the
        # recorder's. This is the migration's gate (PTY-MIGRATION.md §7 step
        # 3): the default switches to the transcript reader once the two
        # agree over real use, and this is where that agreement is watched.
        # `transcripts` counts sessions the recorder never saw -- terminals,
        # VS Code -- so it is expected to be larger; `diff` is per session
        # both saw, and that is the one that should be boring.
        "transcripts": jsonl.lifetime_tokens_cached(),
        "diff": jsonl.diff_against(_store),
    }


@router.get("/history")
def history(limit: int = 25, mode: str | None = None, resumable: bool = False) -> dict:
    """Past conversations, newest first.

    The shell reads this on launch, so closing the window stops losing work.
    Sessions the engine can still resume are marked: a conversation whose
    engine id we never learned (it died on spawn) is history you can read but
    not continue, and the two must not look alike.

    `mode` and `resumable` narrow it before the limit applies, which is the
    only way to ask "the newest General conversation I can continue" and get
    an answer. Filtering the page client-side cannot: the limit has already
    chosen the rows.
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
            for r in _store.recent_sessions(limit=limit, mode=mode, resumable_only=resumable)
        ]
    }


@router.get("/history/by-engine/{engine_id}")
def transcript_by_engine(engine_id: str) -> dict:
    """The same conversation, found by the id the *engine* knows it as.

    The shell remembers an arrangement of tabs by engine id, because that is
    the id it holds for a live session and the one `--resume` takes. Turning
    that back into a conversation used to mean scanning the recent-history
    page and matching -- so a tab opened before the last 25 rows was simply
    not found, and a reload quietly dropped it. A lookup has no window.

    Declared above the `{session_id}` route: that one takes an int, and
    `by-engine` reaching it first would be a 422 rather than this.
    """
    row_id = _store.find_by_engine_id(engine_id)
    if row_id is None:
        raise HTTPException(status_code=404, detail=f"No session for engine id {engine_id}")
    return transcript(row_id)


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


# ----------------------------------------------------------- permissions
#
# Three routes for one conversation between three processes: the MCP server
# asks, the shell shows and answers, the CLI acts on the result.


class PermissionAsk(BaseModel):
    mode: str = "general"
    tool: str
    args: dict = Field(default_factory=dict)


class PermissionDecision(BaseModel):
    decision: str
    # Question text -> the label chosen for it. Only AskUserQuestion sends
    # this; for every other tool the decision itself is the whole answer.
    answers: dict[str, str] | None = None

    @field_validator("decision")
    @classmethod
    def _known(cls, v: str) -> str:
        if v not in ("allow", "deny"):
            raise ValueError("decision must be allow or deny")
        return v


@router.post("/permissions/ask")
async def permission_ask(body: PermissionAsk) -> dict:
    """Called by the MCP permission tool. Blocks until answered or expired.

    Run off the event loop: the wait is a threading.Event held for up to three
    minutes, and doing that on the loop would stop every other request in the
    process -- including the poll this is waiting for an answer from, which
    would deadlock the feature against itself.
    """
    req = await asyncio.to_thread(
        permission_registry.ask, body.mode, body.tool, body.args
    )
    return {"decision": req.decision, "expired": req.expired, "answers": req.answers}


@router.get("/permissions/pending")
def permission_pending() -> dict:
    """What is waiting on you right now."""
    return {"pending": permission_registry.pending()}


@router.post("/permissions/{request_id}/decide")
def permission_decide(request_id: str, body: PermissionDecision) -> dict:
    """404 rather than a silent success when the request is gone: it expired
    while the dialog was still on screen, and saying 'allowed' about a session
    that already gave up and moved on would be a lie the UI then displays."""
    if not permission_registry.decide(  # type: ignore[arg-type]
        request_id, body.decision, body.answers,
    ):
        raise HTTPException(status_code=404, detail="No pending request by that id")
    return {"id": request_id, "decision": body.decision}


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



# Tools that produce a file, and the argument naming it. Derived from what a
# session actually did rather than declared anywhere: a turn that writes a
# file has already told us so in its tool call, and asking the model to
# additionally announce its outputs would be a second source that can
# disagree with the first.
_ARTIFACT_TOOLS = {
    "Write": "file_path",
    "Edit": "file_path",
    "NotebookEdit": "notebook_path",
}


@router.get("/history/{session_id}/artifacts")
def artifacts(session_id: int) -> dict:
    """Files this conversation created or changed.

    One entry per path, not per call: editing the same file eleven times is
    one artifact you might want to look at, and eleven rows of the same name
    is the tool log again under a different heading.
    """
    row = _store.db.execute("SELECT id FROM sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No session {session_id}")

    seen: dict[str, dict] = {}
    for message in _store.transcript(session_id):
        if message["role"] != "tool" or not message["meta"]:
            continue
        try:
            meta = json.loads(message["meta"])
        except ValueError:
            continue
        arg = _ARTIFACT_TOOLS.get(meta.get("tool", ""))
        if not arg:
            continue
        path = (meta.get("args") or {}).get(arg)
        if not path:
            continue

        entry = seen.setdefault(str(path), {
            "path": str(path),
            "name": Path(str(path)).name,
            "tools": [],
            "writes": 0,
            "at": message["created_at"],
        })
        entry["writes"] += 1
        entry["at"] = message["created_at"]          # most recent touch
        if meta["tool"] not in entry["tools"]:
            entry["tools"].append(meta["tool"])

    return {"artifacts": list(seen.values())}


class PromoteRequest(BaseModel):
    # Where in the vault. Validated against the vault root and required to be
    # markdown, the same rule the reader uses: a promote endpoint that can
    # write any path is an arbitrary-write endpoint with a friendly name.
    rel_path: str = Field(min_length=1)
    title: str = Field(min_length=1)
    note: str = ""


@router.post("/history/{session_id}/promote")
def promote(session_id: int, req: PromoteRequest) -> dict:
    """Write a conversation into the vault as a real note.

    The deliberate half of "SQLite with promotion". Nothing reaches the vault
    automatically — the store is a cache of what was said, the vault is what
    was decided, and only a person can tell those apart. This is the route
    that makes the second half of the project's premise reachable at all:
    without it the knowledge never compounds anywhere, it just accumulates in
    a database.
    """
    row = _store.db.execute("SELECT id FROM sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No session {session_id}")

    if not req.rel_path.endswith(".md"):
        raise HTTPException(status_code=400, detail="Promoted notes are markdown")
    try:
        vault_io.resolve_vault_only(req.rel_path)
    except ValueError:
        raise HTTPException(status_code=403, detail="Path escapes the vault")

    try:
        written = _store.promote(
            session_id, vault_io.get_vault_path(), req.rel_path, req.title, req.note,
        )
    except FileExistsError:
        # Never silently: a promoted note may have been edited by hand since,
        # and replacing it would lose work the store never saw.
        raise HTTPException(status_code=409, detail=f"{req.rel_path} already exists")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"path": req.rel_path, "bytes": written.stat().st_size}
