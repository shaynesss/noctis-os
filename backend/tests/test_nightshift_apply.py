import vault_io
from nightshift import apply

PROPOSAL_WITH_DIFF = """## Rationale
Testing a real diff apply.

## Diff
--- maintenance/audit.md
+++ maintenance/audit.md
@@
- old text here
+ new text here

## Evidence
- test evidence
"""

PROPOSAL_WITH_TWO_HUNKS = """## Rationale
Testing a diff that touches two separate spots in the same file.

## Diff
--- maintenance/audit.md
+++ maintenance/audit.md
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
--- maintenance/audit.md
+++ maintenance/audit.md
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
    vault_io.write_file("maintenance/audit.md", "before\nold text here\nafter\n")

    target = apply.apply_proposal(PROPOSAL_WITH_DIFF)

    assert target == "maintenance/audit.md"
    updated = vault_io.read_file("maintenance/audit.md")
    assert "new text here" in updated
    assert "old text here" not in updated
    assert "before" in updated and "after" in updated


def test_apply_proposal_applies_each_hunk_independently(vault):
    vault_io.write_file(
        "maintenance/audit.md",
        "before\nfirst old spot\nmiddle\nsecond old spot\nafter\n",
    )

    target = apply.apply_proposal(PROPOSAL_WITH_TWO_HUNKS)

    assert target == "maintenance/audit.md"
    updated = vault_io.read_file("maintenance/audit.md")
    assert "first new spot" in updated and "second new spot" in updated
    assert "first old spot" not in updated and "second old spot" not in updated
    assert "middle" in updated


def test_apply_proposal_applies_insertion_only_hunk_anchored_on_context(vault):
    vault_io.write_file(
        "maintenance/audit.md",
        "before\nanchor line stays put\n\nnext paragraph\nafter\n",
    )

    target = apply.apply_proposal(PROPOSAL_INSERTION_ONLY)

    assert target == "maintenance/audit.md"
    updated = vault_io.read_file("maintenance/audit.md")
    assert (
        "anchor line stays put\n\nnew paragraph inserted after the anchor\n\nnext paragraph"
        in updated
    )


def test_apply_proposal_raises_when_old_text_not_found(vault):
    vault_io.write_file("maintenance/audit.md", "completely different content\n")
    try:
        apply.apply_proposal(PROPOSAL_WITH_DIFF)
        assert False, "expected DiffApplyError"
    except apply.DiffApplyError:
        pass


def test_apply_proposal_raises_when_old_text_ambiguous(vault):
    vault_io.write_file(
        "maintenance/audit.md", "old text here\nsomewhere else\nold text here\n"
    )
    try:
        apply.apply_proposal(PROPOSAL_WITH_DIFF)
        assert False, "expected DiffApplyError"
    except apply.DiffApplyError:
        pass


PROPOSAL_TARGETING_PATH_WITH_SPACE = """## Rationale
Testing a diff whose target path contains a space, like a real wiki folder
name ("Noctis OS").

## Diff
--- wiki/Noctis OS/Modes.md
+++ wiki/Noctis OS/Modes.md
@@
- old text here
+ new text here

