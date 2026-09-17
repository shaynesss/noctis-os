import pathlib

import vault_io
from nightshift import runner
from nightshift.slack_surface import SlackItem


def _seed_job(vault, slug="noctis-build", flagged=False, last_touched=None):
    meta = {"name": "Noctis build", "stage": "Build", "status": "stalled", "flagged": flagged}
    if last_touched:
        meta["last_touched"] = last_touched
    vault_io.write_frontmatter(f"modes/dev/jobs/{slug}/context.md", meta, "")


def _probe(slug="b"):
    """A kind of slack with a template for a drafter, registered for one
    test. The machinery below is about staging, dedup and fault isolation,
    not about any particular kind -- and riding on whichever kind existed
    is why these tests broke when dev's flagged-job note was removed."""
    return SlackItem(mode="dev", kind="probe", slug_hint=slug, description="a probe", context="ctx")


def _register_probe(monkeypatch):
    def draft(item, vault_path, inbox_path):
        inbox_path.write_text("## Rationale\nA probe.\n\n## Diff\n(none)\n\n## Evidence\n- none\n", encoding="utf-8")
    monkeypatch.setitem(runner.ADVANCE, "probe", draft)
    monkeypatch.setattr(runner, "MECHANICAL_KINDS", frozenset({"probe"}))
    for mode in ("dev", "learn", "research", "settings"):
        monkeypatch.setitem(runner.SLACK_CHECKS, mode, lambda: [])


def test_extract_rationale_reads_the_rationale_section():
    text = "## Rationale\nBecause X happened.\nTwice.\n\n## Diff\nsomething\n"
    assert runner._extract_rationale(text) == "Because X happened.\nTwice."


def test_extract_rationale_missing_section_returns_none():
    assert runner._extract_rationale("## Diff\nonly a diff\n") is None


def test_extract_confidence_reads_high_or_low():
    assert runner._extract_confidence("## Confidence\nhigh -- three sources agree.\n") == "high"
    assert runner._extract_confidence("## Confidence\nlow -- single entry, weak signal.\n") == "low"


def test_extract_confidence_missing_or_malformed_returns_none():
    assert runner._extract_confidence("## Diff\nonly a diff\n") is None
    assert runner._extract_confidence("## Confidence\nmaybe?\n") is None


def test_confidence_is_high_for_a_mechanical_kind_and_parsed_otherwise(monkeypatch):
    """A drafter that makes no judgment is not asked for one. No mechanical
    kind is registered today (dev's flagged-job note went on 2026-09-17), so
    the contract is tested rather than whichever kind happens to exist."""
    item = SlackItem(mode="dev", kind="templated", slug_hint="x", description="d", context="c")
    assert runner._confidence_for(item, "no confidence section at all") is None
    monkeypatch.setattr(runner, "MECHANICAL_KINDS", frozenset({"templated"}))
    assert runner._confidence_for(item, "no confidence section at all") == "high"


def test_confidence_for_distillation_reads_the_drafted_section():
    item = SlackItem(mode="settings", kind="undistilled-lessons", slug_hint="undistilled-learn", description="d", context="c")
    assert runner._confidence_for(item, "## Confidence\nlow -- one entry only.\n") == "low"
    assert runner._confidence_for(item, "no confidence section") is None


def test_run_stages_an_item_where_settings_reads(vault, monkeypatch):
    _register_probe(monkeypatch)
    monkeypatch.setitem(runner.SLACK_CHECKS, "dev", lambda: [_probe()])

    slugs, _failed, _dropped, _seen = runner.run()

    assert len(slugs) == 1
    assert slugs[0].startswith("probe-b-")

    state, _ = vault_io.read_frontmatter(runner.STATE_PATH)
    assert len(state["inbox"]) == 1
    entry = state["inbox"][0]
    assert entry["origin_mode"] == "dev"
    assert entry["slug"] == slugs[0]
    assert entry["rationale"]
    assert entry["confidence"] == "high"

    # maintenance/inbox, which is where Settings reads; drafts went to
    # modes/nightshift/inbox until 2026-09-16 and were never shown.
    proposal_path = vault / "maintenance" / "inbox" / f"{slugs[0]}.md"
    assert proposal_path.exists()
    assert "## Rationale" in proposal_path.read_text(encoding="utf-8")


