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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Callable

from .driver import SessionSpec, run_session
from .events import Event, Limits, SessionStart, TurnEnd

MAX_CONCURRENT = 2

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


class SessionManager:
    """Tracks live and finished sessions, enforcing the concurrency budget."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT, runner: Callable = run_session):
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
            finally:
                handle.ended_at = datetime.now(timezone.utc)
                # A crashed run must not look identical to a clean one --
                # dev.md's failure containment is that a dead session is
                # flagged, never silently frozen.
                fatal = any(getattr(e, "fatal", False) for e in handle.events)
                handle.state = "failed" if fatal else "done"

    def resume_spec(self, handle: SessionHandle, prompt: str) -> SessionSpec:
        """A spec that continues an earlier session rather than starting fresh."""
        if not handle.session_id:
            raise ValueError(f"session {handle.local_id} has no engine id to resume")
        return SessionSpec(
            mode=handle.mode,
            prompt=prompt,
            resume_id=handle.session_id,
            cwd=handle.spec.cwd,
            vault_path=handle.spec.vault_path,
            permission_mode=handle.spec.permission_mode,
        )
