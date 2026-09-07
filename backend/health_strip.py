"""Backend logic for the world screen's health strip (World.tsx): a lint
status read from the vault's Lint History.

Was a static placeholder in World.tsx pending "a real backend health
endpoint ... once Settings mode's audit capabilities expose one" -- this
module is that endpoint's logic. Scoped down from the original three-part
ask (lint, istefox, Claude weekly usage %): the weekly-usage item was
dropped rather than faked (no public per-account API), and the istefox
proxy signal was removed 2026-09-07 as Noctis v2 Stage 1 item 1, with
Obsidian demoted from dependency to optional viewer.
"""

import re
from datetime import datetime, timezone

import vault_io

_LINT_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_LINT_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

_LINT_STALE_AFTER_DAYS = 7

# Directories/files a vault-wide "most recent write" walk must skip -- not
# real vault content, or noisy sync artifacts. Mirrors the lint scanner's
# own node_modules/.git exclusion gap documented in wiki/Lint History.md's
# 2026-07-20 run.


def compute_lint_status() -> dict:
    """Reads the last `## `-headed entry in wiki/Lint History.md (newest
    is appended at the bottom, per that file's own "How to use this page"
    instructions) and surfaces its date and heading label -- not a
    fabricated aging/fixed/new count. Entries are freeform prose with no
    consistent structure run to run (some list "Aging:", others "Fixed
    this run:"), so a numeric count extracted from them would be a guess
    dressed up as data. The date is the one thing reliably extractable.
    """
    if not vault_io.file_exists("wiki/Lint History.md"):
        return {"status": "unknown", "last_run": None, "label": None}

    content = vault_io.read_file("wiki/Lint History.md")
    headings = _LINT_HEADING_RE.findall(content)
    if not headings:
        return {"status": "unknown", "last_run": None, "label": None}

    last_heading = headings[-1].strip()
    date_match = _LINT_DATE_RE.search(last_heading)
    last_run = date_match.group(1) if date_match else None

    status = "unknown"
    if last_run:
        age_days = (
            datetime.now(timezone.utc).date() - datetime.strptime(last_run, "%Y-%m-%d").date()
        ).days
        status = "ok" if age_days <= _LINT_STALE_AFTER_DAYS else "stale"

    return {"status": status, "last_run": last_run, "label": last_heading}