def test_run_is_idempotent_against_already_pending_item(vault, monkeypatch):
    _register_probe(monkeypatch)
    monkeypatch.setitem(runner.SLACK_CHECKS, "dev", lambda: [_probe()])

    first, _, _, _ = runner.run()
    assert len(first) == 1

    second, _, _, _ = runner.run()
    assert second == []

    state, _ = vault_io.read_frontmatter(runner.STATE_PATH)
    assert len(state["inbox"]) == 1


def test_identity_prefix_ignores_date_for_dedup():
    item = SlackItem(mode="dev", kind="undistilled-lessons", slug_hint="x", description="d", context="c")
    assert runner._identity_prefix(item) == "undistilled-lessons-x-"


def test_one_failing_item_does_not_drop_other_items(vault, monkeypatch):
    """A single failing/timing-out advance step (e.g. a claude subprocess
    call) must not abort the whole run and silently drop every other
    independent item -- 2026-07-21 ship-gate finding: this loop had no
    exception handling at all."""
    bad_item = SlackItem(mode="dev", kind="unregistered-kind", slug_hint="a", description="bad", context="c")

    _register_probe(monkeypatch)
    monkeypatch.setitem(runner.SLACK_CHECKS, "learn", lambda: [bad_item])
    monkeypatch.setitem(runner.SLACK_CHECKS, "research", lambda: [_probe()])

    slugs, _failed, _dropped, _seen = runner.run()

    assert len(slugs) == 1
    assert slugs[0].startswith("probe-b-")


def test_run_flags_a_stale_job_and_stages_nothing_for_it(vault, monkeypatch, tmp_path):
    """The deterministic half runs first: a job whose session died three days
    ago is flagged in its own context. Nothing is staged about it -- the
    Inbox lists flags directly, and the note that used to be written here
    proposed nothing, sat beside the same job in that list, and came back
    the night after it was accepted (removed 2026-09-17)."""
    import staleness
    from datetime import datetime, timedelta, timezone
    runtime = tmp_path / "runtime"; runtime.mkdir()
    monkeypatch.setattr(staleness, "RUNTIME_DIR", runtime)
    for mode in ("dev", "learn", "research", "settings"):
        monkeypatch.setitem(runner.SLACK_CHECKS, mode, lambda: [])
    old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    # The context was written before the session ran: nobody has looked
    # since it stopped, which is what makes it unattended.
    _seed_job(vault, slug="died-mid-build",
              last_touched=(datetime.now(timezone.utc) - timedelta(days=4)).isoformat())
    (runtime / "dev__died-mid-build.log").write_text(f"{old} Edit x\n", encoding="utf-8")

    slugs, _failed, _dropped, _seen = runner.run()

    meta, _ = vault_io.read_frontmatter("modes/dev/jobs/died-mid-build/context.md")
    assert meta["flagged"] is True
    assert slugs == []


# --- drops: the outcome that was neither staged, nor failed, nor nothing ------
#
# Until 2026-09-17 each of these three gates was a bare `continue`. The item
# counted in `seen`, appeared in neither `staged` nor `failed`, and the night
# reported itself quiet: `data/nightshift.json` holds `seen: 3, staged: 0,
# failed: 0` for 2026-09-16 and `seen: 4, staged: 1, failed: 0` for 09-17,
# which is three paid-for distiller calls discarded each night, unlogged.

