"""Apply + verify's Apply half (settings.md stage 3): "the interface
performs a deterministic git-diff apply (backend code, not session
judgment)" on accept. Tolerant of the inbox proposal format's simplified
diff shape (inbox/README.md's worked example has no line numbers) -- this
is not a general unified-diff/patch implementation, it's a literal
find-the-old-block-and-replace-it applier, deliberately refusing to guess
when the match isn't unique.

Writes the target file only -- does NOT run `git commit` in the vault, even
though settings.md's stage-3 text says "and commits." Caught by the
2026-07-21 ship-gate review as a stale/aspirational claim in this
docstring, not a regression: the commit half was never actually built.
Flagged in STATUS.md as a real follow-up rather than rushed in here.
"""

import re
from datetime import datetime, timezone

import vault_io


class DiffApplyError(Exception):
    pass


def _section(proposal_text: str, heading: str) -> str | None:
    lines = proposal_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower() == heading:
            body = []
            for follow in lines[i + 1 :]:
                if follow.startswith("##"):
                    break
                body.append(follow)
            return "\n".join(body).strip()
    return None


def _strip_marker(line: str) -> str:
    rest = line[1:]
    return rest[1:] if rest.startswith(" ") else rest


def _old_and_new_blocks(hunk_text: str) -> tuple[str, str]:
    """Context lines (leading-space, unified-diff convention) anchor the
    match on both sides -- a pure-insertion hunk (no removed lines, just a
    context line followed by `+` additions) has nothing else to anchor on.
    Previously only `+`/`-` lines were handled, so a context-only anchor
    was silently dropped and any insertion-only proposal raised "no
    removed lines to anchor the replacement" instead of applying.
    """
    old_lines, new_lines = [], []
    for line in hunk_text.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("-"):
            old_lines.append(_strip_marker(line))
        elif line.startswith("+"):
            new_lines.append(_strip_marker(line))
        else:
            context = _strip_marker(line) if line.startswith(" ") else line
            old_lines.append(context)
            new_lines.append(context)
    return "\n".join(old_lines), "\n".join(new_lines)


def _hunks(diff_text: str) -> list[str]:
    """Splits a diff's body on `@@` hunk markers. A proposal touching two
    separate spots in the same file (research.md's Stage-2 list entry and
    its Stage-3 prose, in one real proposal) produces two `@@` hunks --
    flattening them into a single old/new block (the pre-fix behavior)
    concatenates non-adjacent text that never appears contiguously in the
    target file, so `apply_proposal` always raised "old text not found"
    for any multi-hunk diff. One hunk's old/new block must stay separate
    from the next.
    """
    hunks: list[str] = []
    current: list[str] = []
    started = False
    for line in diff_text.splitlines():
        if line.startswith("@@"):
            if started:
                hunks.append("\n".join(current))
            current = []
            started = True
            continue
        if started:
            current.append(line)
    if started:
        hunks.append("\n".join(current))
    return hunks


def apply_proposal(proposal_text: str) -> str | None:
    """Returns the target file path if a diff was applied, or None if the
    proposal had no diff to apply (e.g. dev's flagged-job status notes,
    which never propose code/branch changes -- see runner.py's
    _draft_flagged_job_summary). Raises DiffApplyError rather than
    guessing when a diff exists but can't be applied unambiguously.
    """
    diff_text = _section(proposal_text, "## diff")
    if not diff_text or diff_text.lower().startswith("(none"):
        return None

    match = re.search(r"^--- (\S+)", diff_text, re.MULTILINE)
    if not match:
        raise DiffApplyError("diff section has no '--- <path>' target file header")
    target = match.group(1)

    hunks = _hunks(diff_text)
    if not hunks:
        raise DiffApplyError("diff has no '@@' hunks to apply")

    current = vault_io.read_file(target)
    for hunk_text in hunks:
        old_block, new_block = _old_and_new_blocks(hunk_text)
        if not old_block:
            raise DiffApplyError("diff has no removed lines to anchor the replacement")

        count = current.count(old_block)
        if count == 0:
            raise DiffApplyError(f"old text not found in {target} -- proposal may be stale")
        if count > 1:
            raise DiffApplyError(f"old text found {count} times in {target} -- ambiguous, refusing to guess")

        current = current.replace(old_block, new_block, 1)

    # Only written once every hunk has validated cleanly -- a later hunk's
    # failure must not leave an earlier hunk's change partially applied.
    vault_io.write_file(target, current)
    return target


