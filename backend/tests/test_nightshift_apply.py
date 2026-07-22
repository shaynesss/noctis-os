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

PROPOSAL_WITH_TWO_HUNKS = """## Rationale
Testing a diff that touches two separate spots in the same file.

## Diff
--- modes/settings/settings.md
+++ modes/settings/settings.md
@@
- first old spot
+ first new spot
@@
- second old spot
+ second new spot

## Evidence
- test evidence
"""

PROPOSAL_INSERTION_ONLY = """## Rationale
Testing a hunk with no removed lines -- a context anchor plus pure additions.

## Diff
--- modes/settings/settings.md
+++ modes/settings/settings.md
@@
 anchor line stays put
+
+new paragraph inserted after the anchor

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


def test_apply_proposal_applies_each_hunk_independently(vault):
    vault_io.write_file(
        "modes/settings/settings.md",
        "before\nfirst old spot\nmiddle\nsecond old spot\nafter\n",
    )

    target = apply.apply_proposal(PROPOSAL_WITH_TWO_HUNKS)

    assert target == "modes/settings/settings.md"
    updated = vault_io.read_file("modes/settings/settings.md")
    assert "first new spot" in updated and "second new spot" in updated
    assert "first old spot" not in updated and "second old spot" not in updated
    assert "middle" in updated


def test_apply_proposal_applies_insertion_only_hunk_anchored_on_context(vault):
    vault_io.write_file(
        "modes/settings/settings.md",
        "before\nanchor line stays put\n\nnext paragraph\nafter\n",
    )

    target = apply.apply_proposal(PROPOSAL_INSERTION_ONLY)

    assert target == "modes/settings/settings.md"
    updated = vault_io.read_file("modes/settings/settings.md")
    assert (
        "anchor line stays put\n\nnew paragraph inserted after the anchor\n\nnext paragraph"
        in updated
    )


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


def test_parse_cursor_advance_extracts_mode():
    text = "## Rationale\nx\n\n<!-- cursor-advance: dev=17 -->\n"
    assert apply.parse_cursor_advance(text) == "dev"


def test_parse_cursor_advance_missing_marker_returns_none():
    assert apply.parse_cursor_advance("no marker here") is None


def test_advance_lessons_cursor_uses_live_lessons_line_count_not_marker_number(vault):
    """A session-supplied count is untrusted by design (settings.md's own
    lessons.md growing past a proposal-drafted number by the time the
    session appends its closing retro is the exact bug this guards
    against) -- advance_lessons_cursor must read the live file, not accept
    a count argument that could already be stale.
    """
    vault_io.write_frontmatter(
        "modes/settings/state.md",
        {"mode": "settings", "busy": False, "lessons_distilled_through": {"dev": 12}},
        "",
    )
    vault_io.write_file("modes/dev/lessons.md", "line one\nline two\nline three\n")

    apply.advance_lessons_cursor("dev")

    state, _ = vault_io.read_frontmatter("modes/settings/state.md")
    assert state["lessons_distilled_through"]["dev"] == 3


def test_parse_job_origin_extracts_mode_and_slug():
    text = "## Rationale\nx\n\n<!-- job-origin: settings/address-accumulation-20260722 -->\n"
    assert apply.parse_job_origin(text) == ("settings", "address-accumulation-20260722")


def test_parse_job_origin_missing_marker_returns_none():
    assert apply.parse_job_origin("no marker here") is None


def test_close_job_marks_context_and_state_entry_done(vault):
    vault_io.write_frontmatter(
        "modes/settings/jobs/address-accumulation-20260722/context.md",
        {"name": "Address accumulation", "stage": "Propose", "status": "1 diff staged"},
        "some prose",
    )
    vault_io.write_frontmatter(
        "modes/settings/state.md",
        {
            "mode": "settings",
            "busy": False,
            "jobs": [
                {"slug": "address-accumulation-20260722", "name": "Address accumulation", "stage": "Propose"},
                {"slug": "other-job", "name": "Other job", "stage": "Audit"},
            ],
        },
        "",
    )

    apply.close_job("settings", "address-accumulation-20260722", "Resolved: test.")

    job_meta, job_content = vault_io.read_frontmatter(
        "modes/settings/jobs/address-accumulation-20260722/context.md"
    )
    assert job_meta["stage"] == "Done"
    assert job_meta["status"] == "Resolved: test."
    assert job_content == "some prose"

    # Stays visible in state.md's jobs list, marked Done -- not removed --
    # so the card shows the resolution instead of the job just vanishing.
    state, _ = vault_io.read_frontmatter("modes/settings/state.md")
    jobs_by_slug = {j["slug"]: j for j in state["jobs"]}
    assert jobs_by_slug["address-accumulation-20260722"]["stage"] == "Done"
    assert jobs_by_slug["address-accumulation-20260722"]["status"] == "Resolved: test."
    assert jobs_by_slug["other-job"]["stage"] == "Audit"


def test_close_job_is_a_noop_when_job_context_missing(vault):
    vault_io.write_frontmatter(
        "modes/settings/state.md",
        {"mode": "settings", "busy": False, "jobs": []},
        "",
    )

    apply.close_job("settings", "never-existed", "Resolved: test.")

    state, _ = vault_io.read_frontmatter("modes/settings/state.md")
    assert state["jobs"] == []