def _register_drafter(monkeypatch, draft_text: str | None):
    def draft(item, vault_path, inbox_path):
        if draft_text is not None:
            inbox_path.write_text(draft_text, encoding="utf-8")
    monkeypatch.setitem(runner.ADVANCE, "probe", draft)
    monkeypatch.setattr(runner, "MECHANICAL_KINDS", frozenset())
    for mode in ("dev", "learn", "research", "settings"):
        monkeypatch.setitem(runner.SLACK_CHECKS, mode, lambda: [])
    monkeypatch.setitem(runner.SLACK_CHECKS, "dev", lambda: [_probe()])


def test_a_drafter_that_writes_nothing_is_recorded_not_forgotten(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DROPS_DIR", tmp_path / "drops")
    _register_drafter(monkeypatch, None)

    staged, failed, dropped, seen = runner.run()

    assert (staged, failed, seen) == ([], [], 1)
    assert len(dropped) == 1
    assert dropped[0]["gate"] == "no-draft"
    assert dropped[0]["kept"] is None       # there was no draft to keep


def test_a_draft_missing_its_rationale_is_kept_for_reading(vault, monkeypatch, tmp_path):
    """The gate was silent *and* it unlinked the draft, so the morning had
    neither a reason nor an artefact. The draft moves to runtime now."""
    monkeypatch.setattr(runner, "DROPS_DIR", tmp_path / "drops")
    _register_drafter(monkeypatch, "## Diff\n(none)\n\n## Confidence\nhigh -- sure.\n")

    _staged, _failed, dropped, _seen = runner.run()

    assert dropped[0]["gate"] == "no-rationale"
    kept = pathlib.Path(dropped[0]["kept"])
    assert kept.exists() and "## Diff" in kept.read_text()


def test_a_draft_with_no_usable_confidence_is_dropped_and_kept(vault, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "DROPS_DIR", tmp_path / "drops")
    _register_drafter(monkeypatch, "## Rationale\nA probe.\n\n## Confidence\nmaybe?\n")

    _staged, _failed, dropped, _seen = runner.run()

    assert dropped[0]["gate"] == "no-confidence"
    assert pathlib.Path(dropped[0]["kept"]).exists()


def test_a_dropped_draft_does_not_stay_in_the_inbox(vault, monkeypatch, tmp_path):
    """A rejected draft must not be left where Settings lists proposals: it
    met none of the contract the listing assumes."""
    monkeypatch.setattr(runner, "DROPS_DIR", tmp_path / "drops")
    _register_drafter(monkeypatch, "## Diff\n(none)\n")

    _staged, _failed, dropped, _seen = runner.run()

    inbox = vault_io.get_vault_path() / runner.MAINTENANCE_INBOX
    assert not (inbox / f"{dropped[0]['slug']}.md").exists()
    state, _ = vault_io.read_frontmatter(runner.STATE_PATH)
    assert state.get("inbox") in ([], None)


def test_the_cursor_marker_uses_the_real_lessons_path_for_maintenance(vault, monkeypatch):
    """`maintenance/lessons.md` is not `modes/maintenance/lessons.md`, and
    the drafter hardcoded the second shape. Any maintenance draft that got
    as far as the marker raised FileNotFoundError and took the whole item
    down as a failure (found 2026-09-17)."""
    vault_io.write_file("maintenance/lessons.md", "# Lessons\n\none\ntwo\n")
    # What the drafter reads before it calls anything.
    vault_io.write_file("maintenance/schedule.md", "# Schedule\n")
    vault_io.write_file("maintenance/agents/distiller.md", "# Distiller\n")
    vault_io.write_file(f"{runner.MAINTENANCE_INBOX}/README.md", "# Format\n")
    item = SlackItem(mode="settings", kind="undistilled-lessons",
                     slug_hint="undistilled-maintenance", description="d", context="c")
    inbox = vault_io.get_vault_path() / runner.MAINTENANCE_INBOX
    inbox.mkdir(parents=True, exist_ok=True)
    draft = inbox / "probe.md"
    draft.write_text("## Rationale\nx\n", encoding="utf-8")

    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: None)
    runner._draft_distillation(item, vault_io.get_vault_path(), draft)

    assert "<!-- cursor-advance: maintenance=4 -->" in draft.read_text()
