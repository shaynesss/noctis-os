from pathlib import Path

import vault_io


def test_read_write_file_roundtrip(vault):
    vault_io.write_file("modes/dev/state.md", "hello")
    assert vault_io.read_file("modes/dev/state.md") == "hello"


def test_frontmatter_roundtrip(vault):
    metadata = {"mode": "dev", "busy": True, "jobs": [{"slug": "a", "stage": "Build"}]}
    vault_io.write_frontmatter("modes/dev/state.md", metadata, "some notes")

    read_metadata, read_content = vault_io.read_frontmatter("modes/dev/state.md")
    assert read_metadata == metadata
    assert read_content.strip() == "some notes"


def test_serialized_files_still_readable_after_write(vault):
    vault_io.write_file("log.md", "# Log\n\n- entry one\n")
    assert "entry one" in vault_io.read_file("log.md")


def test_missing_vault_path_raises(monkeypatch):
    monkeypatch.delenv("VAULT_PATH", raising=False)
    try:
        vault_io.get_vault_path()
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_write_frontmatter_rejects_path_escaping_the_vault(vault):
    try:
        vault_io.write_frontmatter("../../../../tmp/pwned/context.md", {"a": 1}, "")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_read_file_rejects_path_escaping_the_vault(vault):
    try:
        vault_io.read_file("../outside.md")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_file_exists_rejects_path_escaping_the_vault(vault):
    try:
        vault_io.file_exists("../../etc/passwd")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_project_root_path_resolves_outside_the_vault(tmp_path, monkeypatch, vault):
    """Custos's spec-completeness audit can propose a diff against a
    project's own SPEC.md (noctis-os/SPEC.md), which lives in a sibling
    repo, not inside second-brain/ -- found 2026-07-27 when the first-ever
    proposal targeting it raised a bare FileNotFoundError, since
    _resolve_within_vault only ever knew about VAULT_PATH. Patches
    _PROJECT_ROOTS to a throwaway directory rather than the real noctis-os
    checkout, so this test can never touch real repo files.
    """
    fake_project = tmp_path / "fake-project"
    fake_project.mkdir()
    monkeypatch.setattr(vault_io, "_PROJECT_ROOTS", {"noctis-os": fake_project})

    vault_io.write_file("noctis-os/SPEC.md", "hello from the project repo")

    assert (fake_project / "SPEC.md").read_text(encoding="utf-8") == "hello from the project repo"
    assert vault_io.read_file("noctis-os/SPEC.md") == "hello from the project repo"


def test_project_root_path_rejects_traversal(tmp_path, monkeypatch, vault):
    fake_project = tmp_path / "fake-project"
    fake_project.mkdir()
    monkeypatch.setattr(vault_io, "_PROJECT_ROOTS", {"noctis-os": fake_project})

    try:
        vault_io.read_file("noctis-os/../../etc/passwd")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_every_runtime_written_dir_is_excluded_from_reload():
    """uvicorn --reload watches the cwd, so anything the backend writes while
    running restarts it and drops the in-flight request. In WKWebView that
    surfaces as "Load failed", which looks like a network fault and is not.

    Driven by paths.RUNTIME_WRITE_DIRS rather than a hardcoded string. The
    previous version of this test asserted "runtime/*" literally, so when the
    conversation store started writing data/ on every message it caught
    nothing -- the same bug, a second time, past a test written for it.
    """
    from paths import RELOAD_EXCLUDES

    repo = Path(__file__).resolve().parents[2]
    makefile = (repo / "Makefile").read_text()
    app_py = (repo / "desktop" / "app.py").read_text()

    for pattern in RELOAD_EXCLUDES:
        assert pattern in makefile, f"Makefile does not exclude {pattern} from --reload"
        assert pattern in app_py, f"desktop/app.py does not exclude {pattern} from --reload"


def test_the_store_writes_inside_a_declared_runtime_dir():
    """The list only protects what it knows about, so the store's own data
    directory has to be one of the names on it."""
    from orchestrator.store import DATA_DIR
    from paths import RUNTIME_WRITE_DIRS

    assert DATA_DIR.name in RUNTIME_WRITE_DIRS


def test_is_safe_slug():
    assert vault_io.is_safe_slug("noctis-build")
    assert vault_io.is_safe_slug("a")
    assert vault_io.is_safe_slug("a1-b2")
    assert not vault_io.is_safe_slug("../../etc/passwd")
    assert not vault_io.is_safe_slug("..")
    assert not vault_io.is_safe_slug("has/slash")
    assert not vault_io.is_safe_slug("")
    assert not vault_io.is_safe_slug("Has-Upper")
    assert not vault_io.is_safe_slug("-leading-hyphen")
    assert not vault_io.is_safe_slug("trailing-hyphen-")
