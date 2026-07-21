"""The slack-surface tap-in contract (nightshift.md's "Mechanism" section,
SPEC.md EDD): every mode declares its own pending/undone work in its own
`state.md`/lessons file; nightshift only knows *how to ask*, never *why* a
mode has slack. One checker function per mode, registered in SLACK_CHECKS
-- adding a mode to the roster means adding a checker here, nothing else
in this package should need mode-specific knowledge.
"""

from dataclasses import dataclass

import vault_io


@dataclass
class SlackItem:
    mode: str
    kind: str
    slug_hint: str
    description: str
    context: str


def check_dev() -> list[SlackItem]:
    """Dev's slack surface, deliberately near-empty (dev.md's Failure
    Behavior / highest blast radius in the system): flagged-not-frozen
    jobs only -- a session that died mid-build, marked flagged rather than
    silently frozen. Never code or branch work.
    """
    state, _ = vault_io.read_frontmatter("modes/dev/state.md")
    items = []
    for job in state.get("jobs", []):
        if job.get("flagged"):
            items.append(
                SlackItem(
                    mode="dev",
                    kind="flagged-job",
                    slug_hint=job["slug"],
                    description=f"Faber: {job.get('name', job['slug'])} flagged mid-build",
                    context=(
                        f"job slug: {job['slug']}, stage: {job.get('stage')}, "
                        f"status: {job.get('status')}, last_touched: {job.get('last_touched')}"
                    ),
                )
            )
    return items


def check_settings() -> list[SlackItem]:
    """Undistilled lessons: any mode whose lessons.md has grown since the
    last distillation pass, tracked via a line-count cursor in settings'
    own state.md (`lessons_distilled_through`). Cursor advance-on-accept
    isn't wired yet -- known follow-up, same shape as nightshift's other
    not-yet-built mode-specific apply logic (see STATUS.md).
    """
    settings_state, _ = vault_io.read_frontmatter("modes/settings/state.md")
    cursor = settings_state.get("lessons_distilled_through", {}) or {}
    items = []
    for mode in ("dev", "learn", "research", "settings", "nightshift"):
        content = vault_io.read_file(f"modes/{mode}/lessons.md")
        line_count = len(content.splitlines())
        if line_count > cursor.get(mode, 0):
            items.append(
                SlackItem(
                    mode="settings",
                    kind="undistilled-lessons",
                    slug_hint=f"undistilled-{mode}",
                    description=f"Custos: undistilled lessons in {mode}",
                    context=(
                        f"modes/{mode}/lessons.md grew from {cursor.get(mode, 0)} "
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
