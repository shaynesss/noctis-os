"""Process driver — Noctis v2 Stage 2 item 1.

Spawns Claude Code, streams its `stream-json` output, yields normalized
Events. The half of the orchestrator with the moving parts; `parser.py` has
the shape knowledge and no I/O, and keeping them apart is what makes either
testable.

`launch()` takes a command rather than hardcoding `claude`, so tests can
drive the whole streaming path with `cat fixture.jsonl` — no subprocess of
the real CLI, no quota, no network. `build_command()` is what production
passes in, and is a pure function so it can be asserted on directly.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Sequence

from .events import EngineError, Event, SessionStart
from .parser import parse_line

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = REPO_ROOT / "backend" / "launch_config"

MODE_MODELS = {
    "general": "claude-opus-5",
    "faber": "claude-opus-5",
    "noctua": "claude-opus-5",
    "vesper": "claude-opus-5",
    "maintenance": "claude-haiku-4-5",
}

# Tool policy per mode, enforced at spawn rather than by instruction. A
# prompt asking a session not to edit files is a request; --disallowedTools
# is a fact. Maintenance is the one that matters: propose-never-apply is
# the guardrail the regression suite caught failing on a plainly-worded
# request, so it gets a cage as well as a rule.
# Read-only and research tools, pre-allowed wherever a mode should have
# them. Nothing here mutates anything.
#
# **Why this is needed at all.** With `--print`, the CLI's
# `--permission-prompts` defaults to "none" -- "anything that would prompt is
# denied automatically". There is no interactive session to ask, so a tool
# that would normally prompt simply fails. That is why WebSearch and WebFetch
# came back "you haven't granted it yet" with no way to grant it: the UI's
# permission chip sets --permission-mode, and "ask each time" means "deny"
# when nobody can be asked.
#
# Mutating tools are deliberately NOT here. Bash, Edit and Write stay
# governed by the permission mode, so nothing that changes your machine is
# silently pre-approved to make the app feel like it works.
_READ_TOOLS = "Read Grep Glob"
_WEB_TOOLS = "WebSearch WebFetch"

MODE_TOOLS: dict[str, dict[str, str]] = {
    "general": {"disallowed": "Edit Write",
                "allowed": f"{_READ_TOOLS} {_WEB_TOOLS}"},
    # The build mode: its whole job is changing the repo, so its mutating
    # tools stay under the permission mode rather than being listed here.
    "faber": {"allowed": f"{_READ_TOOLS} {_WEB_TOOLS}"},
    "noctua": {"disallowed": "Edit Write Bash",
               "allowed": f"{_READ_TOOLS} {_WEB_TOOLS}"},
    "vesper": {"disallowed": "Edit Write Bash",
               "allowed": f"{_READ_TOOLS} {_WEB_TOOLS}"},
    # No web: maintenance audits the vault, and nothing vault-touching
    # routes outward (Decision Log:76).
    "maintenance": {"disallowed": "Edit Write Bash",
                    "allowed": _READ_TOOLS},
}


# The cycle the UI offers, in escalating order of what a session may do
# without asking. bypassPermissions is deliberately NOT here: it is a real
# flag and remains available to set explicitly, but it should not be
# reachable by tapping a key repeatedly.
PERMISSION_CYCLE = ("plan", "manual", "acceptEdits", "auto")


# Where `claude` actually lives, checked in order. PATH is searched first,
# but it cannot be relied on: launchd starts processes with a bare
# /usr/bin:/bin:/usr/sbin:/sbin, which contains no Homebrew and no npm
# prefix -- so a backend started by the scheduler would fail to find the
# engine even though it runs fine from a terminal. That failure surfaced as
# a bare "[Errno 2] No such file or directory" with nothing naming the
# binary, which is why the error below says what was looked for.
_CLAUDE_FALLBACKS = (
    Path("/opt/homebrew/bin/claude"),
    Path("/usr/local/bin/claude"),
    Path.home() / ".local/bin/claude",
    Path.home() / ".claude/local/claude",
)


def claude_binary() -> str:
    """Absolute path to the engine.

    NOCTIS_CLAUDE_BIN overrides everything, for a non-standard install or to
    pin a specific build.
    """
    override = os.environ.get("NOCTIS_CLAUDE_BIN")
    if override:
        return override
    if found := shutil.which("claude"):
        return found
    for candidate in _CLAUDE_FALLBACKS:
        if candidate.exists():
            return str(candidate)
    # Returned rather than raised: the caller turns a failed spawn into an
    # EngineError in the transcript, and a raise here would instead be an
    # unhandled 500 with the same information in a place nobody is looking.
    return "claude"


@dataclass
class SessionSpec:
    mode: str
    prompt: str
    permission_mode: str = "manual"
    resume_id: str | None = None
    cwd: Path | None = None
    vault_path: Path | None = None
    extra_args: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.mode not in MODE_MODELS:
            raise ValueError(f"unknown mode: {self.mode}")


def build_command(spec: SessionSpec) -> list[str]:
    """The exact argv for a spawn. Pure, so it can be asserted on."""
    cmd = [
        claude_binary(), "-p", spec.prompt,
        "--model", MODE_MODELS[spec.mode],
        "--output-format", "stream-json",
        "--verbose",                 # required for stream-json to emit events
    ]
    if spec.permission_mode:
        cmd += ["--permission-mode", spec.permission_mode]
    if spec.resume_id:
        cmd += ["--resume", spec.resume_id]
    if disallowed := MODE_TOOLS.get(spec.mode, {}).get("disallowed"):
        cmd += ["--disallowedTools", disallowed]
    if allowed := MODE_TOOLS.get(spec.mode, {}).get("allowed"):
        cmd += ["--allowedTools", allowed]
    if spec.vault_path:
        cmd += ["--add-dir", str(spec.vault_path)]
    cmd += list(spec.extra_args)
    return cmd


def build_env(spec: SessionSpec) -> dict[str, str]:
    """Environment for a spawn.

    CLAUDE_CONFIG_DIR points at the mode's own pre-authenticated directory.
    It is never created here: credentials are Keychain entries keyed to the
    directory path, so a directory invented at spawn time would be
    unauthenticated and the session would die with "Not logged in".
    """
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = str(CONFIG_ROOT / spec.mode)
    env["NOCTIS_MODE"] = spec.mode          # read by the telemetry hooks
    return env


async def launch(
    command: Sequence[str],
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: float | None = None,
) -> AsyncIterator[Event]:
    """Run a command emitting stream-json; yield normalized Events.

    Yields as lines arrive rather than collecting — a turn can run for
    minutes and the transcript should fill as it goes, which is the whole
    reason the UI hosts sessions instead of firing and forgetting.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(cwd) if cwd else None,
        )
    except (OSError, FileNotFoundError) as e:
        # Naming the binary matters: the bare errno says only "No such file
        # or directory", which reads like a bad cwd rather than a missing
        # engine and sends you looking in the wrong place.
        yield EngineError(f"could not start engine {command[0]!r}: {e}", fatal=True)
        return

    assert proc.stdout is not None
    try:
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                yield EngineError(f"engine produced no output for {timeout}s", fatal=True)
                return
            if not raw:
                break
            for event in parse_line(raw.decode("utf-8", "replace")):
                yield event

        await proc.wait()
        if proc.returncode:
            stderr = (await proc.stderr.read()).decode("utf-8", "replace") if proc.stderr else ""
            # A non-zero exit after a clean stream is still a failure worth
            # surfacing: the CLI reports refusals and auth problems this way.
            yield EngineError(
                f"engine exited {proc.returncode}: {stderr.strip()[:300]}", fatal=True
            )
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


async def run_session(spec: SessionSpec, timeout: float | None = 600) -> AsyncIterator[Event]:
    """Production entry point: spec → spawned session → Events."""
    config_dir = CONFIG_ROOT / spec.mode
    if not config_dir.is_dir():
        yield EngineError(
            f"config dir missing for '{spec.mode}' — run ./bootstrap/bootstrap.sh", fatal=True
        )
        return
    async for event in launch(
        build_command(spec), env=build_env(spec), cwd=spec.cwd, timeout=timeout
    ):
        yield event


def session_id_of(events: Sequence[Event]) -> str | None:
    """The id `--resume` takes, from a completed run's events."""
    for e in events:
        if isinstance(e, SessionStart) and e.session_id:
            return e.session_id
    return None
