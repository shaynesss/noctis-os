"""Reading history instead of recording it.

Claude Code writes a complete transcript per session to
`~/.claude/projects/<slugged-cwd>/<session-id>.jsonl` — every message, tool
call, thinking block, and per-turn `usage` — whether it was started by Noctis
or by anything else. 128 of them existed before this file did.

`store.record` folds *stream events* into the same tables. That works only
while Noctis is the one streaming, which is exactly what the PTY migration
stops being true. This reads the CLI's own file instead.

Three properties, tested on 2026-09-13 before any of this was written
(`PTY-MIGRATION.md` §3):

  1. **Written incrementally, not flushed at exit.** A session SIGKILLed
     mid-generation already had its partial output on disk. History survives
     a crash, which is what makes reading it safe.
  2. **`--resume` appends** to the same file rather than forking a new one.
  3. **The CLI names its own conversations** in an `aiTitle` record, so
     titling stops costing an engine call.

Run *beside* `store.record`, not instead of it, until the two agree. That
sequencing is deliberate: the 2026-09-12 cutover removed `launch_config/`
while a guard still required it and broke every spawn.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, NamedTuple

from orchestrator import pricing

PROJECTS = Path.home() / ".claude" / "projects"


@dataclass
class Turn:
    """One assistant response and what it cost."""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    thinking_tokens: int = 0


@dataclass
class Conversation:
    """A transcript, in the shape `ConversationStore` already stores."""
    engine_session_id: str = ""
    cwd: str = ""
    title: str | None = None
    started_at: str = ""
    ended_at: str = ""
    git_branch: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)

    @property
    def lifetime(self) -> int:
        """One raw token count. No split, no tiers.

        The CLI's own background calls -- naming a session, checking quota --
        are not in this file. Measured against the store on 2026-09-13 that is
        146,327 tokens out of 82,174,586: **0.178%**, which does not change a
        stat whose job is to be interesting. The `aux_*` columns exist to
        separate that fraction and retire with the migration.
        """
        return sum(t.input_tokens + t.output_tokens + t.cached_tokens
                   + t.cache_write_tokens for t in self.turns)


def transcript_path(session_id: str) -> Path | None:
    """Find a session's file without knowing which project it belongs to.

    The directory is derived from the cwd the session started in, which the
    caller often does not have -- and a session that changed directory mid-run
    still lives in the one it started in.
    """
    for p in PROJECTS.glob(f"**/{session_id}.jsonl"):
        return p
    return None


def _records(path: Path) -> Iterator[dict[str, Any]]:
    """Yield parsed records, skipping unparseable lines.

    A truncated final line is normal rather than exceptional: the file is
    appended to live, so a read can land mid-write. Skipping one line is
    right; refusing the whole transcript for it is not.
    """
    # Line by line rather than `read_text().splitlines()`: that held the whole
    # file and a second copy of it as a list, and the parsed records on top.
    # Streaming keeps the peak at one line, whatever the file's size.
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


@dataclass
class Usage:
    """What one transcript cost, and nothing else it says."""
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    started_at: str = ""
    # API list price of the turns above, and how many of them it could not
    # price -- a model the table in `pricing` does not know. Kept beside the
    # tokens so the two are always measured over the same turns.
    list_cost: float = 0.0
    unpriced_turns: int = 0

    @property
    def lifetime(self) -> int:
        return (self.input_tokens + self.output_tokens + self.cached_tokens
                + self.cache_write_tokens)


def scan_usage(path: Path) -> Usage:
    """The token figures of one transcript, without building the conversation.

    `read` reconstructs every message body, which is what indexing needs and
    what the lifetime figure does not: the backend sat at 640MB resident after
    one Stats visit because the sum over 155 transcripts held each one's text
    in memory on the way to four integers. This walks the same records and
    keeps the integers. It must agree with `read` to the token --
    `test_jsonl_indexer` holds the two together.
    """
    u = Usage()
    for r in _records(path):
        if ts := r.get("timestamp"):
            if not u.started_at or ts < u.started_at:
                u.started_at = ts
        msg = r.get("message") or {}
        if usage := msg.get("usage"):
            u.turns += 1
            inp = int(usage.get("input_tokens", 0))
            out = int(usage.get("output_tokens", 0))
            cached = int(usage.get("cache_read_input_tokens", 0))
            wrote = int(usage.get("cache_creation_input_tokens", 0))
            u.input_tokens += inp
            u.output_tokens += out
            u.cached_tokens += cached
            u.cache_write_tokens += wrote
            price = pricing.list_price(msg.get("model", ""), inp, out, cached, wrote)
            if price is None:
                u.unpriced_turns += 1
            else:
                u.list_cost += price
    return u


def read(path: Path) -> Conversation:
    """Reconstruct one conversation."""
    c = Conversation(engine_session_id=path.stem)
    stamps: list[str] = []

    for r in _records(path):
        if ts := r.get("timestamp"):
            stamps.append(ts)
        # Last one wins: a session that changes directory should report where
        # it ended up, and `aiTitle` is refined as the conversation develops.
        if cwd := r.get("cwd"):
            c.cwd = cwd
        if branch := r.get("gitBranch"):
            c.git_branch = branch
        if r.get("type") == "ai-title" and r.get("aiTitle"):
            c.title = r["aiTitle"]

        msg = r.get("message") or {}
        role = msg.get("role")
        content = msg.get("content")

        if usage := msg.get("usage"):
            c.turns.append(Turn(
                model=msg.get("model", ""),
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                cached_tokens=int(usage.get("cache_read_input_tokens", 0)),
                cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0)),
                thinking_tokens=int((usage.get("output_tokens_details") or {})
                                    .get("thinking_tokens", 0)),
            ))

        if isinstance(content, str) and role:
            c.messages.append({"role": role, "content": content, "meta": None})
        elif isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                kind = b.get("type")
                if kind == "text" and b.get("text"):
                    c.messages.append({"role": role or "assistant",
                                       "content": b["text"], "meta": None})
                elif kind == "thinking":
                    # Kept even with no text, which is the normal case: models
                    # default to `display: "omitted"`, so reasoning is billed
                    # and never returned. All 34 blocks in the transcript this
                    # was first read against were empty. The transcript shows
                    # thinking as a counter and a duration rather than prose
                    # (DOCUMENTATION §10), so the block's *existence* is the
                    # signal -- guarding on its text dropped every one of them.
                    c.messages.append({"role": "thinking",
                                       "content": b.get("thinking") or "", "meta": None})
                elif kind == "tool_use":
                    c.messages.append({
                        "role": "tool",
                        "content": b.get("name", ""),
                        "meta": json.dumps({"id": b.get("id"),
                                            "args": b.get("input") or {}}),
                    })
                elif kind == "tool_result":
                    body = b.get("content")
                    if isinstance(body, list):
                        body = "".join(x.get("text", "") for x in body
                                       if isinstance(x, dict))
                    c.messages.append({
                        "role": "tool_result",
                        "content": body if isinstance(body, str) else json.dumps(body),
                        "meta": json.dumps({"id": b.get("tool_use_id"),
                                            "is_error": bool(b.get("is_error"))}),
                    })

    if stamps:
        c.started_at, c.ended_at = min(stamps), max(stamps)
    # The CLI names only some of its conversations: 125 of the 140
    # transcripts on this machine had no aiTitle when the indexer first ran
    # over them, and an untitled row in history is a row nobody can pick out.
    # The first thing the person asked is what they came to it for, which
    # beats anything derivable from the reply.
    if not c.title:
        first = next((m["content"] for m in c.messages
                      if m["role"] == "user" and m["content"].strip()), "")
        line = first.strip().split("\n")[0].strip().rstrip("?.!")
        if line:
            c.title = line if len(line) <= 60 else line[:60].rstrip() + "…"
    return c


def lifetime_tokens() -> dict[str, Any]:
    """One raw number across every transcript on disk, plus what it came from.

    This is what the Stats page's lifetime figure becomes: read from the CLI's
    own files rather than from rows Noctis had to be present to write. It
    therefore counts sessions started in a terminal or in VS Code too, which
    the current figure silently misses.

    The list price rides along, summed over exactly these turns. It used to
    come from the store, where only the 120 turns the `-p` engine had priced
    carried a figure -- so a cost over 120 turns sat under token counts over
    eight thousand, and read twenty times low against its own tokens.
    `priced_turns` says how many of `turns` the figure covers; it is short
    only by turns whose model the price table does not know.
    """
    total = turns = sessions = unpriced = 0
    inp = out = cached = cache_write = 0
    cost = 0.0
    since = ""
    for p in PROJECTS.glob("**/*.jsonl"):
        u = scan_usage(p)
        if not u.turns:
            continue
        sessions += 1
        turns += u.turns
        total += u.lifetime
        # The four bars Stats draws beside the one number. Still one number:
        # these are its parts, not a second tier.
        inp += u.input_tokens
        out += u.output_tokens
        cached += u.cached_tokens
        cache_write += u.cache_write_tokens
        cost += u.list_cost
        unpriced += u.unpriced_turns
        if u.started_at and (not since or u.started_at < since):
            since = u.started_at
    return {"tokens": total, "turns": turns, "sessions": sessions,
            "input": inp, "output": out, "cached": cached,
            "cache_write": cache_write, "since": since,
            "list_cost": round(cost, 2), "priced_turns": turns - unpriced}


# ------------------------------------------------------------ beside the recorder

import time as _time

# `lifetime_tokens` scans every transcript on disk -- 155 files, the largest
# 26MB -- and Stats asks for it on every visit. Cached on a signature of the
# directory (file count and newest mtime) rather than a clock: a session that
# is still writing bumps the mtime, so the number moves while it is live and
# holds still while nothing is.
_lifetime_cache: tuple[tuple[int, float], dict[str, int]] | None = None
_lifetime_stamp = 0.0
_LIFETIME_MIN_INTERVAL_S = 5.0     # a signature check still stats every file


def _signature() -> tuple[int, float]:
    files = list(PROJECTS.glob("**/*.jsonl"))
    newest = max((p.stat().st_mtime for p in files), default=0.0)
    return len(files), newest


def lifetime_tokens_cached() -> dict[str, int]:
    """`lifetime_tokens`, recomputed only when a transcript has changed."""
    global _lifetime_cache, _lifetime_stamp
    now = _time.monotonic()
    if _lifetime_cache and now - _lifetime_stamp < _LIFETIME_MIN_INTERVAL_S:
        return _lifetime_cache[1]
    sig = _signature()
    if _lifetime_cache and _lifetime_cache[0] == sig:
        _lifetime_stamp = now
        return _lifetime_cache[1]
    result = lifetime_tokens()
    _lifetime_cache, _lifetime_stamp = (sig, result), now
    return result


import threading as _threading

# One pass at a time. Stats calls this on every visit and the shell calls it
# when a terminal ends, so two can easily land together -- and twelve did,
# under a concurrency sweep, all finding the same new transcript and all
# trying to file it. The writers then queued on SQLite's lock past its busy
# timeout and the stats route answered 500. A pass that is already running
# will file everything there is to file; a second one has nothing to add, so
# it returns at once rather than waiting to discover that.
_indexing = _threading.Lock()


class IndexPass(NamedTuple):
    """What one pass did: the ids it filed for the first time, and the ids
    whose rows it brought up to a transcript that had grown."""
    taken: list[str]
    refreshed: list[str]


def mode_for_cwd(cwd: str | None, default: str = "general") -> str:
    """A transcript Noctis did not launch carries no mode signal, but its
    working directory does: a session in a dev job's `project_path` is
    Faber's work whoever opened it -- the VS Code session that built most of
    2026-09-15 was filed as General and its commits credited to whichever
    tab was open. Everywhere else stays the default."""
    if not cwd:
        return default
    try:
        import jobs
        from pathlib import Path as _P
        # The transcript's cwd is wherever the session last was -- often a
        # subdirectory -- so walk up to the project root, stopping at home.
        here = _P(cwd).expanduser().resolve()
        home = _P.home().resolve()
        for candidate in (here, *here.parents):
            if candidate == home or candidate == candidate.parent:
                break
            if jobs.find_job_for_cwd("faber", candidate):
                return "faber"
        return default
    except Exception:  # noqa: BLE001 -- no vault, no jobs: the default is the honest answer
        return default


def index_new(store, mode_of: dict[str, str], default_mode: str = "general") -> IndexPass:
    """Ingest every transcript the store has not seen, and re-read every one
    that has grown since it was filed.

    This is the door into history (`store.ingest`): terminal sessions and VS
    Code sessions arrive here from the transcript the CLI itself wrote.
    `mode_of` is the statusLine's record of which mode launched which
    session; a transcript it does not know -- one started in a terminal
    outside Noctis -- is filed as general rather than guessed at.

    Returns `[]` immediately if another pass is running; see `_indexing`.
    """
    if not _indexing.acquire(blocking=False):
        return IndexPass([], [])
    try:
        taken: list[str] = []
        refreshed: list[str] = []
        for p in PROJECTS.glob("**/*.jsonl"):
            # Deleted on purpose. The file is the CLI's and stays; the row
            # must not come back.
            if store.is_forgotten(p.stem):
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            state = store.transcript_state(p.stem)
            if state is None:
                conv = read(p)
                if store.ingest(conv, mode_of.get(p.stem) or mode_for_cwd(conv.cwd, default_mode), size) is not None:
                    taken.append(p.stem)
                continue
            row_id, source, indexed = state
            # A row the recorder wrote is not behind a transcript; a row the
            # indexer wrote is, whenever the file is not the size it read.
            # Filed once and never revisited was how a session indexed
            # mid-life stayed truncated in history -- found 2026-09-14,
            # 3,387 messages filed of 4,219 on disk.
            if source != "transcript" or size == indexed:
                continue
            known = mode_of.get(p.stem)
            store.refresh(row_id, read(p), size,
                          mode=known if known and known != default_mode else None)
            refreshed.append(p.stem)
        return IndexPass(taken, refreshed)
    finally:
        _indexing.release()


def diff_against(store, limit: int = 50) -> dict:
    """Where the recorder and the transcripts disagree, session by session.

    The migration's step 4 -- switching the default -- is gated on this being
    boring. A session both saw should count the same tokens; one they count
    differently is either a session that continued outside Noctis (the
    transcript is right and larger) or a real defect in one reader.
    """
    rows = []
    for p in sorted(PROJECTS.glob("**/*.jsonl"), key=lambda q: q.stat().st_mtime,
                    reverse=True)[:limit]:
        recorded = store.tokens_for_engine_id(p.stem)
        if recorded is None:
            continue
        seen = scan_usage(p).lifetime
        rows.append({"session": p.stem, "recorded": recorded, "transcript": seen,
                     "delta": seen - recorded})
    agree = sum(1 for r in rows if r["delta"] == 0)
    return {"compared": len(rows), "agree": agree, "rows": rows[:12]}
