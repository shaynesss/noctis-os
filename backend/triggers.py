"""Deterministic backend logic for Custos's three trigger badges
(settings.md: "thresholds for what counts as each firing are still an open
backend-logic question, tracked in SPEC.md" -- this module resolves it).
Runs inline on GET /mode/settings, matching staleness.py's pattern for dev
job flagging: computed live on every poll, not left to a session's say-so
(CLAUDE.md's "Deterministic-where-possible" rule).
"""

from datetime import datetime, timedelta, timezone

import vault_io

MODES = ("dev", "learn", "research", "settings", "nightshift")

# Judgment calls, noted rather than asked -- settings.md itself flagged
# these as an open question until this pass.
STALE_STATE_THRESHOLD = timedelta(days=7)
FRICTION_MARKER = "FRICTION:"


def _new_lessons_text(mode: str, cursor: dict) -> str:
    """Lines added to a mode's lessons.md since the last distillation pass
    -- the same cursor nightshift's settings slack-check already tracks
    (modes/settings/state.md's lessons_distilled_through), reused here
    rather than tracked a second time.

    This runs on every GET /mode/settings poll (World screen, every 15s) --
    a missing lessons.md (mid-setup for a mode, a vault file briefly absent
    during a git operation) must degrade to "no new text" rather than 500
    the whole poll. Every mode's lessons.md exists today by construction
    (seeded at mode-folder scaffolding time), so this is a defensive guard
    against a state that can't currently occur, not a fix for an observed
    failure -- caught in the 2026-07-21 ship-gate review.
    """
    if not vault_io.file_exists(f"modes/{mode}/lessons.md"):
        return ""
    content = vault_io.read_file(f"modes/{mode}/lessons.md")
    lines = content.splitlines()
    seen = cursor.get(mode, 0)
    return "\n".join(lines[seen:])


def compute_trigger_modes() -> dict[str, list[str]]:
    """Same three signals as compute_triggers() below, but names which
    mode(s) fired each one instead of collapsing straight to a bool --
    a bare "accumulation: true" can't tell you whether it's the same
    undistilled item you just addressed or a different mode's lessons.md
    that grew since, which reads as "didn't I already fix this?" on
    Custos's card when it's actually unrelated. Card renders this next to
    each lit trigger badge (ProfileOverlay.tsx's CustosBody).

    Friction: a lessons entry since the last distillation pass is
    explicitly tagged FRICTION: (a mode annoyed Shayne, a rule fought the
    work -- opt-in, not inferred from prose, since judging "did this entry
    describe friction" from free text isn't deterministic).
    Accumulation: any mode's lessons.md has grown past its distillation
    cursor -- identical signal to nightshift's undistilled-lessons slack
    check, reused rather than recomputed differently here.
    Suspicion: any mode's state.md hasn't been modified in
    STALE_STATE_THRESHOLD -- a vault smell, per settings.md's own
    definition ("drift, staleness, a vault smell").
    """
    settings_state, _ = vault_io.read_frontmatter("modes/settings/state.md")
    cursor = settings_state.get("lessons_distilled_through", {}) or {}

    accumulation_modes = []
    friction_modes = []
    for mode in MODES:
        new_text = _new_lessons_text(mode, cursor)
        if new_text.strip():
            accumulation_modes.append(mode)
        if FRICTION_MARKER in new_text:
            friction_modes.append(mode)

    suspicion_modes = []
    now = datetime.now(timezone.utc)
    vault_path = vault_io.get_vault_path()
    for mode in MODES:
        state_path = vault_path / "modes" / mode / "state.md"
        if not state_path.exists():
            continue
        mtime = datetime.fromtimestamp(state_path.stat().st_mtime, tz=timezone.utc)
        if now - mtime > STALE_STATE_THRESHOLD:
            suspicion_modes.append(mode)

    return {"friction": friction_modes, "accumulation": accumulation_modes, "suspicion": suspicion_modes}


def compute_triggers() -> dict[str, bool]:
    """The three lit/unlit badges themselves -- collapses
    compute_trigger_modes() to booleans, same return shape callers and
    tests already depend on."""
    return {trigger: bool(modes) for trigger, modes in compute_trigger_modes().items()}


def compute_diffs_awaiting_review() -> int:
    """"The one stat block on Custos's card" (settings.md) -- must reflect
    what's actually still sitting in nightshift's inbox, not a counter a
    settings session set when it staged the proposal and nothing ever
    updates again. `POST /nightshift/inbox/{id}/accept` (routers/
    nightshift.py) only touches nightshift's own inbox list and settings'
    lessons_distilled_through cursor; it has no reference back to the
    settings-mode job that staged the item, so it can't decrement a stored
    counter. Recomputing live here each poll -- same self-heal pattern as
    compute_triggers() above -- sidesteps needing that link at all: found
    2026-07-22 when an accepted item still read "1 diff staged, awaiting
    Shayne's accept" on Custos's card an hour after Echo's own inbox
    already showed empty.

    Counts only origin_mode == "settings" entries -- dev's flagged-job
    slack items land in the same inbox but never propose a diff (see
    runner.py's _draft_flagged_job_summary), so they aren't a "diff
    awaiting review" in the sense this stat means.
    """
    nightshift_state, _ = vault_io.read_frontmatter("modes/nightshift/state.md")
    inbox = nightshift_state.get("inbox", []) or []
    return sum(1 for item in inbox if item.get("origin_mode") == "settings")
