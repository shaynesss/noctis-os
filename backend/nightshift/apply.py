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


def _old_and_new_blocks(diff_text: str) -> tuple[str, str]:
    old_lines, new_lines = [], []
    for line in diff_text.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("-"):
            old_lines.append(_strip_marker(line))
        elif line.startswith("+"):
            new_lines.append(_strip_marker(line))
    return "\n".join(old_lines), "\n".join(new_lines)


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

    old_block, new_block = _old_and_new_blocks(diff_text)
    if not old_block:
        raise DiffApplyError("diff has no removed lines to anchor the replacement")

    current = vault_io.read_file(target)
    count = current.count(old_block)
    if count == 0:
        raise DiffApplyError(f"old text not found in {target} -- proposal may be stale")
    if count > 1:
        raise DiffApplyError(f"old text found {count} times in {target} -- ambiguous, refusing to guess")

    vault_io.write_file(target, current.replace(old_block, new_block, 1))
    return target


_CURSOR_MARKER = re.compile(r"<!--\s*cursor-advance:\s*(\S+)=(\d+)\s*-->")


def parse_cursor_advance(proposal_text: str) -> tuple[str, int] | None:
    """A distillation proposal (runner.py's _draft_distillation) leaves a
    machine-readable marker recording which mode's lessons_distilled_through
    cursor to advance and to what line count -- computed deterministically
    at draft time, not re-derived from the slug (kind/slug_hint aren't a
    reliable place to recover this: check_settings builds slug_hint as
    f"undistilled-{mode}", and reconstructing "mode" by string-splitting
    the final slug back apart is exactly the fragile parsing this avoids).
    """
    match = _CURSOR_MARKER.search(proposal_text)
    if not match:
        return None
    return match.group(1), int(match.group(2))


def advance_lessons_cursor(mode: str, through: int) -> None:
    state, content = vault_io.read_frontmatter("modes/settings/state.md")
    cursor = state.get("lessons_distilled_through", {}) or {}
    cursor[mode] = through
    state["lessons_distilled_through"] = cursor
    vault_io.write_frontmatter("modes/settings/state.md", state, content)
