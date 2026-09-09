"""The normalized event union — Noctis v2 Stage 2 item 1.

Everything the frontend renders comes through here. The orchestrator parses
Claude Code's `stream-json` into these; nothing above this layer sees the
CLI's own event shapes.

Why normalize at all, given v2 ships exactly one engine: the frontend needs
*some* stable shape, and `stream-json` is a supported flag rather than a
versioned public API (risk 10). Keeping the translation in one file means a
schema change upstream is a patch to `parser.py` and nothing else. This is
the surviving half of the Engine seam the spec demoted — the normalization
was always worth its keep; the multi-adapter abstraction around it was not.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Union


@dataclass(frozen=True)
class SessionStart:
    """First event of a run. `session_id` is what `--resume` takes."""
    session_id: str
    model: str
    cwd: str
    tools: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TextDelta:
    """Assistant prose destined for the transcript."""
    text: str


@dataclass(frozen=True)
class ThinkingDelta:
    """A thinking block. `text` is **usually empty** and that is not a bug.

    Current models default to `display: "omitted"` — reasoning happens and
    is billed, but the raw chain of thought is never returned, and the CLI
    exposes no flag to change it (verified 2026-09-07: `thinking` came back
    as "" with a 976-char signature, and `--include-partial-messages`
    recovered zero characters). The block's *presence* is still meaningful:
    it says the model reasoned before this step.

    The spec's "visible thinking" therefore means visible *activity*, not
    visible text. Pair with ThinkingProgress for a live token counter.
    """
    text: str = ""
    tokens: int = 0


@dataclass(frozen=True)
class ThinkingProgress:
    """Live estimate of thinking tokens, streamed while the model reasons.

    The one honest signal available during a long pause: the count climbs
    (50 → 250 → …) so the UI can show work happening rather than a frozen
    transcript. Estimated, not billed — the authoritative figure arrives on
    TurnEnd's usage.
    """
    estimated_tokens: int


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]

    @property
    def summary(self) -> str:
        """One-line target for the disclosure row, e.g. the path being read.
        Mirrors the field order log_action.py already uses, so the in-app
        transcript and the hook-written runtime log describe a tool call the
        same way."""
        for key in ("file_path", "command", "path", "pattern", "query", "url"):
            if key in self.args:
                v = str(self.args[key])
                return v if len(v) <= 100 else v[:97] + "..."
        return ""


@dataclass(frozen=True)
class ToolResult:
    id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Limits:
    """Rolling subscription windows, from the CLI's `rate_limit_event`.

    Not derived from token counts: these are authoritative values the engine
    reports, and they are the only numbers in the UI that govern a real
    decision — whether there is room to start another session.
    """
    five_hour_used: float           # 0.0 - 1.0
    five_hour_resets_at: int        # unix epoch seconds
    seven_day_used: float
    seven_day_resets_at: int
    using_overage: bool = False


@dataclass(frozen=True)
class Usage:
    """Per-turn token counts. No cost field — under a subscription engine a
    dollar figure is notional and never charged, so showing it would be
    noise at best. Limits are the real currency; see `Limits`.

    A turn can bill more than one model: the CLI runs small background tasks
    on a cheaper tier alongside the model doing the work. The first three
    fields describe the model named in `model` — the one that answered — and
    `aux_*` carries everything else the turn spent.

    They are kept apart rather than summed because they answer different
    questions. "What did this reply cost" is the primary model; "what did my
    day cost" is both. Summing into one number would make the per-turn
    figure wrong, and reporting only the primary — which is what this did
    until 2026-09-08 — silently loses ~900 input tokens on every turn.
    """
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    model: str
    aux_input_tokens: int = 0
    aux_output_tokens: int = 0
    # What the turn actually sent: fresh input plus everything read from or
    # written to the cache. Against `context_window` this is how full the
    # window is -- the one number in the status bar that says whether a long
    # conversation is approaching its limit. Zero when the engine did not
    # report a window, which the UI must show as unknown rather than as 0%.
    context_tokens: int = 0
    context_window: int = 0

    @property
    def context_pct(self) -> float:
        """0.0-1.0, or 0.0 when the window is unknown."""
        return self.context_tokens / self.context_window if self.context_window else 0.0

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.aux_input_tokens

    @property
    def total_output(self) -> int:
        return self.output_tokens + self.aux_output_tokens


@dataclass(frozen=True)
class TurnEnd:
    session_id: str
    usage: Usage
    duration_ms: int
    stop_reason: str | None = None


@dataclass(frozen=True)
class EngineError:
    """A failure the orchestrator should surface rather than swallow —
    a non-zero exit, an unparseable line, a refusal."""
    message: str
    fatal: bool = False


Event = Union[
    SessionStart, TextDelta, ThinkingDelta, ThinkingProgress, ToolCall,
    ToolResult, Limits, TurnEnd, EngineError,
]

__all__ = [
    "SessionStart", "TextDelta", "ThinkingDelta", "ThinkingProgress", "ToolCall", "ToolResult",
    "Limits", "Usage", "TurnEnd", "EngineError", "Event",
]
