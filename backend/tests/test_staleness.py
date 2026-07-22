from datetime import datetime, timedelta, timezone

import staleness
import vault_io


def _seed_job(vault, mode="dev", slug="noctis-build", last_touched=None, flagged=False):
    job_dir = vault / "modes" / mode / "jobs" / slug
    job_dir.mkdir(parents=True)
    metadata = {"name": "Noctis build", "stage": "Build", "status": "in progress"}
    if last_touched:
        metadata["last_touched"] = last_touched
    if flagged:
        metadata["flagged"] = True
    vault_io.write_frontmatter(f"modes/{mode}/jobs/{slug}/context.md", metadata, "")

    state, content = vault_io.read_frontmatter(f"modes/{mode}/state.md")
    entry = {"slug": slug, "name": "Noctis build", "stage": "Build", "status": "in progress", "flagged": flagged}
    if last_touched:
        entry["last_touched"] = last_touched
    state["jobs"] = [entry]
    vault_io.write_frontmatter(f"modes/{mode}/state.md", state, content)


def test_recent_job_is_not_flagged(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(staleness, "RUNTIME_DIR", tmp_path / "runtime")
    recent = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    _seed_job(vault, last_touched=recent)

    flagged = staleness.flag_stale_jobs("dev")

    assert flagged == []
    metadata, _ = vault_io.read_frontmatter("modes/dev/jobs/noctis-build/context.md")
    assert not metadata.get("flagged")


def test_old_job_with_no_activity_gets_flagged(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(staleness, "RUNTIME_DIR", tmp_path / "runtime")
    old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    _seed_job(vault, last_touched=old)

    flagged = staleness.flag_stale_jobs("dev")

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

    flagged = staleness.flag_stale_jobs("dev")

    assert flagged == []


def test_already_flagged_job_is_skipped(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(staleness, "RUNTIME_DIR", tmp_path / "runtime")
    old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    _seed_job(vault, last_touched=old, flagged=True)

    flagged = staleness.flag_stale_jobs("dev")

    assert flagged == []


def test_job_with_no_last_touched_and_no_log_is_not_flagged(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(staleness, "RUNTIME_DIR", tmp_path / "runtime")
    _seed_job(vault, last_touched=None)

    flagged = staleness.flag_stale_jobs("dev")

    assert flagged == []


def test_flagging_generalizes_to_non_dev_modes(vault, monkeypatch, tmp_path):
    """learn/research/settings all promise the same stale-and-flagged
    behavior in their own Failure Behavior text -- this must genuinely work
    for a mode other than dev, not just accept a mode argument that's
    silently ignored."""
    monkeypatch.setattr(staleness, "RUNTIME_DIR", tmp_path / "runtime")
    old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    _seed_job(vault, mode="learn", slug="deep-dive-x", last_touched=old)

    flagged = staleness.flag_stale_jobs("learn")

    assert flagged == ["deep-dive-x"]
    metadata, _ = vault_io.read_frontmatter("modes/learn/jobs/deep-dive-x/context.md")
    assert metadata["flagged"] is True
    state, _ = vault_io.read_frontmatter("modes/learn/state.md")
    assert state["jobs"][0]["flagged"] is True

    # dev's own state must be untouched -- proves the mode argument scopes
    # the write, not just the read.
    dev_state, _ = vault_io.read_frontmatter("modes/dev/state.md")
    assert dev_state.get("jobs", []) == []


def test_session_end_substring_in_a_summary_does_not_count_as_clean_close(vault, monkeypatch, tmp_path):
    """A tool-call summary that happens to contain the literal text
    "SESSION_END" (e.g. editing mark_session_end.py itself) must not be
    misread as the clean-close sentinel -- 2026-07-21 ship-gate finding."""
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(staleness, "RUNTIME_DIR", runtime_dir)
    old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    _seed_job(vault, last_touched=old)

    runtime_dir.mkdir(parents=True)
    # Three tokens, not the real two-token sentinel -- old unanchored code
    # (`"SESSION_END" in last_line`) would have wrongly matched this.
    (runtime_dir / "dev__noctis-build.log").write_text(
        f"{old} Read SESSION_END.md\n", encoding="utf-8"
    )

    flagged = staleness.flag_stale_jobs("dev")

    assert flagged == ["noctis-build"]


def test_parse_last_touched_handles_bare_yaml_date():
    """A job's last_touched written as an unquoted `2026-07-22` (not the
    usual quoted ISO string) is parsed by PyYAML as a `date` object, not a
    str -- previously crashed every GET /mode/<name> poll for that mode via
    a TypeError inside datetime.fromisoformat. Found 2026-07-22 via a real
    research job entry."""
    from datetime import date

    result = staleness._parse_last_touched(date(2026, 7, 22))

    assert result == datetime(2026, 7, 22, tzinfo=timezone.utc)


def test_parse_last_touched_handles_datetime_object():
    value = datetime(2026, 7, 22, 12, 30, tzinfo=timezone.utc)

    assert staleness._parse_last_touched(value) == value


def test_parse_last_touched_handles_string():
    result = staleness._parse_last_touched("2026-07-22T12:30:00+00:00")

    assert result == datetime(2026, 7, 22, 12, 30, tzinfo=timezone.utc)


def test_parse_last_touched_handles_none():
    assert staleness._parse_last_touched(None) is None


def test_flag_stale_jobs_does_not_crash_on_bare_date_last_touched(vault, monkeypatch, tmp_path):
    """Regression test for the actual crash: GET /mode/research 500ing
    because a job's last_touched was a bare YAML date, not a quoted string."""
    from datetime import date

    monkeypatch.setattr(staleness, "RUNTIME_DIR", tmp_path / "runtime")
    _seed_job(vault, mode="research", slug="bare-date-job", last_touched=date(2026, 7, 22))

    # Must not raise.
    flagged = staleness.flag_stale_jobs("research")

    assert isinstance(flagged, list)
