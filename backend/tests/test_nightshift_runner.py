import vault_io
from nightshift import runner
from nightshift.slack_surface import SlackItem


def _seed_flagged_job(vault, slug="noctis-build"):
    vault_io.write_frontmatter(
        "modes/dev/state.md",
        {
            "mode": "dev",
            "busy": False,
            "jobs": [{"slug": slug, "name": "Noctis build", "stage": "Build", "status": "stalled", "flagged": True}],
        },
        "",
    )


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


def test_confidence_for_flagged_job_is_always_high_regardless_of_text():
    item = SlackItem(mode="dev", kind="flagged-job", slug_hint="x", description="d", context="c")
    assert runner._confidence_for(item, "no confidence section at all") == "high"


def test_confidence_for_distillation_reads_the_drafted_section():
    item = SlackItem(mode="settings", kind="undistilled-lessons", slug_hint="undistilled-learn", description="d", context="c")
    assert runner._confidence_for(item, "## Confidence\nlow -- one entry only.\n") == "low"
    assert runner._confidence_for(item, "no confidence section") is None


def test_run_stages_a_flagged_dev_job(vault, monkeypatch):
    _seed_flagged_job(vault)

    # only exercise the dev checker for this test -- settings' checker would
    # try to invoke a real `claude` subprocess otherwise
    monkeypatch.setitem(runner.SLACK_CHECKS, "learn", lambda: [])
    monkeypatch.setitem(runner.SLACK_CHECKS, "research", lambda: [])
    monkeypatch.setitem(runner.SLACK_CHECKS, "settings", lambda: [])

    slugs = runner.run()

    assert len(slugs) == 1
    assert slugs[0].startswith("flagged-job-noctis-build-")

    state, _ = vault_io.read_frontmatter(runner.STATE_PATH)
    assert len(state["inbox"]) == 1
    entry = state["inbox"][0]
    assert entry["origin_mode"] == "dev"
    assert entry["slug"] == slugs[0]
    assert entry["rationale"]
    # dev's flagged-job note is templated/read-only, never a judgment call --
    # confidence is always high, never left as the None placeholder it used to be.
    assert entry["confidence"] == "high"

    proposal_path = vault / "modes" / "nightshift" / "inbox" / f"{slugs[0]}.md"
    assert proposal_path.exists()
    assert "## Rationale" in proposal_path.read_text(encoding="utf-8")


def test_run_is_idempotent_against_already_pending_item(vault, monkeypatch):
    _seed_flagged_job(vault)
    monkeypatch.setitem(runner.SLACK_CHECKS, "learn", lambda: [])
    monkeypatch.setitem(runner.SLACK_CHECKS, "research", lambda: [])
    monkeypatch.setitem(runner.SLACK_CHECKS, "settings", lambda: [])

    first = runner.run()
    assert len(first) == 1

    second = runner.run()
    assert second == []

    state, _ = vault_io.read_frontmatter(runner.STATE_PATH)
    assert len(state["inbox"]) == 1


def test_identity_prefix_ignores_date_for_dedup():
    item = SlackItem(mode="dev", kind="flagged-job", slug_hint="x", description="d", context="c")
    assert runner._identity_prefix(item) == "flagged-job-x-"


def test_one_failing_item_does_not_drop_other_items(vault, monkeypatch):
    """A single failing/timing-out advance step (e.g. a claude subprocess
    call) must not abort the whole run and silently drop every other
    independent item -- 2026-07-21 ship-gate finding: this loop had no
    exception handling at all."""
    bad_item = SlackItem(mode="dev", kind="unregistered-kind", slug_hint="a", description="bad", context="c")
    good_item = SlackItem(mode="dev", kind="flagged-job", slug_hint="b", description="good", context="c")

    monkeypatch.setitem(runner.SLACK_CHECKS, "dev", lambda: [])
    monkeypatch.setitem(runner.SLACK_CHECKS, "learn", lambda: [bad_item])
    monkeypatch.setitem(runner.SLACK_CHECKS, "research", lambda: [good_item])
    monkeypatch.setitem(runner.SLACK_CHECKS, "settings", lambda: [])

    slugs = runner.run()

    assert len(slugs) == 1
    assert slugs[0].startswith("flagged-job-b-")
