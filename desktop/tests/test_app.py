import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import app  # noqa: E402


def test_resolve_npm_prefers_shutil_which(monkeypatch):
    monkeypatch.setattr(app.shutil, "which", lambda name: "/some/path/npm")
    assert app._resolve_npm() == "/some/path/npm"


def test_resolve_npm_falls_back_to_homebrew_when_path_lookup_fails(monkeypatch):
    """The actual bug: launched via LaunchServices (Spotlight/double-click),
    the process gets launchd's minimal PATH, which doesn't include
    Homebrew's bin dir -- shutil.which("npm") fails there exactly like the
    bare "npm" in subprocess.Popen used to. Found live via two failed
    Spotlight launches, both logging FileNotFoundError: 'npm'."""
    monkeypatch.setattr(app.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        "app.Path", lambda p: type("FakePath", (), {"exists": lambda self: p == "/opt/homebrew/bin/npm"})()
    )
    assert app._resolve_npm() == "/opt/homebrew/bin/npm"


def test_resolve_npm_last_resort_returns_bare_name(monkeypatch):
    monkeypatch.setattr(app.shutil, "which", lambda name: None)
    monkeypatch.setattr("app.Path", lambda p: type("FakePath", (), {"exists": lambda self: False})())
    assert app._resolve_npm() == "npm"


def test_npm_env_prepends_npm_bin_directory(monkeypatch):
    monkeypatch.setattr(app, "NPM_BIN", "/opt/homebrew/bin/npm")
    monkeypatch.setattr(app.os, "environ", {"PATH": "/usr/bin:/bin"})
    env = app._npm_env()
    assert env["PATH"] == "/opt/homebrew/bin:/usr/bin:/bin"
