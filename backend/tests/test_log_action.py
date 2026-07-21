import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

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
