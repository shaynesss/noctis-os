#!/usr/bin/env python3
"""System-prompt composition — Noctis v2 Stage 1 item 7.

Composes `second-brain/prompts/system.md` plus a mode's overlay — and the
active job's context, when the session's working directory matches one —
into one text. There is no `CLAUDE_CONFIG_DIR` and no rendered file:
`interactive.py` passes the composed text in the argv
(`--append-system-prompt`), and `system.md` itself is what `~/.claude/CLAUDE.md`
links to. The regression runner composes the same way.

Until 2026-09-15 this module also carried `render()`, which wrote the
composed text to a per-mode config dir the 2026-09-12 cutover had removed,
and a banner at the top of every composed prompt saying the file was
"rewritten on every launch" with a timestamp. The Prompts panel's Save
called `render()` and got "config dir missing" five times per save; the
banner put a fresh timestamp at the head of every session's system prompt,
which is the one place a cacheable prefix must not change. Both are gone.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT = Path(os.environ.get("VAULT_PATH", REPO_ROOT.parent / "second-brain"))
PROMPTS = VAULT / "prompts"

MODES = ("general", "faber", "noctua", "vesper", "maintenance")


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
        system.rstrip(),
        "\n---\n",
        overlay_path.read_text().rstrip(),
    ]
    if job_context:
        parts += ["\n---\n", "## This session's job\n", job_context.rstrip()]
    return "\n".join(parts) + "\n"