## Evidence
- test evidence
"""


def test_apply_proposal_target_path_with_space_is_not_truncated(vault):
    """Found 2026-07-27: the target-path regex was `\\S+` (stops at the
    first space), so the first-ever proposal targeting a path outside
    modes/*/*.md (a wiki page whose parent folder is "Noctis OS", a real
    space in a real path) silently truncated to "wiki/Noctis" and raised a
    bare FileNotFoundError. Every prior proposal only ever targeted
    modes/<name>/<name>.md, which never has a space, so this was never
    exercised before.
    """
    vault_io.write_file("wiki/Noctis OS/Modes.md", "before\nold text here\nafter\n")

    target = apply.apply_proposal(PROPOSAL_TARGETING_PATH_WITH_SPACE)

    assert target == "wiki/Noctis OS/Modes.md"
    updated = vault_io.read_file("wiki/Noctis OS/Modes.md")
    assert "new text here" in updated
    assert "old text here" not in updated


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
        "maintenance/state.md",
        {"mode": "maintenance", "busy": False, "lessons_distilled_through": {"dev": 12}},
        "",
    )
    vault_io.write_file("modes/dev/lessons.md", "line one\nline two\nline three\n")

    apply.advance_lessons_cursor("dev")

    state, _ = vault_io.read_frontmatter("maintenance/state.md")
    assert state["lessons_distilled_through"]["dev"] == 3


def test_parse_job_origin_extracts_mode_and_slug():
    text = "## Rationale\nx\n\n<!-- job-origin: settings/address-accumulation-20260722 -->\n"
    assert apply.parse_job_origin(text) == ("settings", "address-accumulation-20260722")


def test_parse_job_origin_missing_marker_returns_none():
    assert apply.parse_job_origin("no marker here") is None


def test_close_job_marks_the_job_folder_done(vault):
    vault_io.write_frontmatter(
        "maintenance/jobs/address-accumulation-20260722/context.md",
        {"name": "Address accumulation", "stage": "Propose", "status": "1 diff staged"},
        "some prose",
    )

    apply.close_job("maintenance", "address-accumulation-20260722", "Resolved: test.")

    job_meta, job_content = vault_io.read_frontmatter(
        "maintenance/jobs/address-accumulation-20260722/context.md"
    )
    assert job_meta["stage"] == "Done"
    assert job_meta["status"] == "Resolved: test."
    assert job_content == "some prose"


def test_close_job_does_not_write_the_dead_state_jobs_array(vault):
    """`state.md`'s `jobs` was v1's mirror of the job folders. The route that
    maintained it went at the 2026-09-12 cutover and every reader was pointed
    at the folders on 09-16, leaving this the sole writer of a structure
    nothing reads -- and it had already drifted (learn held none against one
    folder, maintenance twenty-six against twenty-seven). A stale mirror is
    what three readers trusted for four days after it stopped being true."""
    vault_io.write_frontmatter(
        "maintenance/jobs/j/context.md", {"name": "J", "stage": "Propose"}, "")
    before = [{"slug": "j", "name": "J", "stage": "Propose"}]
    vault_io.write_frontmatter(
        "maintenance/state.md", {"mode": "maintenance", "jobs": list(before)}, "")

    apply.close_job("maintenance", "j", "Resolved: test.")

    state, _ = vault_io.read_frontmatter("maintenance/state.md")
    assert state["jobs"] == before, "state.md must be left exactly as it was found"
    assert vault_io.read_frontmatter("maintenance/jobs/j/context.md")[0]["stage"] == "Done"


def test_close_job_is_a_noop_when_job_context_missing(vault):
    vault_io.write_frontmatter(
        "maintenance/state.md",
        {"mode": "maintenance", "busy": False, "jobs": []},
        "",
    )

    apply.close_job("maintenance", "never-existed", "Resolved: test.")

    state, _ = vault_io.read_frontmatter("maintenance/state.md")
    assert state["jobs"] == []


# --- what a real drafter actually writes -------------------------------------

PROPOSAL_WITH_GIT_STYLE_HEADERS = """## Rationale
A pattern worth a change.

## Diff
--- a/modes/dev/dev.md
+++ b/modes/dev/dev.md
@@
-old text here
+new text here

## Evidence
- modes/dev/lessons.md, 2026-09-18
"""


def test_apply_proposal_strips_the_git_style_a_prefix_from_the_target(vault):
    """The inbox format's example has a bare path, and the first live
    distillation proposal (2026-09-18, once the drafter could return one at
    all) wrote `--- a/modes/dev/dev.md` anyway, which is what `git diff`
    produces and what a model has read ten thousand of. Reading it literally
    looks for a vault file called `a/modes/...` and raises FileNotFoundError,
    which the accept route turns into a 500.
    """
    vault_io.write_file("modes/dev/dev.md", "before\nold text here\nafter\n")

    target = apply.apply_proposal(PROPOSAL_WITH_GIT_STYLE_HEADERS)

    assert target == "modes/dev/dev.md"
    assert "new text here" in vault_io.read_file("modes/dev/dev.md")


PROPOSAL_TARGETING_A_MISSING_FILE = PROPOSAL_WITH_GIT_STYLE_HEADERS.replace(
    "modes/dev/dev.md", "modes/nowhere/nothing.md")


def test_apply_proposal_raises_a_409_reason_for_a_target_the_vault_lacks(vault):
    """Not a 500: the reader needs to know which file the proposal meant."""
    try:
        apply.apply_proposal(PROPOSAL_TARGETING_A_MISSING_FILE)
        assert False, "expected DiffApplyError"
    except apply.DiffApplyError as exc:
        assert "not in the vault" in str(exc)
        assert "modes/nowhere/nothing.md" in str(exc)
