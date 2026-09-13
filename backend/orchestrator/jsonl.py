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
from typing import Any, Iterator

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
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


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
                    # (DOCUMENTATION §12), so the block's *existence* is the
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
    return c


def lifetime_tokens() -> dict[str, int]:
    """One raw number across every transcript on disk, plus what it came from.

    This is what the Stats page's lifetime figure becomes: read from the CLI's
    own files rather than from rows Noctis had to be present to write. It
    therefore counts sessions started in a terminal or in VS Code too, which
    the current figure silently misses.
    """
    total = turns = sessions = 0
    for p in PROJECTS.glob("**/*.jsonl"):
        c = read(p)
        if not c.turns:
            continue
        sessions += 1
        turns += len(c.turns)
        total += c.lifetime
    return {"tokens": total, "turns": turns, "sessions": sessions}


# ------------------------------------------------------------ beside the recorder

import time as _time

# `lifetime_tokens` parses every transcript on disk -- 128 files, the largest
# 15MB -- and Stats asks for it on every visit. Cached on a signature of the
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


def index_new(store, mode_of: dict[str, str], default_mode: str = "general") -> list[str]:
    """Ingest every transcript the store has not seen. Returns the ids taken.

    This is the second door into history (`store.ingest`): terminal sessions
    and VS Code sessions never pass through the recorder, and without this
    they exist on disk and nowhere in the interface. `mode_of` is the
    statusLine's record of which mode launched which session; a transcript it
    does not know -- one started in a terminal outside Noctis -- is filed as
    general rather than guessed at.
    """
    taken: list[str] = []
    for p in PROJECTS.glob("**/*.jsonl"):
        if store.find_by_engine_id(p.stem) is not None:
            continue
        conv = read(p)
        if store.ingest(conv, mode_of.get(p.stem, default_mode)) is not None:
            taken.append(p.stem)
    return taken


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
        seen = read(p).lifetime
        rows.append({"session": p.stem, "recorded": recorded, "transcript": seen,
                     "delta": seen - recorded})
    agree = sum(1 for r in rows if r["delta"] == 0)
    return {"compared": len(rows), "agree": agree, "rows": rows[:12]}
