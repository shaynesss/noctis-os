import vault_io
from nightshift import slack_surface


def test_check_dev_ignores_unflagged_jobs(vault):
    vault_io.write_frontmatter(
        "modes/dev/state.md",
        {"mode": "dev", "busy": False, "jobs": [{"slug": "a", "name": "A", "status": "in progress"}]},
        "",
    )
    assert slack_surface.check_dev() == []


def test_check_dev_surfaces_flagged_job(vault):
    vault_io.write_frontmatter(
        "modes/dev/state.md",
        {
            "mode": "dev",
            "busy": False,
            "jobs": [
                {"slug": "noctis-build", "name": "Noctis build", "stage": "Build", "status": "stalled", "flagged": True}
            ],
        },
        "",
    )
    items = slack_surface.check_dev()
    assert len(items) == 1
    assert items[0].mode == "dev"
    assert items[0].kind == "flagged-job"
    assert items[0].slug_hint == "noctis-build"


def test_check_settings_no_slack_when_cursor_matches_current_length(vault):
    dev_lessons = vault_io.read_file("modes/dev/lessons.md")
    line_count = len(dev_lessons.splitlines())
    vault_io.write_frontmatter(
        "modes/settings/state.md",
        {
            "mode": "settings",
            "busy": False,
            "lessons_distilled_through": {
                "dev": line_count,
                "learn": 999,
                "research": 999,
                "settings": 999,
                "nightshift": 999,
            },
        },
        "",
    )
    assert slack_surface.check_settings() == []


def test_check_settings_surfaces_growth_past_cursor(vault):
    vault_io.write_file("modes/dev/lessons.md", "# Dev — Lessons\n\n- 2026-07-21 [x]: something learned.\n")
    vault_io.write_frontmatter(
        "modes/settings/state.md",
        {"mode": "settings", "busy": False, "lessons_distilled_through": {"dev": 0}},
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
