"""What an interactive session needs, for the shell that hosts it in a PTY.

The Rust side owns the pseudo-terminal and knows nothing about modes; this
owns the mode and knows nothing about terminals. So the shell asks here for
the argv and gets back a list to hand `portable_pty`.

**It is deliberately not `driver.build_command`.** That builds a `-p` spawn:
`--output-format stream-json`, `--verbose`, a permission-prompt tool, a prompt
baked into the argv. An interactive session wants none of those -- it renders
itself, prompts for its own permissions, and reads what you type. Sharing one
function would mean a flag list with an `if interactive` running through it,
and the two genuinely differ more than they agree.

What they *do* share is the part that must not drift: the model per mode, the
methodology overlay, the subagent roster, the vault as a second allowed
directory, and the tracked permission policy. Those are imported, not copied.

See `PTY-MIGRATION.md`. This is step 1 of §7, and it runs beside the
orchestrator rather than replacing it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import vault_io
from orchestrator.driver import (
    MODE_MODELS,
    SHARED_SETTINGS,
    claude_binary,
    mcp_config,
)
from orchestrator.modes import mode_agents, mode_methodology

REPO_ROOT = Path(__file__).resolve().parent.parent
STATUSLINE = REPO_ROOT / "backend" / "scripts" / "statusline.sh"


def statusline_settings(port: int | None = None) -> dict:
    """The tracked policy plus a status line that reports back here.

    `statusLine` is how an interactive session hands over what the stream used
    to: the 5h and 7d windows, context occupancy, effort, the model, and the
    session's own id and transcript path. The CLI runs this command on every
    render and passes the payload on stdin, so the status bar stops depending
    on a turn being in flight to know anything.

    Composed rather than written to a file for the same reason
    `driver.settings_config` composes: the command needs an absolute path that
    cannot be committed.
    """
    policy = json.loads(SHARED_SETTINGS.read_text())
    policy["statusLine"] = {
        "type": "command",
        "command": f"bash {STATUSLINE} {port or os.environ.get('PORT', '8000')}",
    }
    return policy


def spawn_args(mode: str, cwd: str, resume_id: str | None = None) -> dict:
    """Everything the shell needs to open one interactive session.

    Returns the binary separately from the arguments because the Rust side
    resolves the binary itself when this cannot -- the same PATH problem
    `driver.claude_binary` exists for, in a second process.
    """
    if mode not in MODE_MODELS:
        raise ValueError(f"unknown mode {mode!r}")

    args: list[str] = ["--model", MODE_MODELS[mode]]

    # The mode, as text in the argv. Same mechanism as a `-p` spawn: it cannot
    # be raced by a second session of the same mode, and it switches
    # system-prompt snapshotting off so an edited methodology reaches a
    # resumed session.
    if methodology := mode_methodology(mode):
        args += ["--append-system-prompt", methodology]
    if agents := mode_agents(mode):
        args += ["--agents", agents]

    args += ["--mcp-config", mcp_config()]
    args += ["--settings", json.dumps(statusline_settings())]

    # The vault, always. A session sandboxed to its working directory cannot
    # read its own methodology, job context or lessons -- all of which live
    # outside it.
    if vault := vault_io.get_vault_path():
        args += ["--add-dir", str(vault)]

    if resume_id:
        args += ["--resume", resume_id]

    return {
        "binary": claude_binary(),
        "args": args,
        "cwd": cwd,
        "mode": mode,
        "model": MODE_MODELS[mode],
    }
