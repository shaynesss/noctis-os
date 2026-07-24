import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import busy_marker  # noqa: E402
import mark_session_end  # noqa: E402


def test_appends_session_end_sentinel(vault, tmp_path, monkeypatch):
    monkeypatch.setattr(mark_session_end, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(busy_marker, "RUNTIME_DIR", tmp_path)

    mark_session_end.mark_session_end("dev", "noctis-build", "other")

    log_path = tmp_path / "dev__noctis-build.log"
    assert "SESSION_END" in log_path.read_text(encoding="utf-8")


def test_clears_busy_flag(vault, tmp_path, monkeypatch):
    monkeypatch.setattr(mark_session_end, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(busy_marker, "RUNTIME_DIR", tmp_path)
    busy_marker.set_busy("dev")

    mark_session_end.mark_session_end("dev", "noctis-build", "other")

    assert busy_marker.is_busy("dev") is False


def test_non_terminal_reason_does_not_clear_busy(vault, tmp_path, monkeypatch):
    """SessionEnd fires with reason 'clear'/'resume' when a running CLI
    process recycles its logical session in place (a plain /clear, or the
    auto-compact-driven internal resume) -- the terminal is still open and
    in active use, so busy must stay set."""
    monkeypatch.setattr(mark_session_end, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(busy_marker, "RUNTIME_DIR", tmp_path)
    busy_marker.set_busy("dev")

    mark_session_end.mark_session_end("dev", "noctis-build", "clear")

    assert busy_marker.is_busy("dev") is True


def test_no_mode_is_noop(tmp_path, monkeypatch):
    """A mode=None call (not a Noctis-launched session) writes no
    SESSION_END sentinel and touches no busy marker -- the debug
    instrumentation log is the one exception, by design (its own docstring:
    "logs every invocation, gated or not"), so it's excluded from the
    emptiness check rather than asserting the directory is fully bare."""
    monkeypatch.setattr(mark_session_end, "RUNTIME_DIR", tmp_path)

    mark_session_end.mark_session_end(None, "x", "other")

    remaining = [p for p in tmp_path.iterdir() if p.name != "session_end_debug.log"]
    assert remaining == []


def test_env_identity_wins_over_baked_args(vault, tmp_path, monkeypatch, capsys):
    """A non-dev session cwd'd into a dev project still gets the dev
    project's --mode/--job-id-baked SessionEnd hook invoked (Claude Code
    applies project-local settings.local.json by cwd, not by which mode
    actually launched the session). Its own real NOCTIS_MODE/NOCTIS_JOB_ID
    env -- set by its own launch -- must win, or its exit misattributes as
    dev's SessionEnd and wrongly clears dev's busy marker. Found live
    2026-07-23: a settings session's exit fired mode=dev's SessionEnd at
    the identical microsecond as mode=settings' own."""
    monkeypatch.setattr(mark_session_end, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(busy_marker, "RUNTIME_DIR", tmp_path)
    busy_marker.set_busy("dev")
    busy_marker.set_busy("settings")

    monkeypatch.setenv("NOCTIS_MODE", "settings")
    monkeypatch.setenv("NOCTIS_JOB_ID", "general")
    monkeypatch.setattr(
        sys, "argv", ["mark_session_end.py", "--mode", "dev", "--job-id", "noctis-build"]
    )
    monkeypatch.setattr(sys, "stdin", type("_", (), {"read": staticmethod(lambda: '{"reason": "other"}')})())

    mark_session_end.main()

    assert busy_marker.is_busy("settings") is False
    assert busy_marker.is_busy("dev") is True
    assert (tmp_path / "settings__general.log").exists()
    assert not (tmp_path / "dev__noctis-build.log").exists()
