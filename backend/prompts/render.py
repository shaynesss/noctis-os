#!/usr/bin/env python3
"""System-prompt renderer — Noctis v2 Stage 1 item 7.

Composes `second-brain/prompts/system.md` plus a mode's overlay — and the
active job's context, when the session's working directory matches one —
into one text. There is no `CLAUDE_CONFIG_DIR` and no rendered file any
more: `interactive.py` passes the composed text in the argv
(`--append-system-prompt`), and `system.md` itself is what `~/.claude/CLAUDE.md`
links to. `render()`'s file output survives for the regression suite and the
Prompts panel's check.

This docstring asserted that caller for a long time while the only one was
the Prompts panel's Save button, and the generated banner said the same.
A docstring naming a caller that does not exist is worse than none, because
it reads as verification. Both are true now, and `tests/test_prompts.py`
pins the launch path to calling it.

    python3 backend/prompts/render.py            # render every mode
    python3 backend/prompts/render.py faber      # one mode
    python3 backend/prompts/render.py --check    # verify without writing

**The config dir itself is never created here.** Claude Code keys
credentials to the config-dir path in the macOS Keychain, so a directory
this script invented would be unauthenticated and every launch into it
would fail with "Not logged in". Directories are created once by
`bootstrap/`, logged into once by hand, and only their CLAUDE.md is
rewritten per launch. Rendering into a missing directory is an error, not
something to paper over by creating one.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT = Path(os.environ.get("VAULT_PATH", REPO_ROOT.parent / "second-brain"))
PROMPTS = VAULT / "prompts"
CONFIG_ROOT = REPO_ROOT / "backend" / "launch_config"

MODES = ("general", "faber", "noctua", "vesper", "maintenance")

BANNER = """<!-- GENERATED — do not edit.
     Rewritten on every launch by backend/prompts/render.py from
     second-brain/prompts/system.md + prompts/overlays/{mode}.md.
     Edit those, not this. Rendered {when}. -->
"""


def compose(mode: str, job_context: str | None = None) -> str:
    """Base prompt, then the mode overlay, then this launch's job context.

    Order is deliberate: the stable half sits first so it stays a cacheable
    prefix across launches, and the volatile half (job context, which
    changes every time) sits last. Reversing it would invalidate the prompt
    cache on every launch, and cache reads are the bulk of an orchestrated
    workload's token usage.
    """
    system = (PROMPTS / "system.md").read_text()
    overlay_path = PROMPTS / "overlays" / f"{mode}.md"
    if not overlay_path.exists():
        raise FileNotFoundError(f"no overlay for mode '{mode}': {overlay_path}")

    parts = [
        BANNER.format(mode=mode, when=datetime.now(timezone.utc).isoformat(timespec="seconds")),
        system.rstrip(),
        "\n---\n",
        overlay_path.read_text().rstrip(),
    ]
    if job_context:
        parts += ["\n---\n", "## This session's job\n", job_context.rstrip()]
    return "\n".join(parts) + "\n"


def render(mode: str, job_context: str | None = None, check: bool = False) -> tuple[bool, str]:
    """Returns (changed, message). `check` reports without writing."""
    target_dir = CONFIG_ROOT / mode
    if not target_dir.is_dir():
        return False, f"config dir missing: {target_dir} — run ./bootstrap/bootstrap.sh"

    content = compose(mode, job_context)
    target = target_dir / "CLAUDE.md"

    # Compare ignoring the banner's timestamp, so an unchanged prompt does
    # not report as changed on every call.
    def body(t: str) -> str:
        return t.split("-->", 1)[-1] if t.startswith("<!--") else t

    if target.exists() and body(target.read_text()) == body(content):
        return False, f"{mode}: unchanged"
    if check:
        return True, f"{mode}: WOULD CHANGE"
    target.write_text(content)
    return True, f"{mode}: rendered ({len(content)} chars)"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    check = "--check" in sys.argv
    modes = args or list(MODES)

    failed = False
    for mode in modes:
        if mode not in MODES:
            print(f"  unknown mode: {mode}", file=sys.stderr)
            failed = True
            continue
        try:
            _, msg = render(mode, check=check)
            print(f"  {msg}")
        except FileNotFoundError as e:
            print(f"  {mode}: {e}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
