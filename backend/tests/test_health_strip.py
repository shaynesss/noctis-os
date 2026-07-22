from datetime import datetime, timedelta, timezone

import health_strip
import vault_io


def test_lint_status_unknown_when_file_missing(vault):
    result = health_strip.compute_lint_status()
    assert result == {"status": "unknown", "last_run": None, "label": None}


def test_lint_status_ok_for_recent_run(vault):
    today = datetime.now(timezone.utc).date().isoformat()
    vault_io.write_file(
        "wiki/Lint History.md",
        f"# Lint History\n\n## {today} — run 5\n\nNo findings.\n",
    )

    result = health_strip.compute_lint_status()

    assert result["status"] == "ok"
    assert result["last_run"] == today
    assert "run 5" in result["label"]


def test_lint_status_stale_after_seven_days(vault):
    old = (datetime.now(timezone.utc).date() - timedelta(days=10)).isoformat()
    vault_io.write_file(
        "wiki/Lint History.md",
        f"# Lint History\n\n## {old} — run 1\n\nBaseline.\n",
    )

    result = health_strip.compute_lint_status()

    assert result["status"] == "stale"
    assert result["last_run"] == old


def test_lint_status_uses_last_of_multiple_headings(vault):
    older = (datetime.now(timezone.utc).date() - timedelta(days=20)).isoformat()
    newer = datetime.now(timezone.utc).date().isoformat()
    vault_io.write_file(
        "wiki/Lint History.md",
        f"# Lint History\n\n## {older} — run 1\n\nFirst.\n\n## {newer} — run 2\n\nSecond.\n",
    )

    result = health_strip.compute_lint_status()

    assert result["last_run"] == newer
    assert "run 2" in result["label"]


def test_istefox_status_ok_for_recent_write(vault):
    vault_io.write_file("wiki/Some Page.md", "content")

    result = health_strip.compute_istefox_status()

    assert result["status"] == "ok"
    assert result["last_write"] is not None


def test_istefox_status_skips_git_and_tmp_dirs(monkeypatch, tmp_path):
    # Deliberately bypasses the `vault` fixture -- it seeds fresh
    # modes/*/state.md files that would always read as "just now" and mask
    # the thing under test: that .git/.tmp.driveupload are excluded from
    # the "most recent write" scan even though they're the newest files.
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    import os

    old_time = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
    real_file = tmp_path / "wiki" / "Old Page.md"
    real_file.parent.mkdir(parents=True, exist_ok=True)
    real_file.write_text("old", encoding="utf-8")
    os.utime(real_file, (old_time, old_time))

    git_file = tmp_path / ".git" / "HEAD"
    git_file.parent.mkdir(parents=True, exist_ok=True)
    git_file.write_text("ref: refs/heads/main", encoding="utf-8")

    tmp_upload = tmp_path / ".tmp.driveupload" / "123"
    tmp_upload.parent.mkdir(parents=True, exist_ok=True)
    tmp_upload.write_text("x", encoding="utf-8")

    result = health_strip.compute_istefox_status()

    # Only "Old Page.md" (2 days old) should count -- .git/.tmp.driveupload
    # are newer (just written) but must be excluded, so status is stale.
    assert result["status"] == "stale"


def test_istefox_status_unknown_for_empty_vault(vault, tmp_path):
    for child in tmp_path.iterdir():
        if child.is_file():
            child.unlink()
        else:
            import shutil

            shutil.rmtree(child)

    result = health_strip.compute_istefox_status()

    assert result == {"status": "unknown", "last_write": None}