_CURSOR_MARKER = re.compile(r"<!--\s*cursor-advance:\s*(\S+)=(\d+)\s*-->")


def parse_cursor_advance(proposal_text: str) -> str | None:
    """A distillation proposal (runner.py's _draft_distillation) leaves a
    machine-readable marker naming which mode's lessons_distilled_through
    cursor to advance -- not re-derived from the slug (kind/slug_hint aren't
    a reliable place to recover this: check_settings builds slug_hint as
    f"undistilled-{mode}", and reconstructing "mode" by string-splitting
    the final slug back apart is exactly the fragile parsing this avoids).

    Only the mode name is trusted from the marker -- the line-count half
    (still written for human readability, e.g. "settings=19") is deliberately
    ignored. Found 2026-07-22: a session-close append to a mode's own
    lessons.md happens *after* a proposal's cursor value is drafted, so any
    number a session types into the marker is stale by construction the
    moment it writes its own closing retro. Advancing to a session-supplied
    number reproduced this every time; advancing to the live line count at
    accept time (see advance_lessons_cursor below) cannot be stale, since
    accept always happens after every write that could still be pending.
    """
    match = _CURSOR_MARKER.search(proposal_text)
    if not match:
        return None
    return match.group(1)


def advance_lessons_cursor(mode: str) -> None:
    """Sets the cursor to the target mode's lessons.md live line count at
    accept time, not to a number carried in the proposal -- see
    parse_cursor_advance's docstring for why a session-supplied number is
    structurally unreliable here. Same self-heal pattern as triggers.py
    computing badges live instead of trusting stored state.
    """
    lessons_path = f"modes/{mode}/lessons.md"
    through = len(vault_io.read_file(lessons_path).splitlines()) if vault_io.file_exists(lessons_path) else 0

    state, content = vault_io.read_frontmatter("modes/settings/state.md")
    cursor = state.get("lessons_distilled_through", {}) or {}
    cursor[mode] = through
    state["lessons_distilled_through"] = cursor
    vault_io.write_frontmatter("modes/settings/state.md", state, content)


_JOB_ORIGIN_MARKER = re.compile(r"<!--\s*job-origin:\s*([\w-]+)/([\w-]+)\s*-->")


def parse_job_origin(proposal_text: str) -> tuple[str, str] | None:
    """A proposal staged on behalf of a live job (settings.md's Propose
    stage: "address the trigger" sessions, not nightshift's own automatic
    distiller run, which has no job to link back to) leaves a
    machine-readable marker recording which job to close once this
    proposal is accepted -- same shape as `parse_cursor_advance` above.
    """
    match = _JOB_ORIGIN_MARKER.search(proposal_text)
    if not match:
        return None
    return match.group(1), match.group(2)


def close_job(mode: str, slug: str, resolution: str) -> None:
    """Collapses what settings.md's Apply + verify stage used to defer to
    "the next settings session" into the same deterministic accept action
    as the diff apply and cursor advance above -- confirming a
    deterministic write landed is not a judgment call, so no session needs
    re-launching just to close the job out. Found 2026-07-22: the deferred
    design left a resolved job visibly stuck on Custos's card (still
    "awaiting accept" after the accept had already happened) until some
    future session happened to re-audit it.

    Marks the job `Done` in both its own context.md and the mode's
    `state.md` jobs list -- kept visible (not removed) so the card shows
    the resolution rather than the job just vanishing with no confirmation
    it actually passed. The frontend collapses Done rows to a single line
    (ProfileOverlay.tsx's JobRow) so this doesn't pile up as clutter.
    """
    job_path = f"modes/{mode}/jobs/{slug}/context.md"
    if vault_io.file_exists(job_path):
        job_meta, job_content = vault_io.read_frontmatter(job_path)
        job_meta["stage"] = "Done"
        job_meta["status"] = resolution
        job_meta["last_touched"] = datetime.now(timezone.utc).isoformat()
        vault_io.write_frontmatter(job_path, job_meta, job_content)

    state_path = f"modes/{mode}/state.md"
    state_meta, state_content = vault_io.read_frontmatter(state_path)
    jobs = state_meta.get("jobs", []) or []
    for job in jobs:
        if job.get("slug") == slug:
            job["stage"] = "Done"
            job["status"] = resolution
            job["last_touched"] = datetime.now(timezone.utc).isoformat()
            break
    state_meta["jobs"] = jobs
    vault_io.write_frontmatter(state_path, state_meta, state_content)
