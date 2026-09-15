"""Session routes: what the shell needs around a terminal.

A session is a real interactive `claude` in a pseudo-terminal the shell
hosts (PTY-MIGRATION.md). Nothing here streams a conversation any more;
what remains is the argv a terminal spawns with, the status-line reports it
sends back, history read from the CLI's own transcripts, and stats.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import interactive
import vault_io
from engine import MODE_MODELS
from orchestrator import jsonl
from orchestrator.store import ConversationStore
from transcript import blocks_from_messages

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/sessions", tags=["sessions"])

# The rolling windows, as last reported. A dataclass rather than the old
# Limits event: the stream that carried that event is gone, and this is the
# only reader left. Newest wins whichever terminal reported it -- the windows
# are a property of the account, not of one session.
@dataclass
class Windows:
    five_hour_used: float
    five_hour_resets_at: int
    seven_day_used: float
    seven_day_resets_at: int
    using_overage: bool = False


_limits: Windows | None = None

# How many terminals the shell may have open at once. Advisory: the shell
# reports it, nothing here enforces it -- a terminal is a process the shell
# owns, and a cap enforced by a backend that does not own the process would
# be a number that lies. Ceiling of nine, because nobody has needed more.
MAX_CONCURRENT_CEILING = 9
def max_concurrent() -> int:
    try:
        return max(1, min(MAX_CONCURRENT_CEILING, int(os.environ.get("NOCTIS_MAX_CONCURRENT", "4"))))
    except ValueError:
        return 4

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
    # An empty path is `Path(".")`, which resolves to wherever the backend
    # happens to be running -- inside home, so the confinement below let it
    # through and a session opened in the backend's own directory. Found by
    # the route sweep; nothing legitimate sends an empty cwd.
    if not raw or not raw.strip():
        raise HTTPException(status_code=400, detail="A working directory is required")
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


@router.get("")
def list_sessions() -> dict:
    """What is live right now, as the terminals themselves report it.

    A terminal is live if its status line has reported within the last
    half-minute -- the CLI re-runs it every five seconds while the session
    is up, so silence longer than that is a session that has gone.
    """
    cutoff = time.time() - 30
    live = [
        {"slot": k, "session_id": v.get("session_id"),
         "model": (v.get("model") or {}).get("id"),
         "cwd": (v.get("workspace") or {}).get("current_dir")}
        for k, v in _statusline.items()
        if k.startswith("term-") and v.get("reported_at", 0) >= cutoff
    ]
    return {"running": len(live), "queued": 0, "max_concurrent": max_concurrent(),
            "live": live}


@router.get("/interactive-args")
def interactive_args(mode: str, cwd: str, resume_id: str | None = None,
                     slot: str | None = None, prompt: str | None = None) -> dict:
    """The argv for a session the shell hosts in a pseudo-terminal.

    The Rust side owns the terminal and knows nothing about modes; this owns
    the mode and knows nothing about terminals. See `interactive.py` for why
    this is not `build_command` with a flag. `slot` is the shell's name for
    the terminal, baked into the status-line command so reports come back
    labelled with it.
    """
    # Resolved and confined here, the same way the old launch route did it:
    # the Rust side hands this straight to the process as its working
    # directory and does not expand `~`, so a remembered "~/Developer/x"
    # would otherwise be a literal directory called "~".
    try:
        args = interactive.spawn_args(mode, str(_safe_cwd(cwd)), resume_id,
                                      slot=slot, prompt=prompt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if resume_id:
        # A conversation deleted from history and then resumed is wanted
        # again; without this its transcript would grow behind a tombstone
        # and never be filed. See `store.unforget`.
        _store.unforget(resume_id)
    return args


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
    taken, refreshed = jsonl.index_new(_store, _mode_of)
    return {"indexed": taken, "refreshed": refreshed, "count": len(taken)}


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
    # Whether there is anything to resume. The CLI assigns a session id at
    # start but writes the transcript on the first message, so a terminal
    # that was opened and never spoken to has an id that `--resume` cannot
    # find -- and a shell that remembered it came back to "No conversation
    # found" instead of a fresh session. The shell remembers the id only
    # once this is true.
    tp = payload.get("transcript_path")
    payload["transcript_exists"] = bool(tp) and Path(str(tp)).is_file()
    # Keyed by the shell's slot name when it gave one, so the strip can ask
    # for its own terminal's reading; the session id is the fallback for a
    # session the shell did not start.
    _statusline[slot if slot and slot != "-" else sid] = payload
    if mode in MODE_MODELS and sid != "unknown":
        _mode_of[sid] = mode

    # The rolling windows are a property of the account, not of one session,
    # so the newest report from any terminal is the right answer for all of
    # them -- the same "newest wins" the manager applies to Limits events.
    #
    # Shape-checked rather than trusted: the payload is whatever this CLI
    # version writes, and this route runs every five seconds for every
    # terminal. A field that arrives as a string instead of an object must
    # cost one skipped reading, not a traceback per terminal per five
    # seconds until the CLI is downgraded. The report itself is kept either
    # way -- the slot is live, whatever its numbers look like.
    rl = payload.get("rate_limits")
    five = rl.get("five_hour") if isinstance(rl, dict) else None
    seven = rl.get("seven_day") if isinstance(rl, dict) else None
    if isinstance(five, dict) and isinstance(seven, dict):
        global _limits
        try:
            _limits = Windows(
                five_hour_used=float(five.get("used_percentage") or 0) / 100,
                five_hour_resets_at=int(five.get("resets_at") or 0),
                seven_day_used=float(seven.get("used_percentage") or 0) / 100,
                seven_day_resets_at=int(seven.get("resets_at") or 0),
                using_overage=bool(payload.get("using_overage", False)),
            )
        except (TypeError, ValueError):
            pass  # a window whose numbers are not numbers is no reading
    return {"ok": True}


@router.delete("/statusline/{slot}")
def statusline_close(slot: str) -> dict:
    """The shell says a terminal has gone.

    Liveness is otherwise "reported within half a minute", which is right
    for a terminal that died without saying so and wrong for one the shell
    watched exit: it stayed in the live count for thirty seconds after its
    pane said "session ended". The shell knows the instant, so it says.
    Idempotent -- a slot that was never there, or already closed, is fine.
    """
    _statusline.pop(slot, None)
    return {"closed": slot}


@router.get("/statusline/all")
def statusline_all() -> dict:
    """Every slot's newest reading, in one call.

    The shell polls this once for all of its terminals rather than once per
    terminal: it needs each slot's session id to remember the arrangement
    (a remembered slot reopens with `--resume`), and the model/context of
    the one on screen for the bar. Session-keyed entries -- sessions the
    shell did not start -- are left out; they are not slots.
    """
    return {"slots": {k: v for k, v in _statusline.items() if k.startswith("term-")}}


@router.get("/limits")
def limits() -> dict:
    """The rolling windows, or nulls before any session has reported them.

    Nulls rather than zeros: zero utilisation and "not yet known" would
    otherwise render identically, and the difference decides whether there
    is room to start another session.
    """
    global _limits_seen
    lim = _limits
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
    # The lifetime figure is read from the CLI's own transcripts, not from
    # rows the recorder wrote. Step 4 of PTY-MIGRATION.md §7, taken on the
    # evidence of step 3: of sixteen sessions both readers saw, one agreed,
    # and the recorder was short by 2-5x -- output tokens included, which
    # cache re-reads cannot explain. The transcript is the more complete
    # source, and it also counts sessions Noctis never hosted.
    disk = jsonl.lifetime_tokens_cached()
    return {
        "lifetime": {
            "input": disk["input"],
            "output": disk["output"],
            "cached": disk["cached"],
            "cache_write": disk["cache_write"],
            "turns": disk["turns"],
            "since": disk["since"][:10] if disk["since"] else life["since"],
            # API list price for everything run so far, priced from the same
            # transcripts the counts above come from. Named list_cost, not
            # cost or spend, because it is what these turns WOULD have cost
            # on the API and not what anything charged — the subscription's
            # marginal cost per turn is zero. See orchestrator.pricing.
            "list_cost": disk["list_cost"],
            "priced_turns": disk["priced_turns"],
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
    row = _store.db.execute("SELECT id, engine_session_id FROM sessions WHERE id=?",
                            (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No session {session_id}")

    # Tombstoned first. The row is indexed from a transcript the CLI keeps on
    # disk, and deleting the row does not delete the file -- the end-to-end
    # sweep deleted a conversation and the next indexing pass filed it
    # straight back, as `general`, under a title nobody chose. The tombstone
    # is what makes "delete" mean it.
    if row["engine_session_id"]:
        _store.forget(row["engine_session_id"])

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
