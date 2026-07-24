import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import busy_marker  # noqa: E402
import log_action  # noqa: E402


def test_log_action_appends_line(tmp_path, monkeypatch):
    monkeypatch.setattr(log_action, "RUNTIME_DIR", tmp_path)

    log_action.log_action(
        "dev", "noctis-build", {"tool_name": "Edit", "tool_input": {"file_path": "main.py"}}
    )

    log_path = tmp_path / "dev__noctis-build.log"
    line = log_path.read_text(encoding="utf-8").strip()
    assert "Edit" in line
    assert "main.py" in line


def test_log_action_no_mode_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(log_action, "RUNTIME_DIR", tmp_path)

    log_action.log_action(None, None, {"tool_name": "Edit", "tool_input": {}})

    assert list(tmp_path.iterdir()) == []


def test_log_action_missing_job_id_falls_back_to_general(tmp_path, monkeypatch):
    monkeypatch.setattr(log_action, "RUNTIME_DIR", tmp_path)

    log_action.log_action("learn", None, {"tool_name": "Read", "tool_input": {"path": "x.md"}})

    assert (tmp_path / "learn__general.log").exists()


def test_log_action_refreshes_busy_marker(tmp_path, monkeypatch):
    """A long-running session's marker must not go stale from launch-time
    age alone -- each tool call should refresh it, so is_busy() measures
    time since last activity, not time since launch."""
    monkeypatch.setattr(log_action, "RUNTIME_DIR", tmp_path)

    log_action.log_action("dev", "noctis-build", {"tool_name": "Edit", "tool_input": {}})

    assert busy_marker.is_busy("dev") is True


def test_log_action_no_mode_does_not_touch_busy_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(log_action, "RUNTIME_DIR", tmp_path)

    log_action.log_action(None, None, {"tool_name": "Edit", "tool_input": {}})

    assert busy_marker.is_busy("dev") is False


def test_env_identity_wins_over_baked_args(tmp_path, monkeypatch):
    """Same cross-contamination fix as mark_session_end's: a session's own
    NOCTIS_MODE/NOCTIS_JOB_ID env must win over a dev project's baked
    --mode/--job-id args picked up incidentally via cwd."""
    monkeypatch.setattr(log_action, "RUNTIME_DIR", tmp_path)

    monkeypatch.setenv("NOCTIS_MODE", "settings")
    monkeypatch.setenv("NOCTIS_JOB_ID", "general")
    monkeypatch.setattr(
        sys, "argv", ["log_action.py", "--mode", "dev", "--job-id", "noctis-build"]
    )
    monkeypatch.setattr(
        sys, "stdin", type("_", (), {"read": staticmethod(lambda: '{"tool_name": "Edit"}')})()
    )

    log_action.main()

    assert (tmp_path / "settings__general.log").exists()
    assert not (tmp_path / "dev__noctis-build.log").exists()
