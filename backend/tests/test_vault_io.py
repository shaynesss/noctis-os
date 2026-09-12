import re
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

    # Every *invocation*, not "somewhere in the file". The substring version
    # of this passed while `make backend` -- a second target with its own copy
    # of the flags -- was missing an exclude entirely, and that target is the
    # one the app actually runs. A file-wide `in` check cannot tell two
    # invocations apart, which is the same shape of mistake this test was
    # rewritten once already to avoid.
    for command in _uvicorn_commands(makefile):
        if "--reload" not in command:
            continue                      # nothing to exclude from
        for pattern in RELOAD_EXCLUDES:
            assert pattern in command, (
                f"a Makefile uvicorn invocation does not exclude {pattern}: {command}"
            )
        # Both directions. A pattern left behind after its directory was
        # deleted is dead config that reads as protection -- `launch_config/*`
        # survived the 2026-09-12 cutover in two invocations and one comment.
        for flag in re.findall(r"--reload-exclude '([^']+)'", command):
            assert flag in RELOAD_EXCLUDES, (
                f"the Makefile excludes {flag}, which is not a runtime-written "
                f"directory any more -- remove it or add it to RUNTIME_WRITE_DIRS"
            )


def test_the_desktop_app_does_not_reload():
    """It is the daily driver, and Noctis's own primary job is editing this
    repository. With --reload on, a Faber session touching any backend/*.py
    restarts the backend hosting it -- killing its own in-flight stream and
    every other live session's, which presents as the model going silent
    mid-turn.

    `make dev` keeps --reload: that is the loop where a backend edit should
    take effect at once and no session is being hosted.
    """
    repo = Path(__file__).resolve().parents[2]
    app_py = (repo / "desktop" / "app.py").read_text()
    invocation = app_py[app_py.index('"main:app"'):app_py.index('"8000"')]
    assert "--reload" not in invocation, (
        "desktop/app.py runs uvicorn with --reload; a session editing the "
        "backend would restart its own host mid-turn"
    )


def _uvicorn_commands(makefile: str) -> list[str]:
    """Each uvicorn invocation in the Makefile, with continuations folded in.

    A recipe line ending in a backslash continues, so the flags for one
    invocation are spread over several lines and cannot be matched one at a
    time.
    """
    folded = makefile.replace("\\\n", " ")
    found = [line for line in folded.splitlines() if "uvicorn main:app" in line]
    assert found, "no uvicorn invocation found in the Makefile"
    return found


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
