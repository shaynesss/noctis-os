import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import busy_marker  # noqa: E402 -- needs sys.path insert above first

TEST_TOKEN = "test-token-123"


@pytest.fixture(autouse=True)
def _isolated_busy_marker(tmp_path, monkeypatch):
    """busy_marker.RUNTIME_DIR is a hardcoded path to the real
    backend/runtime/ dir, not env-var-overridable like VAULT_PATH -- any
    test that exercises POST /session/launch for mode=dev without its own
    explicit monkeypatch (test_dev_launch_opens_vscode and two others in
    test_session_router.py did exactly this) sets the REAL dev.busy marker
    file on the live running app. Found 2026-07-23: running this suite
    while working a settings/Custos session on Faber-related code flipped
    Faber's world-screen icon to busy for real, with nothing to ever clear
    it since no real session launched. autouse so every test is isolated by
    default rather than relying on each test author remembering to patch
    this individually, the way only test_nondev_launch_opens_terminal did.
    """
    monkeypatch.setattr(busy_marker, "RUNTIME_DIR", tmp_path / "runtime")


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """A throwaway vault with just enough structure for the routers under
    test: modes/<name>/{<name>.md, lessons.md, state.md, jobs/}."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("NOCTIS_API_TOKEN", TEST_TOKEN)
    # Keeps new-build scratch directories (routers/mode.py's create_job) out
    # of the real home directory during tests.
    monkeypatch.setenv("NOCTIS_SCRATCH_ROOT", str(tmp_path / "scratch"))

    (tmp_path / "log.md").write_text("# Log\n\n", encoding="utf-8")

    for name in ("dev", "learn", "research", "settings", "nightshift"):
        mode_dir = tmp_path / "modes" / name
        (mode_dir / "jobs").mkdir(parents=True)
        (mode_dir / f"{name}.md").write_text(f"# {name} methodology\n", encoding="utf-8")
        (mode_dir / "lessons.md").write_text(f"# {name} lessons\n", encoding="utf-8")
        (mode_dir / "state.md").write_text(
            "---\nmode: " + name + "\nbusy: false\n---\n\nnotes\n", encoding="utf-8"
        )

    return tmp_path


@pytest.fixture
def client(vault):
    from fastapi.testclient import TestClient

    import main

    return TestClient(main.app)


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}
