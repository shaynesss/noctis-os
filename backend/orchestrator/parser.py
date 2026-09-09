"""`stream-json` → normalized `Event`s — Noctis v2 Stage 2 item 1.

Pure and synchronous: one JSON line in, zero or more Events out. No process
handling, no I/O. That split is deliberate — the parser is the part with all
the shape knowledge and none of the moving parts, so it can be tested
exhaustively against a recorded fixture without spawning anything.

Written against a real captured stream (`tests/fixtures/stream_with_tools.jsonl`),
not against assumption. Two things that shape looks wrong until you see it:

  * `tool_result` blocks arrive on a **user** event, not an assistant one —
    Claude Code echoes tool output back as a user turn.
  * `thinking`, `tool_use` and `text` are all blocks *inside* one assistant
    event's message content, so a single line can yield several Events.
  * a `thinking` block's text is **empty** under the models' default
    `display: "omitted"`. It is still emitted — its presence is the signal.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Iterator

from .events import (
    EngineError, Event, Limits, SessionStart, TextDelta, ThinkingDelta,
    ThinkingProgress, ToolCall, ToolResult, TurnEnd, Usage,
)

# Emitted by the CLI for its own bookkeeping; nothing above this layer needs
# them. Named rather than silently ignored, so a genuinely new event type
# still reaches the `unknown` branch and can be noticed.
IGNORED_SUBTYPES = {"hook_started", "hook_response", "status"}


def _split_model_usage(
    model_usage: dict[str, Any], usage: dict[str, Any]
) -> tuple[str, int, int]:
    """Name the model that answered, and total what the others spent.

    `modelUsage` is keyed by model and routinely holds two entries: the
    session's model, and a cheaper tier the CLI uses for background tasks.
    This used to take `next(iter(keys))` — the first key in dict order —
    which named the *background* model while the token counts beside it came
    from top-level `usage`, i.e. the primary. The name and the numbers
    disagreed, verified live on 2026-09-08.

    Top-level `usage` is exactly the primary model's entry, so the primary is
    identified by matching it rather than guessed at: an exact match, with
    largest-output as the fallback for a shape that stops holding.
    """
    if not model_usage:
        return "", 0, 0

    want = (int(usage.get("input_tokens", -1)), int(usage.get("output_tokens", -1)))
    primary = ""
    for name, m in model_usage.items():
        if (int(m.get("inputTokens", -2)), int(m.get("outputTokens", -2))) == want:
            primary = name
            break
    if not primary:
        # The model that produced the most output is the one that answered.
        primary = max(model_usage, key=lambda k: int(model_usage[k].get("outputTokens", 0)))

    aux_in = sum(int(m.get("inputTokens", 0)) for n, m in model_usage.items() if n != primary)
    aux_out = sum(int(m.get("outputTokens", 0)) for n, m in model_usage.items() if n != primary)
    return primary, aux_in, aux_out


def parse_line(line: str) -> list[Event]:
    """Zero or more Events from one stream-json line. Never raises: a bad
    line becomes an EngineError, because an orchestrator that dies on one
    malformed frame is worse than one that reports it and keeps reading."""
    line = line.strip()
    if not line:
        return []
    try:
        d = json.loads(line)
    except json.JSONDecodeError:
        return [EngineError(f"unparseable stream line: {line[:120]}")]

    kind = d.get("type")

    if kind == "system":
        sub = d.get("subtype")
        if sub == "init":
            return [SessionStart(
                session_id=d.get("session_id", ""),
                model=d.get("model", ""),
                cwd=d.get("cwd", ""),
                tools=list(d.get("tools") or []),
            )]
        if sub == "thinking_tokens":
            return [ThinkingProgress(int(d.get("estimated_tokens", 0)))]
        if sub in IGNORED_SUBTYPES:
            return []
        return []

    if kind == "assistant":
        out: list[Event] = []
        for b in (d.get("message") or {}).get("content") or []:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text" and b.get("text"):
                out.append(TextDelta(b["text"]))
            elif bt == "thinking":
                # Emitted even when the text is empty: the block's presence
                # is the signal that reasoning happened, and empty is the
                # normal case under display:"omitted".
                out.append(ThinkingDelta(text=b.get("thinking") or ""))
            elif bt == "tool_use":
                out.append(ToolCall(
                    id=b.get("id", ""),
                    name=b.get("name", ""),
                    args=b.get("input") or {},
                ))
        return out

    if kind == "user":
        out = []
        for b in (d.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                out.append(ToolResult(
                    id=b.get("tool_use_id", ""),
                    content=_flatten(b.get("content")),
                    is_error=bool(b.get("is_error")),
                ))
        return out

    if kind == "rate_limit_event":
        info = d.get("rate_limit_info") or {}
        w = info.get("unifiedWindows") or {}
        five, seven = w.get("five_hour") or {}, w.get("seven_day") or {}
        return [Limits(
            five_hour_used=float(five.get("utilization", 0.0)),
            five_hour_resets_at=int(five.get("resetsAt", 0)),
            seven_day_used=float(seven.get("utilization", 0.0)),
            seven_day_resets_at=int(seven.get("resetsAt", 0)),
            using_overage=bool(info.get("isUsingOverage")),
        )]

    if kind == "result":
        u = d.get("usage") or {}
        primary, aux_in, aux_out = _split_model_usage(d.get("modelUsage") or {}, u)
        ev: list[Event] = [TurnEnd(
            session_id=d.get("session_id", ""),
            usage=Usage(
                input_tokens=int(u.get("input_tokens", 0)),
                output_tokens=int(u.get("output_tokens", 0)),
                cached_tokens=int(u.get("cache_read_input_tokens", 0)),
                cache_write_tokens=int(u.get("cache_creation_input_tokens", 0)),
                model=primary,
                aux_input_tokens=aux_in,
                aux_output_tokens=aux_out,
                context_tokens=(int(u.get("input_tokens", 0))
                                + int(u.get("cache_read_input_tokens", 0))
                                + int(u.get("cache_creation_input_tokens", 0))),
                # Reported per model; the primary's is the session's.
                context_window=int(
                    (d.get("modelUsage") or {}).get(primary, {}).get("contextWindow", 0)
                ),
                # Every model the turn billed, not just the primary -- the
                # background tier costs list price too.
                list_cost_usd=sum(
                    float(m.get("costUSD") or 0.0)
                    for m in (d.get("modelUsage") or {}).values()
                ),
            ),
            duration_ms=int(d.get("duration_ms", 0)),
            stop_reason=d.get("stop_reason"),
        )]
        # `is_error` rides on the same event as the turn's totals, so the
        # failure is reported without losing the usage that led to it.
        if d.get("is_error"):
            ev.append(EngineError(str(d.get("result", "engine reported an error")), fatal=True))
        return ev

    return []


def parse_stream(lines: Iterable[str]) -> Iterator[Event]:
    for line in lines:
        yield from parse_line(line)


def _flatten(content: Any) -> str:
    """Tool results arrive as a string or as a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return "" if content is None else str(content)
