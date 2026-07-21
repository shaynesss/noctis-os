import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

import mark_session_end  # noqa: E402
import vault_io  # noqa: E402


def test_appends_session_end_sentinel(vault, tmp_path, monkeypatch):
    monkeypatch.setattr(mark_session_end, "RUNTIME_DIR", tmp_path)

    mark_session_end.mark_session_end("dev", "noctis-build")

    log_path = tmp_path / "dev__noctis-build.log"
    assert "SESSION_END" in log_path.read_text(encoding="utf-8")


def test_clears_busy_flag(vault, tmp_path, monkeypatch):
    monkeypatch.setattr(mark_session_end, "RUNTIME_DIR", tmp_path)
    vault_io.write_frontmatter("modes/dev/state.md", {"mode": "dev", "busy": True}, "")

    mark_session_end.mark_session_end("dev", "noctis-build")

    state, _ = vault_io.read_frontmatter("modes/dev/state.md")
    assert state["busy"] is False


def test_no_mode_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(mark_session_end, "RUNTIME_DIR", tmp_path)

    mark_session_end.mark_session_end(None, "x")

    assert list(tmp_path.iterdir()) == []
