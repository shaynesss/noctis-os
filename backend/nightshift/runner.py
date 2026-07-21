"""Nightshift's Scan -> Advance -> Stage loop (nightshift.md section 2),
the launchd entrypoint's actual logic (scripts/nightshift_run.sh just
invokes this). Propose-never-commit: writes only to
modes/nightshift/inbox/<slug>.md and the mirrored index entry in
modes/nightshift/state.md -- nothing else in the vault, ever.
"""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

# launchd runs this with no shell env at all -- same fix as main.py, for
# the same reason (VAULT_PATH/NOCTIS_API_TOKEN only exist if explicitly
# loaded, not just because a shell happened to source .env once).
load_dotenv(Path(__file__).parent.parent.parent / ".env")

import vault_io  # noqa: E402
from nightshift.slack_surface import SLACK_CHECKS, SlackItem  # noqa: E402

STATE_PATH = "modes/nightshift/state.md"
DISTILLER_MODEL = "claude-haiku-4-5"


def _existing_pending_slugs() -> list[str]:
    """Slugs already staged and awaiting review -- Scan re-derives slack
    from scratch every run (nightshift.md's Failure Behavior: no memory of
    its own prior runs), so Stage is the one place that must be idempotent
    against what's already pending.
    """
    state, _ = vault_io.read_frontmatter(STATE_PATH)
    return [item.get("slug", "") for item in state.get("inbox", [])]


def _identity_prefix(item: SlackItem) -> str:
    """The stable part of a slug -- everything but the run's date stamp.
    Dedup must match on this, not the full slug: two runs on different
    days produce different date-stamped slugs for the *same* underlying
    slack, and staging both every night would be exactly the re-proposing
    spam Stage's idempotency is supposed to prevent.
    """
    return f"{item.kind}-{item.slug_hint}-"


def _slug_for(item: SlackItem) -> str:
    date = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{_identity_prefix(item)}{date}"


def _draft_flagged_job_summary(item: SlackItem, vault_path: Path, inbox_path: Path) -> None:
    """Dev's slack surface stays mechanical on purpose (dev.md's Failure
    Behavior: highest blast radius in the system) -- a templated status/
    staleness note, never a live subagent producing code or branch advice.
    """
    body = (
        "## Rationale\n"
        f"{item.description} and hasn't been touched since it was flagged. "
        "Surfacing for a status check, not proposing any code or branch change "
        "(dev's slack surface is deliberately read-only per dev.md's Failure Behavior).\n\n"
        "## Diff\n"
        "(none -- dev's nightshift advance never proposes code or branch changes)\n\n"
        "## Evidence\n"
        f"- {item.context}\n"
    )
    inbox_path.write_text(body, encoding="utf-8")


def _draft_distillation(item: SlackItem, vault_path: Path, inbox_path: Path) -> None:
    """Settings' slack surface genuinely needs judgment (identify a
    recurring pattern, draft a diff candidate) -- borrows settings' own
    distiller subagent at reduced permission: read-only over the vault,
    write scoped to exactly this one inbox file, no bash, no network.
    """
    methodology = vault_io.read_file("modes/nightshift/nightshift.md")
    agent_def = vault_io.read_file("modes/settings/agents/distiller.md")
    readme = vault_io.read_file("modes/nightshift/inbox/README.md")

    prompt = f"""{methodology}

---

You are nightshift's Advance step for this run, borrowing settings mode's
distiller subagent at reduced permission (drafts only, never writes to a
live mode file):

{agent_def}

---

Required proposal format:

{readme}

---

Task: {item.context}. Read the relevant lessons.md file(s) under modes/,
identify the specific pattern, and write ONE proposal file to exactly this
path: {inbox_path}
Follow the three-part format above (Rationale, Diff, Evidence) exactly.
Do not write anywhere else. Do not run any other tool besides Read/Grep/Write.
"""

    subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--model",
            DISTILLER_MODEL,
            "--allowedTools",
            f"Read Grep Write({inbox_path})",
            "--disallowedTools",
            "Bash WebFetch WebSearch Edit",
            "--add-dir",
            str(vault_path),
        ],
        check=True,
        cwd=vault_path,
        timeout=180,
        capture_output=True,
        text=True,
    )


ADVANCE = {
    "flagged-job": _draft_flagged_job_summary,
    "undistilled-lessons": _draft_distillation,
}


def run() -> list[str]:
    vault_path = vault_io.get_vault_path()
    inbox_dir = vault_path / "modes" / "nightshift" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    pending = _existing_pending_slugs()
    staged_slugs = []

    for checker in SLACK_CHECKS.values():
        for item in checker():
            prefix = _identity_prefix(item)
            if any(existing.startswith(prefix) for existing in pending):
                continue  # already awaiting review, Scan re-derives but Stage stays idempotent

            slug = _slug_for(item)

            inbox_path = inbox_dir / f"{slug}.md"
            try:
                ADVANCE[item.kind](item, vault_path, inbox_path)
            except Exception as exc:
                # One failing/timing-out claude subprocess call (rate
                # limit, network blip) must not drop every other
                # independent item's proposal for the whole run -- found
                # in the 2026-07-21 ship-gate review, where this had no
                # exception handling at all.
                print(f"nightshift: advance failed for {slug} ({item.kind}): {exc}", file=sys.stderr)
                continue

            if not inbox_path.exists():
                continue  # advance failed to produce a draft -- stage nothing, no partial write

            rationale = _extract_rationale(inbox_path.read_text(encoding="utf-8"))
            if not rationale:
                inbox_path.unlink()  # malformed draft, doesn't meet the mandatory-rationale contract
                continue

            _stage(item, slug, rationale)
            staged_slugs.append(slug)

    return staged_slugs


def _extract_rationale(proposal_text: str) -> str | None:
    """The index entry's `rationale` duplicates the proposal file's
    `## Rationale` section verbatim (inbox/README.md) -- one canonical
    text, parsed rather than drafted twice.
    """
    lines = proposal_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower() == "## rationale":
            body_lines = []
            for follow in lines[i + 1 :]:
                if follow.startswith("##"):
                    break
                body_lines.append(follow)
            text = "\n".join(body_lines).strip()
            return text or None
    return None


def _stage(item: SlackItem, slug: str, rationale: str) -> None:
    state, content = vault_io.read_frontmatter(STATE_PATH)
    inbox = state.get("inbox", [])
    inbox.append(
        {
            "slug": slug,
            "origin_mode": item.mode,
            "description": item.description,
            "rationale": rationale,
            "confidence": None,
            "staged_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    state["inbox"] = inbox
    vault_io.write_frontmatter(STATE_PATH, state, content)


if __name__ == "__main__":
    slugs = run()
    if slugs:
        print(f"nightshift: staged {len(slugs)} item(s): {', '.join(slugs)}")
    else:
        print("nightshift: quiet night, nothing staged")
