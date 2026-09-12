"""Session manager — Noctis v2 Stage 2 item 1.

Owns the live sessions: how many may run, which mode each belongs to, what
happens to the rest. The spec caps concurrency at 2.

**Why a cap at all**, given the machine could run more: under a subscription
engine the constraint is the 5h rolling window, not CPU. Two orchestrated
sessions burn it noticeably faster than chatting, and hitting the ceiling
mid-task is a worse failure than waiting a minute — an exhausted window
blocks *everything*, including the session you cared about. The cap is a
budget, not a resource limit.

Queued rather than rejected: a refused launch pushes the decision onto the
person at exactly the moment they are trying to start work, which is the
friction v2 exists to remove.
"""
from __future__ import annotations

import asyncio
import itertools
import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import AsyncIterator, Callable

from .driver import SessionSpec, run_session
from .events import (EngineError, Event, Limits, SessionStart, TextDelta,
                     TurnEnd)

# How many sessions may run at once. A **budget on the 5-hour window**, not a
# resource limit -- orchestrated sessions burn quota faster than chatting, and
# nothing about the machine minds more of them.
#
# It was 2, and 2 was never asked for: it was chosen when each mode had its
# own config dir whose CLAUDE.md was rewritten per launch, so concurrent
# sessions *of the same mode* would have raced on that file. Nothing per-mode
# is written to disk any more, so same-mode concurrency is ordinary now, and
# with it the reason the number was small.
#
# Settable, because the right value depends on the plan rather than on the
# code: a heavy day measured 3% of the 5-hour window, so 2 was leaving most
# of the budget unspent.
DEFAULT_MAX_CONCURRENT = 4


