"""Marker-file based `busy` tracking -- deliberately NOT a field a session
ever writes directly, unlike the rest of state.md.

`busy` used to be a plain state.md field, read-modify-written by
POST /session/launch (set True) and the SessionEnd hook (set False). But a
running session also legitimately rewrites its own state.md directly via
its own Edit/Write tool calls (updating adopt_counts/last_touched/jobs, per
each mode's "Verdict + file" close discipline) -- and since those edits
don't go through this backend at all, the session has no way to know
`busy` exists or must be preserved. A session's own frontmatter rewrite
silently dropped it at least once in practice (found 2026-07-22, Vesper's
card going idle mid-session while the terminal was still open).

Moving `busy` to a runtime marker file makes it structurally immune to
this: sessions never touch backend/runtime/, only backend code does. Same
pattern already used for staleness/flagged (staleness.py) and the
action-feed log (log_action.py) -- runtime state that must survive a
session's own vault edits lives in runtime/, not in vault-editable
frontmatter. v1's GET /mode/<name> read this marker over state.md's own
`busy`; that route went at the 2026-09-12 cutover and **nothing reads the
marker now** (2026-09-29 audit: `is_busy` has no caller outside its tests).
The SessionEnd hook still writes and clears it. Either a reader comes back
or this module goes; until then it is state nobody looks at.

Clearing the marker still depends entirely on the SessionEnd hook firing --
and that hook only runs on a clean CLI exit. A session killed some other
way (terminal window closed, machine slept mid-session, process crashed)
never fires SessionEnd, so the marker is orphaned and the mode reads
"busy" forever with nothing actually running (found live 2026-07-23:
dev.busy was touched by a launch at 23:37 UTC on 2026-07-22 with no
process left running and no matching SESSION_END ever logged after it --
the prior launch's SessionEnd at 23:26:55 had fired correctly, so this was
a genuine non-graceful exit, not a hook regression). There's no reliable
way to confirm a Terminal.app/VS Code-launched `claude` process is still
alive from here (no PID is captured at launch), so this applies the same
self-healing TTL staleness.py already uses for the analogous "did a
session ever cleanly close" problem on job contexts: a marker older than
STALE_THRESHOLD is treated as abandoned and cleared on the next check,
rather than trusting a single missed hook to hold forever.
"""

from datetime import datetime, timezone
from pathlib import Path

from staleness import STALE_THRESHOLD

RUNTIME_DIR = Path(__file__).parent / "runtime"


def _marker_path(mode: str) -> Path:
    return RUNTIME_DIR / f"{mode}.busy"


def set_busy(mode: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _marker_path(mode).touch()


def clear_busy(mode: str) -> None:
    _marker_path(mode).unlink(missing_ok=True)


def is_busy(mode: str) -> bool:
    marker = _marker_path(mode)
    if not marker.exists():
        return False
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(
        marker.stat().st_mtime, tz=timezone.utc
    )
    if age > STALE_THRESHOLD:
        marker.unlink(missing_ok=True)
        return False
    return True
