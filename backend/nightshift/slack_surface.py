"""The slack-surface tap-in contract (nightshift.md's "Mechanism" section,
SPEC.md EDD): every mode declares its own pending/undone work in its own
`state.md`/lessons file; nightshift only knows *how to ask*, never *why* a
mode has slack. One checker function per mode, registered in SLACK_CHECKS
-- adding a mode to the roster means adding a checker here, nothing else
in this package should need mode-specific knowledge.
"""

from dataclasses import dataclass

import vault_io
from jobs import MAINTENANCE_STATE
from jobs import lessons_path


@dataclass
class SlackItem:
    mode: str
    kind: str
    slug_hint: str
    description: str
    context: str


def check_dev() -> list[SlackItem]:
    """Dev has no slack surface, and that is the whole of it (2026-09-17).

    It used to stage a status note for every flagged job. The note proposed
    nothing, said so itself ("Accepting archives this note. Nothing in
    Noctis changes."), and appeared beside the same job in the Inbox's own
    flagged list: one fact rendered twice, with an accept button that
    cleared neither. Worse, accepting archived it and the next run staged
    it again, because dedup only checks what is still pending.

    Nightshift's part in this is setting the flag, which `staleness.flag_pass`
    does at the top of a run. The Inbox reads the flags directly, and the
    acknowledge button is what clears one.
    """
    return []


def check_settings() -> list[SlackItem]:
    """Undistilled lessons: any mode whose lessons.md has grown since the
    last distillation pass, tracked via a line-count cursor in maintenance's
    own state.md (`lessons_distilled_through`). Advance-on-accept is wired:
    the accept route calls `apply.advance_lessons_cursor`, which reads the
    live line count rather than the number the draft carried.

    This is the one surviving trigger. Friction (a `FRICTION:` marker scan)
    and suspicion (a 7-day `state.md` staleness read) were computed by
    `triggers.py`, which went with the trigger badges at the v2 cutover;
    accumulation lives on here, as a nightly check rather than a badge.
    """
    settings_state, _ = vault_io.read_frontmatter(MAINTENANCE_STATE)
    cursor = settings_state.get("lessons_distilled_through", {}) or {}
    items = []
    # Vault folder names. Settings and nightshift collapsed into
    # root-level `maintenance/` at the 2026-09-12 cutover.
    for mode in ("dev", "learn", "research", "maintenance"):
        content = vault_io.read_file(lessons_path(mode))
        line_count = len(content.splitlines())
        if line_count > cursor.get(mode, 0):
            items.append(
                SlackItem(
                    mode="settings",
                    kind="undistilled-lessons",
                    slug_hint=f"undistilled-{mode}",
                    description=f"Custos: undistilled lessons in {mode}",
                    context=(
                        f"{lessons_path(mode)} grew from {cursor.get(mode, 0)} "
                        f"to {line_count} lines since the last distillation pass"
                    ),
                )
            )
    return items


def check_learn() -> list[SlackItem]:
    """Learn's declared slack surface is due recall items -- no real
    recall-bank data model exists yet, so this is an honest empty return,
    not a fabricated signal. A quiet night is a correct outcome (nightshift.md
    "What good looks like").
    """
    return []


def check_research() -> list[SlackItem]:
    """Same honest gap as check_learn: research's parked triggers and
    standing sweeps aren't backed by real state yet.
    """
    return []


SLACK_CHECKS = {
    "dev": check_dev,
    "learn": check_learn,
    "research": check_research,
    "settings": check_settings,
}
