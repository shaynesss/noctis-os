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
frontmatter. GET /mode/<name> overrides whatever `busy` value happens to
be sitting in state.md's frontmatter with this marker's live value, so a
stale/dropped key in the vault file can no longer matter.
"""

from pathlib import Path

RUNTIME_DIR = Path(__file__).parent / "runtime"


def _marker_path(mode: str) -> Path:
    return RUNTIME_DIR / f"{mode}.busy"


def set_busy(mode: str) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _marker_path(mode).touch()


def clear_busy(mode: str) -> None:
    _marker_path(mode).unlink(missing_ok=True)


def is_busy(mode: str) -> bool:
    return _marker_path(mode).exists()
