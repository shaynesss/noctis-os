import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import mark_session_end  # noqa: E402


def test_appends_session_end_sentinel(tmp_path, monkeypatch):
    monkeypatch.setattr(mark_session_end, "RUNTIME_DIR", tmp_path)

    mark_session_end.mark_session_end("dev", "noctis-build")

    log_path = tmp_path / "dev__noctis-build.log"
    assert "SESSION_END" in log_path.read_text(encoding="utf-8")


def test_no_mode_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(mark_session_end, "RUNTIME_DIR", tmp_path)

    mark_session_end.mark_session_end(None, "x")

    assert list(tmp_path.iterdir()) == []
