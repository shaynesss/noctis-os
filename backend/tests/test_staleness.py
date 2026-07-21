from datetime import datetime, timedelta, timezone

import staleness
import vault_io


def _seed_job(vault, slug="noctis-build", last_touched=None, flagged=False):
    job_dir = vault / "modes" / "dev" / "jobs" / slug
    job_dir.mkdir(parents=True)
    metadata = {"name": "Noctis build", "stage": "Build", "status": "in progress"}
    if last_touched:
        metadata["last_touched"] = last_touched
    if flagged:
        metadata["flagged"] = True
    vault_io.write_frontmatter(f"modes/dev/jobs/{slug}/context.md", metadata, "")

    state, content = vault_io.read_frontmatter("modes/dev/state.md")
    entry = {"slug": slug, "name": "Noctis build", "stage": "Build", "status": "in progress", "flagged": flagged}
    if last_touched:
        entry["last_touched"] = last_touched
    state["jobs"] = [entry]
    vault_io.write_frontmatter("modes/dev/state.md", state, content)


def test_recent_job_is_not_flagged(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(staleness, "RUNTIME_DIR", tmp_path / "runtime")
    recent = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    _seed_job(vault, last_touched=recent)

    flagged = staleness.flag_stale_dev_jobs()

    assert flagged == []
    metadata, _ = vault_io.read_frontmatter("modes/dev/jobs/noctis-build/context.md")
    assert not metadata.get("flagged")


def test_old_job_with_no_activity_gets_flagged(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(staleness, "RUNTIME_DIR", tmp_path / "runtime")
    old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    _seed_job(vault, last_touched=old)

    flagged = staleness.flag_stale_dev_jobs()

    assert flagged == ["noctis-build"]
    metadata, _ = vault_io.read_frontmatter("modes/dev/jobs/noctis-build/context.md")
    assert metadata["flagged"] is True
    state, _ = vault_io.read_frontmatter("modes/dev/state.md")
    assert state["jobs"][0]["flagged"] is True


def test_old_job_that_closed_cleanly_is_not_flagged(vault, monkeypatch, tmp_path):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(staleness, "RUNTIME_DIR", runtime_dir)
    old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    _seed_job(vault, last_touched=old)

    runtime_dir.mkdir(parents=True)
    (runtime_dir / "dev__noctis-build.log").write_text(f"{old} SESSION_END\n", encoding="utf-8")

    flagged = staleness.flag_stale_dev_jobs()

    assert flagged == []


def test_already_flagged_job_is_skipped(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(staleness, "RUNTIME_DIR", tmp_path / "runtime")
    old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    _seed_job(vault, last_touched=old, flagged=True)

    flagged = staleness.flag_stale_dev_jobs()

    assert flagged == []


def test_job_with_no_last_touched_and_no_log_is_not_flagged(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(staleness, "RUNTIME_DIR", tmp_path / "runtime")
    _seed_job(vault, last_touched=None)

    flagged = staleness.flag_stale_dev_jobs()

    assert flagged == []
