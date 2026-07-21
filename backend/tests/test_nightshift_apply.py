import vault_io
from nightshift import apply

PROPOSAL_WITH_DIFF = """## Rationale
Testing a real diff apply.

## Diff
--- modes/settings/settings.md
+++ modes/settings/settings.md
@@
- old text here
+ new text here

## Evidence
- test evidence
"""

PROPOSAL_NO_DIFF = """## Rationale
Dev's flagged-job status note.

## Diff
(none -- dev's nightshift advance never proposes code or branch changes)

## Evidence
- job slug: x
"""


def test_apply_proposal_with_no_diff_section_is_a_noop(vault):
    assert apply.apply_proposal("no diff heading at all") is None


def test_apply_proposal_with_none_diff_is_a_noop(vault):
    assert apply.apply_proposal(PROPOSAL_NO_DIFF) is None


def test_apply_proposal_replaces_old_text_with_new(vault):
    vault_io.write_file("modes/settings/settings.md", "before\nold text here\nafter\n")

    target = apply.apply_proposal(PROPOSAL_WITH_DIFF)

    assert target == "modes/settings/settings.md"
    updated = vault_io.read_file("modes/settings/settings.md")
    assert "new text here" in updated
    assert "old text here" not in updated
    assert "before" in updated and "after" in updated


def test_apply_proposal_raises_when_old_text_not_found(vault):
    vault_io.write_file("modes/settings/settings.md", "completely different content\n")
    try:
        apply.apply_proposal(PROPOSAL_WITH_DIFF)
        assert False, "expected DiffApplyError"
    except apply.DiffApplyError:
        pass


def test_apply_proposal_raises_when_old_text_ambiguous(vault):
    vault_io.write_file(
        "modes/settings/settings.md", "old text here\nsomewhere else\nold text here\n"
    )
    try:
        apply.apply_proposal(PROPOSAL_WITH_DIFF)
        assert False, "expected DiffApplyError"
    except apply.DiffApplyError:
        pass


def test_parse_cursor_advance_extracts_mode_and_count():
    text = "## Rationale\nx\n\n<!-- cursor-advance: dev=17 -->\n"
    assert apply.parse_cursor_advance(text) == ("dev", 17)


def test_parse_cursor_advance_missing_marker_returns_none():
    assert apply.parse_cursor_advance("no marker here") is None


def test_advance_lessons_cursor_updates_settings_state(vault):
    vault_io.write_frontmatter(
        "modes/settings/state.md",
        {"mode": "settings", "busy": False, "lessons_distilled_through": {"dev": 12}},
        "",
    )

    apply.advance_lessons_cursor("dev", 20)

    state, _ = vault_io.read_frontmatter("modes/settings/state.md")
    assert state["lessons_distilled_through"]["dev"] == 20