def max_concurrent_setting() -> int:
    """Read at construction, not at import.

    A module-level constant would bind into `__init__`'s default the moment
    this file is imported, which is before `.env` is necessarily loaded --
    so the setting would work or not depending on import order, which is the
    worst way for a setting to behave.
    """
    try:
        value = int(os.environ.get("NOCTIS_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT))
    except ValueError:
        return DEFAULT_MAX_CONCURRENT
    return max(1, value)

_counter = itertools.count(1)


@dataclass
class SessionHandle:
    local_id: int
    mode: str
    spec: SessionSpec
    state: str = "queued"                     # queued -> running -> done | failed
    session_id: str | None = None             # engine id, once known; --resume takes it
    started_at: datetime | None = None
    ended_at: datetime | None = None
    events: list[Event] = field(default_factory=list)

    @property
    def resumable(self) -> bool:
        return self.state == "done" and self.session_id is not None


# What the automatic close asks for, drawn from system.md's Communication
# rules rather than invented here -- the interface should not hold a second,
# quietly diverging copy of a rule the vault owns.
#
# All three rules, because a turn that failed one has usually failed the
# others: it stopped without text, so it also never reported state and never
# handed anything back.
ALREADY_CLOSED = "closed"

CLOSING_PROMPT = (
    f"If that turn already ended with a handback -- what was done, what it "
    f"fixed, what is next -- reply with exactly `{ALREADY_CLOSED}` and nothing "
    f"else.\n\nOtherwise close it now, in prose, with no tool calls except a "
    f"`git status` if code was touched.\n\n"
    "Say what was done, what it fixed, and what is next -- a handback, not a "
    "restatement of the working. If the turn ended before finishing, report "
    "state rather than intent: what actually landed on disk, not what you "
    "meant to do next. If it produced nothing, say that it produced nothing "
    "and why; \"read three files, found nothing worth changing\" is a "
    "complete answer and an empty one is not."
)


class SessionManager:
    """Tracks live and finished sessions, enforcing the concurrency budget."""

    def __init__(self, max_concurrent: int | None = None, runner: Callable = run_session):
        max_concurrent = max_concurrent or max_concurrent_setting()
        self._sem = asyncio.Semaphore(max_concurrent)
        self._runner = runner
        self.max_concurrent = max_concurrent
        self.sessions: dict[int, SessionHandle] = {}
        self.limits: Limits | None = None      # most recent, for the status line

    # -- introspection the UI reads ------------------------------------
    @property
    def running(self) -> list[SessionHandle]:
        return [h for h in self.sessions.values() if h.state == "running"]

    @property
    def queued(self) -> list[SessionHandle]:
        return [h for h in self.sessions.values() if h.state == "queued"]

    def by_mode(self, mode: str) -> list[SessionHandle]:
        return [h for h in self.sessions.values() if h.mode == mode]

    def at_capacity(self) -> bool:
        return len(self.running) >= self.max_concurrent

    # -- the one thing it does -----------------------------------------
    async def start(self, spec: SessionSpec) -> AsyncIterator[tuple[SessionHandle, Event]]:
        """Run a session, yielding (handle, event) as output arrives.

        The handle is yielded alongside every event so a caller streaming to
        several tabs can route without tracking correlation itself.
        """
        handle = SessionHandle(local_id=next(_counter), mode=spec.mode, spec=spec)
        self.sessions[handle.local_id] = handle

        # Waiting here is what implements the queue: over budget, this
        # blocks until a slot frees, and the handle stays visibly "queued"
        # in the meantime rather than disappearing.
        async with self._sem:
            handle.state = "running"
            handle.started_at = datetime.now(timezone.utc)
            try:
                async for event in self._runner(spec):
                    handle.events.append(event)
                    if isinstance(event, SessionStart):
                        handle.session_id = event.session_id
                    elif isinstance(event, Limits):
                        self.limits = event          # newest wins
                    elif isinstance(event, TurnEnd) and event.session_id:
                        handle.session_id = event.session_id
                    yield handle, event
                # The turn is over. If it did not close itself, close it.
                #
                # This is the Stop hook Noctis cannot have: `Stop` fires at
                # the end of every turn and can refuse the stop, but it does
                # not fire under `--print`, and the Agent SDK that does
                # support hooks requires API-key auth -- which is the metered
                # path this whole architecture exists to avoid. So the
                # equivalent lives here, where a turn's end is already known.
                #
                # Cheap only because every turn is its own spawn already: the
                # continuation is one more `--resume`, measured at ~0.9x a
                # small work turn in notional list price and below the
                # resolution of the 5h window on a subscription.
                last = next((e for e in reversed(handle.events)
                             if isinstance(e, TurnEnd)), None)
                if last is not None and last.needs_closing and not spec.continuation:
                    async for event in self._close_turn(handle, spec):
                        handle.events.append(event)
                        yield handle, event
            finally:
                handle.ended_at = datetime.now(timezone.utc)
                # A crashed run must not look identical to a clean one --
                # dev.md's failure containment is that a dead session is
                # flagged, never silently frozen.
                fatal = any(getattr(e, "fatal", False) for e in handle.events)
                handle.state = "failed" if fatal else "done"

    async def _close_turn(
        self, handle: SessionHandle, spec: SessionSpec
    ) -> AsyncIterator[Event]:
        """Resume the session once and ask it to close the turn it left open.

        Marked `continuation=True`, which is the whole loop guard: this is
        itself a turn, and would qualify for a continuation of its own
        without something to tell the two apart.

        Failures here are swallowed deliberately. The close is a courtesy on
        top of a turn that already happened -- if the engine will not spawn
        or the resume id is stale, the right outcome is the transcript the
        user already has, not an error about the thing that was trying to
        help.
        """
        if not handle.session_id:
            return                      # nothing to resume; nothing to do
        closing = replace(
            spec,
            prompt=CLOSING_PROMPT,
            resume_id=handle.session_id,
            continuation=True,
            images=(),                  # the pictures went with the first turn
        )
        # Text is buffered rather than streamed, because most of the time
        # there is nothing to show: a turn that closed itself answers
        # `closed`, and that word must never reach the transcript. Streaming
        # it and retracting would be worse than a short wait, and what is
        # being waited on is a closing note rather than the turn's substance.
        buffered: list[Event] = []
        text: list[str] = []
        try:
            async for event in self._runner(closing):
                if isinstance(event, EngineError):
                    return              # see docstring: stay quiet, keep the turn
                if isinstance(event, TextDelta):
                    text.append(event.text)
                buffered.append(event)
        except Exception:               # noqa: BLE001 - see docstring
            return

        if "".join(text).strip().strip(".`").lower() == ALREADY_CLOSED:
            return                      # it had already handed back; say nothing
        for event in buffered:
            yield event


    def resume_spec(
        self, handle: SessionHandle, prompt: str, permission_mode: str
    ) -> SessionSpec:
        """A spec that continues an earlier session rather than starting fresh.

        `permission_mode` is required rather than inherited from the handle.
        Inheriting is what this did, and it is wrong: the chip is a live
        control, so a session that opened in `manual` would stay in `manual`
        for the rest of its life no matter what the chip was switched to
        afterwards. The router happens to dodge this by building its own spec
        from each request, which is the only reason the chip works today --
        so the bug was invisible while the wrong behaviour sat here with a
        test asserting it. Required, so the next caller has to decide.
        """
        if not handle.session_id:
            raise ValueError(f"session {handle.local_id} has no engine id to resume")
        return SessionSpec(
            mode=handle.mode,
            prompt=prompt,
            resume_id=handle.session_id,
            cwd=handle.spec.cwd,
            vault_path=handle.spec.vault_path,
            permission_mode=permission_mode,
        )
