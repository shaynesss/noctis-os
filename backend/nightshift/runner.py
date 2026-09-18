"""Nightshift's Scan -> Advance -> Stage loop (nightshift.md section 2),
the launchd entrypoint's actual logic (scripts/nightshift_run.sh just
invokes this). Propose-never-commit: writes only to
maintenance/inbox/<slug>.md and the mirrored index entry in
maintenance/state.md -- nothing else in the vault, ever.
"""

import json
import os
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
from jobs import MAINTENANCE_INBOX, MAINTENANCE_STATE, lessons_path  # noqa: E402
from nightshift.apply import _section  # noqa: E402
from nightshift.slack_surface import SLACK_CHECKS, SlackItem  # noqa: E402
import staleness  # noqa: E402

STATE_PATH = MAINTENANCE_STATE
# Cheapest/fastest current Claude tier, for mechanical distillation work
# (dev.md: "effort routing expressed as model routing"). Env-overridable so
# a smaller/newer tier can be adopted without a code change when one ships --
# a literal never gets revisited on its own.
DISTILLER_MODEL = os.environ.get("NIGHTSHIFT_DISTILLER_MODEL", "claude-haiku-4-5")


# Where a draft that failed the inbox contract is kept instead of deleted.
# Runtime, not vault: it is a machine artefact, high-churn and gitignored,
# the same rule the action logs follow.
DROPS_DIR = Path(__file__).resolve().parents[1] / "runtime" / "nightshift-drops"

# Why a draft never reached the inbox. Three gates, each a real contract from
# `maintenance/inbox/README.md`, and until 2026-09-17 all three were a bare
# `continue`: the item counted in `seen`, never appeared in `staged`, never
# appeared in `failed`, and the night reported itself quiet. `data/nightshift.json`
# has `seen: 3, staged: 0, failed: 0` for 2026-09-16 and the same shape for
# 09-17, which is three distiller calls a night, paid for, discarded, unlogged.
# **Three gates, and deliberately not a fourth (2026-09-18).** A draft whose
# diff does not match its target could be caught here, at 03:00, instead of
# surfacing in the morning as a proposal that can only be rejected -- the
# first restage of the maintenance item was exactly that. It is staged
# anyway, on Shayne's call: a dead proposal is readable, sits in the Inbox
# with the route's own reason under it, and can be judged on its argument;
# a drop is a line in a record and a file in `runtime/`, which is strictly
# less. The gates below reject drafts that are not proposals at all. Whether
# a proposal is *right* is the review's job, and a diff that no longer
# applies is a question about the proposal, not about the draft.
GATES = {
    "no-draft": "the drafter returned nothing",
    "no-rationale": "the draft has no `## Rationale` section",
    "no-confidence": "the draft's `## Confidence` is missing or is not high/low",
}


def _drop(dropped: list[dict], item: SlackItem, slug: str, gate: str,
          draft: str | None) -> None:
    """Record a draft that did not make it, and keep it if there is one.

    Deleting the evidence is what made this invisible twice over: the gate
    was silent *and* the artefact it rejected was unlinked, so the next
    morning had neither a reason nor a draft to read. The text goes to
    `runtime/nightshift-drops/` instead, where it can be opened.

    It is text rather than a file from 2026-09-18: a rejected draft never
    reaches the inbox at all now, because the drafter hands its work back
    and the runner is what writes.
    """
    kept: str | None = None
    if draft and draft.strip():
        DROPS_DIR.mkdir(parents=True, exist_ok=True)
        target = DROPS_DIR / f"{slug}.md"
        target.write_text(draft, encoding="utf-8")
        kept = str(target)
    dropped.append({"slug": slug, "kind": item.kind, "gate": gate, "kept": kept})
    print(f"nightshift: dropped {slug} ({gate}: {GATES[gate]})"
          + (f"; draft kept at {kept}" if kept else ""), file=sys.stderr)


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


