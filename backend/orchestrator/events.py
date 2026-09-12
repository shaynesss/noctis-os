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
    cached_tokens: int          # read back from the cache
    model: str
    # Written *into* the cache. Routinely the largest of the four counts and
    # the dominant cost driver, and it was reported nowhere -- so the token
    # totals could not be reconciled against the list-price figure beside
    # them, which is exactly how the two came to look unrelated.
    cache_write_tokens: int = 0
    aux_input_tokens: int = 0
    aux_output_tokens: int = 0
    # The model's window size, reported per model on the result event. Zero
    # when the engine did not report one, which the UI must show as unknown
    # rather than as 0%.
    #
    # There is deliberately no `context_tokens` beside it. There was, summing
    # this turn's input + cache reads + cache writes, and dividing the two
    # gave 470% -- because those counts are cumulative across every API call
    # the turn made, while the window is the size of one. Occupancy is a
    # moment, not a total, so it comes from ContextSnapshot instead.
    context_window: int = 0
    # What this turn would have cost at API list price, summed across every
    # model it billed. Explicitly NOT what you were charged: the engine
    # reports costBasis "list", and under a subscription the marginal cost of
    # a turn is zero. Kept because "what would this have cost me on the API"
    # is a real question with a real answer — it is what the subscription is
    # worth — and refused as a spend figure, which it is not.
    list_cost_usd: float = 0.0

    @property
    def total_input(self) -> int:
        return self.input_tokens + self.aux_input_tokens

    @property
    def total_output(self) -> int:
        return self.output_tokens + self.aux_output_tokens


@dataclass(frozen=True)
class ContextSnapshot:
    """How full the window is *at one moment*, from one assistant message.

    Occupancy cannot be read off the `result` event. That event's usage is
    cumulative across every API call the turn made, and a turn that runs
    fifteen tools makes fifteen calls, each re-sending the whole conversation.
    Summing them measures traffic, not occupancy: one real turn recorded
    2,599,073 cache-read tokens against a 1M window, and the status bar
    faithfully reported 470% full.

    An assistant message carries the usage of the single call that produced
    it, so its prompt size *is* the window's occupancy at that instant. The
    last one to arrive is the current answer.
    """
    tokens: int


@dataclass(frozen=True)
class TurnEnd:
    """The end of one turn, and what the turn actually produced.

    `text_chars` and `tool_calls` exist because a turn is allowed to end with
    tool calls and no assistant text at all -- the model treats a tool result
    as "still working" and the turn simply stops there. That is a legal shape,
    not a crash, but the shell renders the transcript, so an empty turn draws
    a blank screen identical to a dead backend, a session still thinking, and
    a finished job. Four states, one rendering, and the only way to tell them
    apart was to ask.

    Counting them here makes silence a fact on the event rather than an
    absence to be inferred. A rule asking the model to always write something
    cannot fix this -- it needs a reply to attach to, and on these turns there
    is none; it was tried three times and failed three times. This is a health
    check, and CLAUDE.md says health checks are backend code.
    """
    session_id: str
    usage: Usage
    duration_ms: int
    stop_reason: str | None = None
    text_chars: int = 0
    tool_calls: int = 0
    # Text emitted *after the last tool call*, which is a different question
    # from `text_chars` and the one that actually matters. A turn can narrate
    # its way through six tools, run a seventh, and stop -- text_chars is
    # large, the turn read as fine, and what you are left looking at is
    # "Ran 1 shell command" with no word about what it found.
    text_after_last_tool: int = 0
    # Why the engine stopped, in its own words -- "completed" on a normal
    # turn, something else when it did not get there.
    terminal_reason: str = ""
    # Tools the turn asked for and was refused. A non-empty list is the
    # difference between "said nothing" and "was not allowed to do anything".
    denials: tuple[Denial, ...] = ()

    @property
    def silent(self) -> bool:
        """Ended without saying anything at all."""
        return self.text_chars == 0

    @property
    def needs_closing(self) -> bool:
        """The turn ended without doing what system.md requires of it.

        Three mechanically-checkable failures, and deliberately only three:
        it said nothing at all, it ended on a tool call without saying what
        came of it, or it was cut off at the output ceiling mid-sentence.

        Not checked, because it cannot be without guessing: whether prose
        that *is* present amounts to the handback the rule asks for. A
        keyword search for "Summary" would be the same fragile inference
        this module replaced. The nudge sent on these three carries the full
        rule, so when it does fire it asks for the whole thing.
        """
        return self.silent or self.unclosed or self.truncated

    @property
    def truncated(self) -> bool:
        """The engine stopped because it ran out of room, not because it was
        done. `end_turn` is a finished thought; `max_tokens` is a sentence cut
        in half, and the two are indistinguishable in a transcript unless one
        of them says so."""
        return self.stop_reason == "max_tokens"

    @property
    def unclosed(self) -> bool:
        """Ended on a tool call, with nothing said about it.

        The common shape, and the one the first version of this missed by
        counting text across the whole turn: narration mid-turn made
        `silent` false while the reader was still left with an unexplained
        tool call as the last thing on screen. Whether the turn spoke
        earlier is irrelevant to whether it finished.
        """
        return self.tool_calls > 0 and self.text_after_last_tool == 0

    @property
    def blocked(self) -> bool:
        """Ended without speaking *because* it was refused the tools it
        needed. The honest reading of a silent turn with denials on it, and
        the one that names something fixable rather than blaming the model."""
        return self.silent and bool(self.denials)


@dataclass(frozen=True)
class Denial:
    """A tool the engine refused, reported on the turn that wanted it.

    The engine has always sent these, on the `result` event's
    `permission_denials`, and nothing read them. That is the whole reason a
    caged session looked like a broken one: Faber's mutating tools sit behind
    a permission prompt, every prompt went unanswered, and the turn ended
    with nothing done and nothing to say. The refusals were in the stream the
    entire time.

    A session that cannot act is a different thing from a session that chose
    not to speak, and until this was read there was no way to tell them apart.
    """
    tool: str
    target: str = ""


@dataclass(frozen=True)
class EngineError:
    """A failure the orchestrator should surface rather than swallow —
    a non-zero exit, an unparseable line, a refusal."""
    message: str
    fatal: bool = False


Event = Union[
    SessionStart, TextDelta, ThinkingDelta, ThinkingProgress, ToolCall,
    ToolResult, Limits, ContextSnapshot, TurnEnd, Denial, EngineError,
]

__all__ = [
    "SessionStart", "TextDelta", "ThinkingDelta", "ThinkingProgress", "ToolCall", "ToolResult",
    "Limits", "Usage", "ContextSnapshot", "TurnEnd", "Denial", "EngineError",
    "Event",
]
