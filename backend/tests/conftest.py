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


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch):
    """Clear settings the suite asserts defaults for.

    `main.py` loads `.env`, so anything set there is present during a test
    run: setting NOCTIS_MAX_CONCURRENT=9 locally turned three assertions
    about the *default* red, and the suite's result started depending on a
    gitignored file on one machine. A test that reads the developer's
    environment is not testing the code.

    Tests that want a value set it themselves with monkeypatch, which still
    works -- this only removes what the ambient environment supplies.
    """
    monkeypatch.delenv("NOCTIS_MAX_CONCURRENT", raising=False)


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

    for name in ("dev", "learn", "research"):
        mode_dir = tmp_path / "modes" / name
        (mode_dir / "jobs").mkdir(parents=True)
        (mode_dir / f"{name}.md").write_text(f"# {name} methodology\n", encoding="utf-8")
        (mode_dir / "lessons.md").write_text(f"# {name} lessons\n", encoding="utf-8")
        (mode_dir / "state.md").write_text(
            "---\nmode: " + name + "\nbusy: false\n---\n\nnotes\n", encoding="utf-8"
        )

    # Maintenance is not under modes/. Settings and nightshift collapsed into
    # root-level `maintenance/` at the 2026-09-12 cutover, and it carries the
    # inbox and archive the other three have no equivalent of.
    maint = tmp_path / "maintenance"
    for sub in ("jobs", "inbox", "archive"):
        (maint / sub).mkdir(parents=True)
    (maint / "audit.md").write_text("# maintenance methodology\n", encoding="utf-8")
    (maint / "lessons.md").write_text("# maintenance lessons\n", encoding="utf-8")
    (maint / "state.md").write_text(
        "---\nmode: maintenance\nbusy: false\n---\n\nnotes\n", encoding="utf-8"
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


@pytest.fixture(autouse=True)
def _isolated_history_db(tmp_path_factory, monkeypatch):
    """Keep the suite out of the real `backend/data/history.db`.

    `routers/sessions_v2.py` builds its `ConversationStore` at import time
    against the live database, so every test that POSTs `/v2/sessions` opened
    a real conversation row in the history the app reads. Found 2026-09-12:
    134 of the 158 `general` rows on this machine were test launches --
    "what is this?", one message, no engine id -- and because they were the
    newest rows, the shell's restore looked for the most recent *resumable*
    General session, found only test debris in the window it reads, and gave
    up before restoring any tab at all. A reload brought back nothing, and
    the cause was not in the restore code.

    Same shape as the busy-marker fixture above, and for the same reason:
    autouse, so isolation is the default rather than something each test
    author has to remember. Tests that build their own store still do.

    Its own directory rather than `tmp_path`, because an autouse fixture
    shares that directory with the test using it -- and a database dropped
    there is a file the test did not put there. `test_log_action_no_mode_is_noop`
    asserts `tmp_path` is empty, and duly failed on the WAL files.
    """
    data = tmp_path_factory.mktemp("history")
    from orchestrator import store as store_mod
    from routers import search as search_mod
    from routers import sessions_v2 as sv2

    # For the routers that construct a store per call (panels, digest).
    monkeypatch.setattr(store_mod, "DATA_DIR", data / "data")
    # And for the two that built theirs at import, against the live file.
    monkeypatch.setattr(sv2, "_store", store_mod.ConversationStore(data / "history.db"))
    monkeypatch.setattr(search_mod, "_store", store_mod.ConversationStore(data / "history.db"))
