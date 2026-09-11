"""Pending permission requests — the thing that makes the chip a control.

The chip sets `--permission-mode`, and for `manual` to mean "ask me" rather
than "refuse", something has to be asked. Under `--print` that something is
whatever `--permission-prompt-tool` names; here it is an MCP tool, which
calls into this module and blocks until a person clicks.

**Why a registry rather than a callback.** The asking party is a separate
process (the MCP server, spawned by the CLI, which was spawned by us) and the
answering party is a web view. Neither can call the other. A small table in
the middle that one writes to and the other reads is the only shape that
works, and it is the same shape as the existing inbox.

Requests expire. A prompt nobody answers must not hold a session open
forever, and a session waiting on a dialog that was never rendered is a hang
with no visible cause — the worst failure this file could have. On timeout
the answer is *deny*, because the safe default is the one you did not have to
be present for.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

Decision = Literal["allow", "deny"]

# Long enough to notice a prompt and decide, short enough that a forgotten one
# does not pin a process for the afternoon.
TIMEOUT_SECONDS = 180.0


@dataclass
class Request:
    id: str
    mode: str
    tool: str
    # The tool's own arguments, shown so a decision can be made on what the
    # session actually wants to do rather than on the tool's name. "Write" is
    # not a question anyone can answer; "Write to bootstrap.sh" is.
    args: dict[str, Any]
    created_at: float
    decided: threading.Event = field(default_factory=threading.Event)
    decision: Decision | None = None
    # Set when the answer came from a timeout rather than a person, so the UI
    # can say so instead of implying you denied something you never saw.
    expired: bool = False
    # What the person chose, for a tool whose whole purpose is to ask -- the
    # answer is the point of the call, not a modifier on it. Question text ->
    # the label picked for it. None for every ordinary permission request,
    # where "allow" carries all the meaning there is.
    answers: dict[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "mode": self.mode, "tool": self.tool,
                "args": self.args, "age": round(time.time() - self.created_at, 1)}


class PermissionRegistry:
    """Thread-safe, in-memory, deliberately not persisted.

    A pending request belongs to a live process. If the backend restarts, the
    session that was waiting is gone too, and restoring its question would
    surface a dialog for a decision nobody can act on any more.
    """

    def __init__(self, timeout: float = TIMEOUT_SECONDS) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, Request] = {}
        self._timeout = timeout

    def ask(self, mode: str, tool: str, args: dict[str, Any]) -> Request:
        """Register a question and block until it is answered or expires."""
        req = Request(id=uuid.uuid4().hex[:12], mode=mode, tool=tool,
                      args=args, created_at=time.time())
        with self._lock:
            self._pending[req.id] = req

        if not req.decided.wait(timeout=self._timeout):
            req.decision, req.expired = "deny", True

        with self._lock:
            self._pending.pop(req.id, None)
        return req

    def decide(
        self, request_id: str, decision: Decision,
        answers: dict[str, str] | None = None,
    ) -> bool:
        """Answer a question. False when there is nothing by that id, which
        happens when it expired while the dialog was still on screen.

        `answers` carries a choice back for AskUserQuestion, where allowing
        the call is not the answer -- the selection is. Ignored, and normally
        absent, for every other tool.
        """
        with self._lock:
            req = self._pending.get(request_id)
        if req is None:
            return False
        req.decision = decision
        req.answers = answers
        req.decided.set()
        return True

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return [r.as_dict() for r in self._pending.values()]


registry = PermissionRegistry()
