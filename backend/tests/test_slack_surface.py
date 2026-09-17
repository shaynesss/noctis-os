import vault_io
from nightshift import slack_surface


def _job(slug, **meta):
    vault_io.write_frontmatter(f"modes/dev/jobs/{slug}/context.md", {"name": slug, "stage": "Build", "status": "in progress", **meta}, "")


def test_dev_has_no_slack_surface(vault):
    """A flagged job is not nightshift's to write about (2026-09-17). The
    note it staged proposed nothing, said so itself, sat beside the same job
    in the Inbox's own flagged list, and came back the night after it was
    accepted because dedup only checks what is still pending. Nightshift's
    part is setting the flag, which `staleness.flag_pass` does; the Inbox
    reads the flags, and acknowledging clears one."""
    _job("noctis-build", name="Noctis build", status="stalled", flagged=True)
    assert slack_surface.check_dev() == []


def test_check_settings_no_slack_when_cursor_matches_current_length(vault):
    dev_lessons = vault_io.read_file("modes/dev/lessons.md")
    line_count = len(dev_lessons.splitlines())
    vault_io.write_frontmatter(
        "maintenance/state.md",
        {
            "mode": "maintenance",
            "busy": False,
            "lessons_distilled_through": {
                "dev": line_count,
                "learn": 999,
                "research": 999,
                "maintenance": 999,
                "nightshift": 999,
            },
        },
        "",
    )
    assert slack_surface.check_settings() == []


def test_check_settings_surfaces_growth_past_cursor(vault):
    vault_io.write_file("modes/dev/lessons.md", "# Dev — Lessons\n\n- 2026-07-21 [x]: something learned.\n")
    vault_io.write_frontmatter(
        "maintenance/state.md",
        {"mode": "maintenance", "busy": False, "lessons_distilled_through": {"dev": 0}},
        "",
    )
    items = slack_surface.check_settings()
    slugs = [item.slug_hint for item in items]
    assert "undistilled-dev" in slugs


def test_check_learn_and_research_are_honest_empties(vault):
    assert slack_surface.check_learn() == []
    assert slack_surface.check_research() == []


def test_registry_covers_every_mode_with_a_checker():
    assert set(slack_surface.SLACK_CHECKS) == {"dev", "learn", "research", "settings"}
