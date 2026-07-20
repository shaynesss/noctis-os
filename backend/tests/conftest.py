import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_TOKEN = "test-token-123"


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """A throwaway vault with just enough structure for the routers under
    test: modes/<name>/{<name>.md, lessons.md, state.md, jobs/}."""
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("NOCTIS_API_TOKEN", TEST_TOKEN)

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
