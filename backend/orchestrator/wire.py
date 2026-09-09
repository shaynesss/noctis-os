"""Event → JSON, the shape the frontend actually consumes.

Kept in its own file rather than as `dataclasses.asdict` at the call site,
because this *is* the API contract. `asdict` would silently publish every
field rename as a breaking change to the UI; here a rename is a visible edit
to a mapping, and the tests below it fail loudly.

The tag is `t`, one line per event, newline-delimited JSON over SSE. The
frontend reassembles: TextDelta fragments concatenate into one transcript
block, tool calls pair with their results by id.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

from .events import (
    EngineError, Event, Limits, SessionStart, TextDelta, ThinkingDelta,
    ThinkingProgress, ToolCall, ToolResult, TurnEnd,
)

# Tool output is unbounded -- a Read of a large file, a Bash dump. The
# transcript shows a disclosure row, not the whole payload, so sending
# megabytes to render a collapsed row wastes the connection. Truncation is
# marked so the UI can say "truncated" rather than quietly showing a prefix
# as if it were the whole result.
MAX_RESULT_CHARS = 4000


def to_dict(e: Event) -> dict[str, Any]:
    """One event as the frontend sees it. Unknown types raise rather than
    serialize partially -- a silently dropped event is a transcript with a
    hole in it, which is worse than a failed request."""
    if isinstance(e, SessionStart):
        return {"t": "start", "session_id": e.session_id, "model": e.model,
                "cwd": e.cwd, "tools": list(e.tools)}

    if isinstance(e, TextDelta):
        return {"t": "text", "text": e.text}

    if isinstance(e, ThinkingDelta):
        # `text` is normally empty by design (see events.py). Sent anyway so
        # the frontend never has to guess whether empty means "absent" or
        # "omitted by the model" -- the field being present says which.
        return {"t": "thinking", "text": e.text, "tokens": e.tokens}

    if isinstance(e, ThinkingProgress):
        return {"t": "thinking_progress", "tokens": e.estimated_tokens}

    if isinstance(e, ToolCall):
        # `summary` is computed here rather than in the UI so the in-app
        # transcript and the hook-written runtime log describe a call
        # identically -- one definition of "what this tool call was on".
        return {"t": "tool_call", "id": e.id, "name": e.name, "summary": e.summary}

    if isinstance(e, ToolResult):
        content = e.content or ""
        return {"t": "tool_result", "id": e.id,
                "content": content[:MAX_RESULT_CHARS],
                "truncated": len(content) > MAX_RESULT_CHARS,
                "is_error": e.is_error}

    if isinstance(e, Limits):
        return {"t": "limits",
                "five_hour": {"used": e.five_hour_used, "resets_at": e.five_hour_resets_at},
                "seven_day": {"used": e.seven_day_used, "resets_at": e.seven_day_resets_at},
                "using_overage": e.using_overage}

    if isinstance(e, TurnEnd):
        return {"t": "turn_end", "session_id": e.session_id,
                "duration_ms": e.duration_ms, "stop_reason": e.stop_reason,
                # `model` names the model these counts describe. `aux` is
                # what the turn also spent on the CLI's background tier --
                # separate, because per-turn and per-day are different
                # questions and summing makes the first one wrong.
                "usage": {"input": e.usage.input_tokens,
                          "output": e.usage.output_tokens,
                          "cached": e.usage.cached_tokens,
                          "model": e.usage.model,
                          "aux_input": e.usage.aux_input_tokens,
                          "aux_output": e.usage.aux_output_tokens}}

    if isinstance(e, EngineError):
        return {"t": "error", "message": e.message, "fatal": e.fatal}

    raise TypeError(f"no wire mapping for {type(e).__name__}")


def to_sse(e: Event) -> str:
    """One SSE frame. `data:` plus a blank line, per the format."""
    return f"data: {json.dumps(to_dict(e), separators=(',', ':'))}\n\n"


def blocks_from_messages(rows: Iterable[Any]) -> list[dict[str, Any]]:
    """Stored messages → the transcript blocks the shell renders.

    Lives here with the rest of the contract, so a restored conversation and
    a live one are described by the same shapes -- the UI must not be able to
    tell a reloaded transcript from one it just streamed.

    Tool calls and their results are stored as two rows and rendered as one
    block, paired by the id in their meta. Pairing on adjacency would break
    on the interleaving the live reducer already handles correctly.
    """
    blocks: list[dict[str, Any]] = []
    by_tool_id: dict[str, dict[str, Any]] = {}

    for row in rows:
        role, content = row["role"], row["content"] or ""
        meta = json.loads(row["meta"]) if row["meta"] else {}

        if role == "user":
            blocks.append({"kind": "user", "text": content,
                           "at": str(row["created_at"])[11:16]})
        elif role == "assistant":
            # Deltas were stored as separate rows; rejoin them the way the
            # live reducer does, or a reloaded reply arrives shattered into
            # one paragraph per fragment.
            if blocks and blocks[-1]["kind"] == "text":
                blocks[-1]["text"] += content
            else:
                blocks.append({"kind": "text", "text": content})
        elif role == "thinking":
            blocks.append({"kind": "thinking", "tokens": meta.get("tokens", 0), "ms": 0})
        elif role == "tool":
            block = {"kind": "tool", "id": meta.get("id", ""), "name": meta.get("tool", "tool"),
                     "target": content.split(" ", 1)[-1] if " " in content else "",
                     "meta": "done", "body": ""}
            blocks.append(block)
            if block["id"]:
                by_tool_id[block["id"]] = block
        elif role == "tool_result":
            target = by_tool_id.get(meta.get("id", ""))
            if target is not None:
                target["body"] = content
                target["meta"] = "error" if meta.get("is_error") else "done"
                target["open"] = bool(meta.get("is_error"))
    return blocks