def _draft_distillation(item: SlackItem, vault_path: Path) -> str:
    """Maintenance's slack surface genuinely needs judgment (identify a
    recurring pattern, draft a diff candidate) -- borrows maintenance's own
    distiller subagent at reduced permission: read-only over the vault, no
    write tool at all, no bash, no network.

    **The drafter returns the proposal; the runner writes it (2026-09-18).**
    It used to be handed a `Write` scoped to one path, and every such draft
    since the machine started working was thrown away: any parenthesised
    specifier on `Write` in `--allowedTools` is refused, so the model did
    the reading, found the pattern, wrote a correct four-part proposal and
    was denied at the last step. `Write(/abs/path.md)`, `Write(//abs)`,
    `Write(rel/path.md)` and `Write(dir/**)` were all measured; only a bare
    `Write` is honoured, and a bare `Write` on an unattended nightly job is
    the whole vault. Handing the text back needs no write permission and is
    what `maintenance/agents/distiller.md` says this subagent is: read-only.

    Methodology and agent definition moved to maintenance/ on 2026-09-07
    (Noctis v2 Stage 1 item 3). State -- the inbox, its index, the archive --
    deliberately did not move yet, so every other path here is unchanged.
    """
    methodology = vault_io.read_file("maintenance/schedule.md")
    agent_def = vault_io.read_file("maintenance/agents/distiller.md")
    readme = vault_io.read_file(f"{MAINTENANCE_INBOX}/README.md")

    prompt = f"""{methodology}

---

You are the maintenance sweep's Advance step for this run, borrowing the
distiller subagent at reduced permission (drafts only, never writes to a
live mode file):

{agent_def}

---

Required proposal format:

{readme}

---

Task: {item.context}. Read the relevant lessons.md file(s) under modes/,
identify the specific pattern, and draft ONE proposal.

Return that proposal as your final message and nothing else: start at
`## Rationale`, no preamble, no sign-off, no code fence around it. You have
no write tool and nothing to save it to -- your answer *is* the file, and
the sweep writes it where it belongs.
Follow the four-part format above (Rationale, Diff, Evidence, Confidence)
exactly.

How your diff will be applied, because it decides whether the proposal
survives: the ` ` context lines and `-` removed lines of each `@@` hunk are
joined into one block and searched for in the target file as an exact
string, which must be found exactly once. So copy every context line
verbatim from the file you read, in file order, with no line left out --
quoting the first bullet of a list and then jumping to the next heading
makes a block that appears nowhere. Keep the context tight, two or three
lines either side is plenty, and a blank line you are *adding* is a `+`
line, not a context line. If you cannot quote the surrounding lines exactly,
say so in the Rationale and give no diff rather than an approximate one.

For Confidence: write "high" if multiple independent lessons
entries clearly support the same pattern, or "low" if you're inferring
from a single entry or a weaker signal -- then one sentence on why. This
is a genuine self-assessment, not a formality; judge it honestly.
Read and Grep are the only tools you have; do not attempt any other.
"""

    result = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--model",
            DISTILLER_MODEL,
            "--allowedTools",
            "Read Grep",
            "--disallowedTools",
            "Bash WebFetch WebSearch Edit Write",
            "--add-dir",
            str(vault_path),
        ],
        check=True,
        cwd=vault_path,
        timeout=180,
        capture_output=True,
        text=True,
        # Otherwise every call waits three seconds for a stdin that is
        # never coming ("no stdin data received in 3s, proceeding without
        # it"), three times a night for nothing.
        stdin=subprocess.DEVNULL,
    )

    draft = _result_text(result)

    if draft and item.slug_hint.startswith("undistilled-"):
        # Records which mode's lessons_distilled_through cursor to advance
        # on accept, and to what -- computed here (deterministic, draft
        # time), not re-derived later from the slug at accept time (see
        # apply.py's parse_cursor_advance for why that would be fragile).
        target_mode = item.slug_hint.removeprefix("undistilled-")
        # `lessons_path`, not an f-string: maintenance's lessons live at
        # `maintenance/lessons.md`, outside `modes/`, and this hardcoded the
        # wrong shape. Any maintenance draft that got this far raised
        # FileNotFoundError here and was recorded as a failure of the whole
        # item (found 2026-09-17, while making the drop gates speak).
        line_count = len(vault_io.read_file(lessons_path(target_mode)).splitlines())
        draft += f"\n<!-- cursor-advance: {target_mode}={line_count} -->\n"

    return draft


