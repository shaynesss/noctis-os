"""A hook that dies has to leave a receipt.

Both hooks end in a bare `except Exception` because a hook must never break
the session it observes. That policy is right; the silence around it was not.
A broken interpreter path or a bad import made the action feed go quiet, and
a quiet feed is indistinguishable from a session that used no tools -- the
exact failure `driver.py` cites for moving the telemetry settings into argv.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from hooks import failure_log

BACKEND = Path(__file__).resolve().parents[1]
HOOKS = BACKEND / "hooks"


@pytest.fixture(autouse=True)
def _isolated_log(tmp_path, monkeypatch):
    """Never write the developer's real runtime log from a test."""
    monkeypatch.setattr(failure_log, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(failure_log, "FAILURE_LOG", tmp_path / "hook-failures.log")


def test_a_swallowed_failure_is_written_down():
    try:
        raise RuntimeError("engine on fire")
    except RuntimeError as exc:
        failure_log.record("PostToolUse", exc)

    line = failure_log.recent()[-1]
    assert "PostToolUse" in line
    assert "RuntimeError: engine on fire" in line
    # The frame, so a broken hook can be found without reproducing it.
    assert "test_hook_failure_log.py:" in line


def test_nothing_recorded_reads_as_healthy():
    """`recent` returning empty is what `make doctor` prints "ok" on, so an
    unreadable or absent log must not look like a failure."""
    assert failure_log.recent() == []


def test_the_log_does_not_grow_without_bound():
    """A broken hook fails on every tool call of every session, so this fills
    fast; the newest lines are the ones worth keeping."""
    for i in range(failure_log.MAX_LINES + 40):
        try:
            raise ValueError(f"fault {i}")
        except ValueError as exc:
            failure_log.record("PostToolUse", exc)

    lines = failure_log.FAILURE_LOG.read_text().splitlines()
    assert len(lines) <= failure_log.MAX_LINES
    assert f"fault {failure_log.MAX_LINES + 39}" in lines[-1], "newest must survive"


def test_recording_a_failure_cannot_itself_raise(monkeypatch):
    """The one thing this module may never do. A hook that crashes while
    recording that it crashed is strictly worse than one that crashes
    quietly, because it takes the session with it."""
    monkeypatch.setattr(failure_log, "RUNTIME_DIR", Path("/proc/nonexistent/nope"))
    monkeypatch.setattr(failure_log, "FAILURE_LOG", Path("/proc/nonexistent/nope/x.log"))
    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        failure_log.record("SessionEnd", exc)      # must not raise


@pytest.mark.parametrize("hook,payload", [
    ("log_action.py", b"{}"),
    ("mark_session_end.py", b'{"reason":"other"}'),
])
def test_both_hooks_still_run_standalone(hook, payload):
    """They are spawned as scripts by the engine, not imported. An import
    added for the failure path has to resolve in that context too -- and
    `mark_session_end` imports busy_marker inside a function, so the obvious
    placement would have raised NameError inside the handler itself.
    """
    proc = subprocess.run(
        [sys.executable, str(HOOKS / hook), "--mode", "faber"],
        input=payload, capture_output=True, cwd=BACKEND, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr.decode()[:400]
