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
