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
from typing import Any

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
                "usage": {"input": e.usage.input_tokens,
                          "output": e.usage.output_tokens,
                          "cached": e.usage.cached_tokens,
                          "model": e.usage.model}}

    if isinstance(e, EngineError):
        return {"t": "error", "message": e.message, "fatal": e.fatal}

    raise TypeError(f"no wire mapping for {type(e).__name__}")


def to_sse(e: Event) -> str:
    """One SSE frame. `data:` plus a blank line, per the format."""
    return f"data: {json.dumps(to_dict(e), separators=(',', ':'))}\n\n"
