#!/usr/bin/env python3
"""Where a hook goes when it dies.

A hook must never break the session it observes, so both hooks end in a bare
`except Exception: pass`. That policy is right and the silence is not: a hook
that stops firing reports nothing, so a broken interpreter path or an import
error looks exactly like a session that happened not to use any tools. The
action feed simply goes quiet, and `driver.py` names this as the reason the
telemetry settings had to move into the argv in the first place.

So the swallow stays and gains a receipt. One line per failure in a
gitignored runtime file, which `make doctor` reads -- the failure becomes
findable without ever reaching the session.

Writing the receipt is itself wrapped, because a hook that crashes while
recording that it crashed is strictly worse than one that crashes quietly.
"""
from __future__ import annotations

import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

RUNTIME_DIR = Path(__file__).parent.parent / "runtime"
FAILURE_LOG = RUNTIME_DIR / "hook-failures.log"

# Enough to see a pattern, not enough to grow without bound. A hook that
# fails does so on every tool call of every session, so this fills fast and
# the newest lines are the ones worth keeping.
MAX_LINES = 200


def record(hook: str, exc: BaseException) -> None:
    """Append one line naming the hook, the fault, and where it came from."""
    try:
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        where = traceback.extract_tb(exc.__traceback__)
        frame = f"{Path(where[-1].filename).name}:{where[-1].lineno}" if where else "?"
        mode = os.environ.get("NOCTIS_MODE") or "?"
        line = (f"{datetime.now(timezone.utc).isoformat()} {hook} mode={mode} "
                f"{frame} {type(exc).__name__}: {exc}\n")

        existing = []
        if FAILURE_LOG.exists():
            existing = FAILURE_LOG.read_text("utf-8").splitlines(keepends=True)
        FAILURE_LOG.write_text("".join(existing[-(MAX_LINES - 1):]) + line, "utf-8")
    except Exception:                       # noqa: BLE001
        pass    # see the module docstring: never break the session


def recent(limit: int = 5) -> list[str]:
    """The newest failures, for `make doctor`. Empty when all is well."""
    try:
        return [l.rstrip() for l in
                FAILURE_LOG.read_text("utf-8").splitlines()][-limit:]
    except Exception:                       # noqa: BLE001
        return []
