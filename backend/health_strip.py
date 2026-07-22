"""Backend logic for the world screen's health strip (World.tsx): a lint
status read from the vault's Lint History, and an istefox proxy signal.

Both were static placeholders in World.tsx pending "a real backend health
endpoint ... once Settings mode's audit capabilities expose one" -- this
module is that endpoint's logic. Scoped down from the original three-part
ask (lint, istefox, Claude weekly usage %) after confirming there is no
public API for an individual account's weekly usage percentage; that item
was dropped rather than faked.
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
_ISTEFOX_SKIP_DIRS = {".git", ".obsidian", "node_modules", "__pycache__"}
_ISTEFOX_SKIP_PREFIXES = (".tmp.",)
_ISTEFOX_STALE_AFTER_SECONDS = 24 * 60 * 60


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


def compute_istefox_status() -> dict:
    """Proxy signal for the istefox connector, not a real heartbeat --
    no such heartbeat exists anywhere in this codebase, and building one
    would mean finding and instrumenting wherever the connector's own code
    lives, out of scope for this pass (see the 2026-07-22 settings-mode
    scoping decision). Surfaces the most recent mtime across the vault as
    "is anything touching this vault lately," which is what the health
    strip actually needs: a rough liveness signal, not connector-specific
    telemetry.
    """
    vault_path = vault_io.get_vault_path()
    latest: float | None = None
    for path in vault_path.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _ISTEFOX_SKIP_DIRS for part in path.parts):
            continue
        if any(
            part.startswith(prefix) for part in path.parts for prefix in _ISTEFOX_SKIP_PREFIXES
        ):
            continue
        mtime = path.stat().st_mtime
        if latest is None or mtime > latest:
            latest = mtime

    if latest is None:
        return {"status": "unknown", "last_write": None}

    last_write = datetime.fromtimestamp(latest, tz=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - last_write).total_seconds()
    status = "ok" if age_seconds <= _ISTEFOX_STALE_AFTER_SECONDS else "stale"
    return {"status": status, "last_write": last_write.isoformat()}