def _result_text(result: subprocess.CompletedProcess) -> str:
    """The proposal, out of `--output-format json`'s envelope.

    The envelope is read rather than thrown away because throwing it away
    is what hid the permission bug above for three nights. `stdout` carried
    `permission_denials` every one of those nights, naming the tool and the
    exact path it was refused, and `capture_output=True` with nothing
    reading the result discarded it; the night saw only a missing file and
    called it `no-draft`, which is true and useless.

    A drafter that comes back with nothing usable raises, so the run records
    a failure *with its reason* rather than an empty draft with none. An
    identical raise across every item is what `report.record` reads as a
    broken machine rather than a quiet night.
    """
    try:
        payload = json.loads(result.stdout or "")
    except ValueError:
        raise RuntimeError(
            f"drafter output was not JSON: {(result.stdout or result.stderr or '')[:200]}"
        ) from None

    if payload.get("is_error"):
        # Checked before the text, because on an error the text *is* the
        # error ("ran out of turns"), and a proposal file is the last place
        # that should end up.
        raise RuntimeError(f"drafter errored: {str(payload.get('result'))[:200]}")

    body = _proposal_body(payload.get("result") or "")
    if body:
        return body

    # Checked after the text, the other way round: a denial the model worked
    # around and still answered correctly is not worth throwing a good draft
    # away for. A denial that left nothing behind is exactly the bug above.
    denied = sorted({d.get("tool_name", "?") for d in payload.get("permission_denials") or []})
    if denied:
        raise RuntimeError(f"drafter was denied {', '.join(denied)} and returned nothing")
    return ""


def _proposal_body(text: str) -> str:
    """The proposal file's content, out of whatever the model wrapped it in.

    Two liberties, both one-directional: a fenced block is unwrapped, and
    anything before the first `## Rationale` is cut. A model told to answer
    with a file still sometimes says "Here is the proposal:" first, and that
    line would otherwise be the first line of a vault file for good. Nothing
    is added, nothing is reordered, and a draft with no `## Rationale` at all
    comes back whole -- for the gate to reject and the drops folder to keep,
    which is the only way the morning can see what went wrong.
    """
    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if len(lines) > 1 and lines[-1].strip() == "```":
            body = "\n".join(lines[1:-1]).strip()
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower() == "## rationale":
            body = "\n".join(lines[i:]).strip()
            break
    return body + "\n" if body else ""


# What a kind of slack turns into: `(item, vault_path) -> str`, the proposal's
# text. A drafter does not write -- see `_draft_distillation`. `flagged-job` was
# here until 2026-09-17:
# it drafted a status note about a flagged job that proposed nothing, sat
# beside the same job in the Inbox's flagged list, and came back the night
# after it was accepted. The flag itself is the item; the Inbox shows it.
ADVANCE = {
    "undistilled-lessons": _draft_distillation,
}

# Kinds whose drafter is a template rather than a judgment.
MECHANICAL_KINDS: frozenset[str] = frozenset()


def run() -> tuple[list[str], list[dict], list[dict], int]:
    """Scan -> Advance -> Stage. Returns (staged, failures, drops, seen).

    Failures are returned, not only printed: from 2026-08-05 to 09-15 every
    night's advance step failed identically ("No such file or directory:
    'claude'" -- launchd's PATH) and this loop, correctly refusing to let one
    item's failure drop the rest, printed each one to a log and ended the
    night as quiet. The caller records them, so identical failure across
    every item is a broken machine and reported as one.

    **Drops are the same lesson learned a second time.** An item can also
    reach Advance, cost a real model call, and then be discarded by one of
    three contract gates without being a failure at all -- which meant it
    was counted in `seen`, absent from `staged`, absent from `failed`, and
    the night called itself quiet. `seen: 3, staged: 0, failed: 0` is what
    2026-09-16 recorded, and it was three distiller runs thrown away. Drops
    are returned for the same reason failures are, and the rejected draft is
    kept rather than deleted, so the reason and the artefact both survive to
    the morning.

    **And a third time, on 2026-09-18.** Every distillation draft since the
    machine started working was denied at its `Write` and discarded as
    `no-draft`: the reason sat in the drafter's own JSON output, which was
    captured and never read. Advance hands its text back now and the gates
    run against that, so a proposal reaches `inbox/` only by passing them,
    and a rejected one never lands where the app lists proposals at all."""
    vault_path = vault_io.get_vault_path()
    # Where Settings reads. Drafts went to modes/nightshift/inbox/ until
    # 2026-09-16, a path the app stopped reading at the cutover, so a night's
    # proposal could be indexed and never shown.
    inbox_dir = vault_path / MAINTENANCE_INBOX
    inbox_dir.mkdir(parents=True, exist_ok=True)
    # First, the deterministic half: mark the jobs whose session died
    # mid-build, so the dev scan below has something to find. Nothing else
    # calls this since v1's poll went.
    for folder, slugs in staleness.flag_pass().items():
        for slug in slugs:
            print(f"nightshift: flagged {folder}/{slug} as stale", file=sys.stderr)
    pending = _existing_pending_slugs()
    staged_slugs = []
    failed: list[dict] = []
    dropped: list[dict] = []
    seen = 0

    for checker in SLACK_CHECKS.values():
        for item in checker():
            prefix = _identity_prefix(item)
            if any(existing.startswith(prefix) for existing in pending):
                continue  # already awaiting review, Scan re-derives but Stage stays idempotent

            slug = _slug_for(item)
            seen += 1

            try:
                draft = ADVANCE[item.kind](item, vault_path)
            except Exception as exc:
                # One failing/timing-out claude subprocess call (rate
                # limit, network blip) must not drop every other
                # independent item's proposal for the whole run -- found
                # in the 2026-07-21 ship-gate review, where this had no
                # exception handling at all.
                print(f"nightshift: advance failed for {slug} ({item.kind}): {exc}", file=sys.stderr)
                failed.append({"slug": slug, "kind": item.kind, "error": str(exc)[:200]})
                continue

            if not (draft or "").strip():
                # Advance produced no proposal. Nothing to keep, but the fact
                # is recorded: a night that silently stages nothing is the one
                # failure this whole record exists to make visible.
                _drop(dropped, item, slug, "no-draft", None)
                continue

            rationale = _extract_rationale(draft)
            if not rationale:
                _drop(dropped, item, slug, "no-rationale", draft)
                continue

            confidence = _confidence_for(item, draft)
            if not confidence:
                _drop(dropped, item, slug, "no-confidence", draft)
                continue

            # Past the gates, so this is a proposal. The file and its index
            # entry are written together or the file sits invisible
            # (inbox/README.md), and the runner owns both writes.
            (inbox_dir / f"{slug}.md").write_text(draft, encoding="utf-8")
            _stage(item, slug, rationale, confidence)
            staged_slugs.append(slug)

    return staged_slugs, failed, dropped, seen


