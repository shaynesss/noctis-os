"""The engine: where `claude` is, what it runs as, and one-shot calls to it.

This is what survives of `orchestrator/driver.py`. The driver built `-p`
spawns and streamed their events -- the conversation surface Noctis has
replaced with a real interactive session in a terminal (PTY-MIGRATION.md).
What it also held, and what everything else in the backend actually
depended on, was not the spawn at all: the mode -> model table, the tool
allowlist, the tracked permission policy, the MCP config, the binary lookup,
and a one-shot call for summarising text. Those are here, verbatim where the
reasoning still holds, so that deleting the orchestrator deletes the
orchestrator and nothing else.

`one_shot` is the one place `-p` remains, and it is the right use of it: a
scripting mode used for a script. It summarises text it is handed, on the
cheap tier, with every tool refused.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

MODE_MODELS = {
    "general": "claude-opus-5",
    "faber": "claude-opus-5",
    "noctua": "claude-opus-5",
    "vesper": "claude-opus-5",
    "maintenance": "claude-haiku-4-5",
}

# Tool policy, identical for every mode.
#
# **There is deliberately no per-mode cage.** Modes used to differ here --
# maintenance and the research modes had Bash, Edit and Write disallowed,
# general had Edit and Write -- and that was the wrong axis to vary on. What
# makes Noctua research and Faber build is the methodology each one reads.
# Varying *capability* on top of that produced a mode handed a task it could
# not perform and with no way to say so. Methodology is the difference
# between the modes. Permission is not.
#
# In an interactive session the CLI prompts for anything not listed here,
# in its own terminal, which is where a person is looking. The list is what
# skips the question entirely.
ALL_TOOLS = (
    "Read Grep Glob WebSearch WebFetch Edit Write Bash "
    "NotebookEdit TodoWrite Task "
    # Noctis's own retrieval, pre-approved: a session asking permission to
    # search the vault is asking permission to do the thing the design is
    # built around. `propose` is deliberately absent -- that one writes, and
    # it is Custos's, so it keeps asking.
    "mcp__noctis__vault_search mcp__noctis__history_search "
    "mcp__noctis__job_context mcp__noctis__worklist"
)

# What a session can be started on, and what each is for. The mode's own
# entry in MODE_MODELS is the default; this is the menu when you want
# something else for one session -- dev.md's "effort routing expressed as
# model routing". A mode is its methodology, not its model.
#
# It had no readers between the Settings models table being removed and the
# launcher gaining its chooser (2026-09-17), which is why Fable was missing
# from it. Listed rather than passed through: an id the engine does not know
# is rejected after the terminal has painted, and the error lands where a
# session should be.
MODEL_CATALOG: list[dict[str, str]] = [
    {"id": "claude-opus-5", "name": "Opus 5",
     "blurb": "Best for everyday, complex tasks"},
    {"id": "claude-fable-5-1", "name": "Fable 5.1",
     "blurb": "Deepest reasoning, on usage credits"},
    {"id": "claude-sonnet-5", "name": "Sonnet 5",
     "blurb": "Efficient for routine tasks"},
    {"id": "claude-haiku-4-5", "name": "Haiku 4.5",
     "blurb": "Fastest for quick answers"},
]

# The ids alone, for validating what the launcher sends.
MODELS = tuple(m["id"] for m in MODEL_CATALOG)

MODE_TOOLS: dict[str, dict[str, str]] = {
    # The same entry for every mode, by construction rather than by five
    # copies that could drift apart. The dict shape is kept because the
    # panels router reports it to the interface, and because reintroducing a
    # per-mode difference should have to be written on purpose rather than
    # inherited from a default nobody revisited.
    mode: {"allowed": ALL_TOOLS} for mode in MODE_MODELS
}

# How hard the engine thinks. Passed at spawn as `--effort`; dev.md has asked
# for this routing since it was written ("default high; medium/low for
# mechanical or repetitive work; xhigh for genuine deep exploration"). `max`
# is left out of the cycle -- real, settable, but not something to land on
# by tapping a key.
EFFORT_CYCLE = ("low", "medium", "high", "xhigh")

# The permission modes a session can run in, in escalating order of what it
# may do without asking. Still a fact about the engine after the migration:
# an interactive session has one too, and Shift+Tab in its own TUI cycles
# it. bypassPermissions is deliberately NOT here -- real, settable, but not
# something reachable by tapping a key.
PERMISSION_CYCLE = ("plan", "manual", "acceptEdits", "auto")

# The Noctis MCP server, attached to every session. Dependency-free by
# design, so the interpreter running the backend can run it directly and
# there is nothing to install.
MCP_SERVER = REPO_ROOT / "backend" / "mcp" / "server.py"

# Permissions, shared by every mode and tracked in git.
#
# **Bash is allowed whole, not command by command.** It used to be a curated
# list, which meant every ordinary thing outside it hit a prompt, and the
# list could only ever be as complete as the last time someone remembered to
# extend it. A mode is not defined by what it cannot do.
#
# **git push is denied, not merely absent.** dev.md's "commits as work
# progresses, Shayne pushes" was a rule in a markdown file that a session
# could simply fail to follow; here it is a fact about what the process may
# do. The scheduler's vault push is backend Python calling git directly, so
# it is unaffected.
#
# **crossSessionInbound is set rather than left to fall out.** Checked in the
# installed engine: the key is an optional enum of accept/hold/refuse that
# catches to undefined, so an unrecognised value degrades to holding and
# cannot take the deny rule down with it. What it costs is an unattended
# write path into a session with every tool pre-approved -- bounded by the
# socket, which is 0700/0600, so a sender is already running as this user.
SHARED_SETTINGS = REPO_ROOT / "backend" / "orchestrator" / "permissions.json"


def mcp_config() -> str:
    """--mcp-config takes a JSON string as readily as a file, and a string
    keeps the spawn self-describing: no generated file on disk to drift from
    the code that depends on it. Noctis's own server, plus whatever ~/.claude
    already has -- the config root is not redirected."""
    return json.dumps({"mcpServers": {"noctis": {
        "command": sys.executable,
        "args": [str(MCP_SERVER)],
    }}})


def settings_config() -> str:
    """The tracked permission policy, as inline JSON.

    **It registers no hooks, and used to appear to.** Until 2026-09-17 this
    built a `hooks` block naming `log_action.py` and `mark_session_end.py`,
    and nothing ever read it: the `-p` orchestrator that passed this as
    `--settings` was deleted at the PTY migration, and its one remaining
    caller (`capabilities.py --migrate`) reads `permissions` alone. The block
    cost more than its bytes, because the hooks README and DOCUMENTATION §11
    both described it as how a session gets its hooks, and a session reading
    either was told the wrong thing for two months.

    Where hooks actually come from, both routes, so this is written down
    somewhere the code can be read next to it:

    * the telemetry pair, from each project's own `.claude/settings.local.json`
      (so a project without one gets neither; see DOCUMENTATION §21)
    * `guard_shared_tree.py`, from `interactive.py`'s `statusline_settings`,
      which every hosted session carries in its argv
    """
    return json.dumps(json.loads(SHARED_SETTINGS.read_text()))


# Where `claude` actually lives, checked in order. PATH is searched first,
# but it cannot be relied on: launchd starts processes with a bare
# /usr/bin:/bin:/usr/sbin:/sbin, which contains no Homebrew and no npm
# prefix -- so a backend started by the scheduler would fail to find the
# engine even though it runs fine from a terminal.
_CLAUDE_FALLBACKS = (
    Path("/opt/homebrew/bin/claude"),
    Path("/usr/local/bin/claude"),
    Path.home() / ".local/bin/claude",
    Path.home() / ".claude/local/claude",
)


def claude_binary() -> str:
    """Absolute path to the engine. NOCTIS_CLAUDE_BIN overrides everything."""
    override = os.environ.get("NOCTIS_CLAUDE_BIN")
    if override:
        return override
    if found := shutil.which("claude"):
        return found
    for candidate in _CLAUDE_FALLBACKS:
        if candidate.exists():
            return str(candidate)
    # Returned rather than raised, so a failed spawn names what was looked
    # for instead of dying on a bare errno in a place nobody is looking.
    return "claude"


RECAP_MODEL = os.environ.get("NOCTIS_RECAP_MODEL", "claude-haiku-4-5")


def one_shot_command(prompt: str) -> list[str]:
    """The argv, separately so it can be asserted on without launching.

    `--output-format json`, not stream-json: a one-shot has no events worth
    watching, only a result, and reading one object is what let this stop
    depending on the stream parser the orchestrator took with it.
    """
    return [
        claude_binary(), "-p", prompt,
        "--model", RECAP_MODEL,
        "--output-format", "json",
        "--permission-mode", "plan",
        # Refused outright rather than left to the permission mode: this
        # summarises text that is handed to it, and a summariser that can
        # read the filesystem is a larger thing than the job needs.
        "--disallowedTools", "Bash Edit Write Read Grep Glob WebSearch WebFetch Task",
        # A script leaves no session behind. Without this every recap wrote a
        # transcript under `~/.claude/projects/`, and the indexer -- which
        # reads that directory as the record of what happened -- filed each
        # one as a `general` conversation titled "Summarise this
        # conversation in ONE sentence…". Five of them were in history
        # before the sweep of 2026-09-14 noticed.
        "--no-session-persistence",
        # And it runs no project hooks. The backend's cwd is this repo, whose
        # `.claude/settings.local.json` bakes `--mode dev` into its hooks;
        # each one-shot's SessionEnd therefore fired *dev's* hook, which
        # cleared dev's busy marker -- sixteen times in one day, out from
        # under a live Faber session. The user's own settings still load;
        # the project's and the local file's do not.
        "--setting-sources", "user",
    ]


async def one_shot(prompt: str, timeout: float = 60) -> str:
    """Run a single prompt on the cheap tier and return its text."""
    env = dict(os.environ)
    # No CLAUDE_CONFIG_DIR, for the same reason no session sets one.
    env.pop("CLAUDE_CONFIG_DIR", None)
    proc = await asyncio.create_subprocess_exec(
        *one_shot_command(prompt),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"one_shot produced no result in {timeout}s")
    if proc.returncode:
        raise RuntimeError(f"engine exited {proc.returncode}: "
                           f"{err.decode('utf-8', 'replace').strip()[:300]}")
    try:
        body = json.loads(out.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"engine returned something other than JSON: {exc}")
    return str(body.get("result") or "").strip()