def _extract_rationale(proposal_text: str) -> str | None:
    """The index entry's `rationale` duplicates the proposal file's
    `## Rationale` section verbatim (inbox/README.md) -- one canonical
    text, parsed rather than drafted twice."""
    return _section(proposal_text, "## rationale") or None


def _extract_confidence(proposal_text: str) -> str | None:
    """Reads the distiller's own self-assessment back out of its `##
    Confidence` section (inbox/README.md's fourth, judgment-only section).
    First word must be high/low -- anything else is a malformed draft.
    """
    body = _section(proposal_text, "## confidence") or ""
    word = body.split()[:1]
    return word[0].lower() if word and word[0].lower() in ("high", "low") else None


def _confidence_for(item: SlackItem, proposal_text: str) -> str | None:
    """A drafter that makes no judgment call is not asked for one.

    Distillation genuinely involves judgment (finding a pattern across
    lessons entries), so its confidence is a real self-assessment parsed out
    of the proposal. A mechanical, templated drafter is `high` by
    construction: there is nothing for it to be unsure about. None is
    registered today; the branch stays because the contract is per kind,
    not per drafter that happens to exist.
    """
    if item.kind in MECHANICAL_KINDS:
        return "high"
    return _extract_confidence(proposal_text)


def _stage(item: SlackItem, slug: str, rationale: str, confidence: str) -> None:
    state, content = vault_io.read_frontmatter(STATE_PATH)
    inbox = state.get("inbox", [])
    inbox.append(
        {
            "slug": slug,
            "origin_mode": item.mode,
            "description": item.description,
            "rationale": rationale,
            "confidence": confidence,
            "staged_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    state["inbox"] = inbox
    vault_io.write_frontmatter(STATE_PATH, state, content)


if __name__ == "__main__":
    from nightshift import report

    slugs, failed, dropped, seen = run()
    entry = report.record(slugs, failed, dropped, seen)
    if entry["error"]:
        # Every item failed the same way: not a quiet night, a broken one.
        # Said so, and exited non-zero, so launchd's log and Settings'
        # Maintenance section both carry it. Six weeks of "quiet night"
        # hid exactly this.
        print(f"nightshift: FAILED -- every advance failed: {entry['error']}", file=sys.stderr)
        sys.exit(2)
    if slugs:
        print(f"nightshift: staged {len(slugs)} item(s): {', '.join(slugs)}")
    elif failed:
        print(f"nightshift: nothing staged; {len(failed)} of {seen} item(s) failed (see above)")
    else:
        print("nightshift: quiet night, nothing staged")
