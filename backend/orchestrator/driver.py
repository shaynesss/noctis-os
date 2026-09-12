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
import json
import os
import shutil
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, AsyncIterator, Sequence

from .modes import mode_agents, mode_methodology
from .events import (EngineError, Event, SessionStart, TextDelta,
                     ToolCall, TurnEnd)
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

# Tool policy, identical for every mode.
#
# **There is deliberately no per-mode cage any more.** Modes used to differ
# here -- maintenance and the research modes had Bash, Edit and Write in
# --disallowedTools, general had Edit and Write -- and that was the wrong axis
# to vary on. What makes Noctua research and Faber build is the methodology
# each one reads, composed into its own CLAUDE_CONFIG_DIR/CLAUDE.md by
# prompts/render.py. Varying *capability* on top of that produced a mode
# handed a task it could not perform and with no way to say so: the turn
# tried, was refused, ended with nothing done, and drew a blank transcript
# indistinguishable from a crash. Methodology is the difference between the
# modes. Permission is not.
#
# The guardrails that actually matter are kept, and kept where they apply to
# every mode rather than to one: `git push` is denied outright in
# permissions.json, and the permission chip still governs each session at run
# time. What is gone is the idea that a mode is defined by what it cannot do.
#
# **Why --allowedTools is needed at all.** `--permission-prompts` decides *who
# answers* a permission request under `--print`. It defaults to "host" -- the
# SDK host, or whatever `--permission-prompt-tool` names. That is now the
# Noctis MCP server, so a request reaches the interface and a person answers.
# Anything listed here skips the question entirely.
ALL_TOOLS = (
    "Read Grep Glob WebSearch WebFetch Edit Write Bash "
    "NotebookEdit TodoWrite Task "
    # Noctis's own retrieval, pre-approved: a session asking permission to
    # search the vault is asking permission to do the thing the design is
    # built around, and the first live session was duly stopped by a dialog
    # to allow `vault_search("design lodge")`. `propose` is deliberately
    # absent -- that one writes, and it is Custos's, so it keeps asking.
    "mcp__noctis__vault_search mcp__noctis__history_search "
    "mcp__noctis__job_context mcp__noctis__worklist"
)

# What a session can be switched to, and what each is for. The mode's own
# entry in MODE_MODELS is the default; this is the menu when you want
# something else for one session -- dev.md's "effort routing expressed as
# model routing", made reachable rather than a launcher-only override.
MODEL_CATALOG: list[dict[str, str]] = [
    {"id": "claude-opus-5", "name": "Opus 5",
     "blurb": "Best for everyday, complex tasks"},
    {"id": "claude-sonnet-5", "name": "Sonnet 5",
     "blurb": "Efficient for routine tasks"},
    {"id": "claude-haiku-4-5", "name": "Haiku 4.5",
     "blurb": "Fastest for quick answers"},
]

MODE_TOOLS: dict[str, dict[str, str]] = {
    # The same entry for every mode, by construction rather than by five
    # copies that could drift apart. The dict shape is kept because the
    # panels router reports it to the interface, and because reintroducing a
    # per-mode difference should have to be written on purpose rather than
    # inherited from a default nobody revisited.
    mode: {"allowed": ALL_TOOLS} for mode in MODE_MODELS
}


# The cycle the UI offers, in escalating order of what a session may do
# without asking. bypassPermissions is deliberately NOT here: it is a real
# flag and remains available to set explicitly, but it should not be
# reachable by tapping a key repeatedly.
PERMISSION_CYCLE = ("plan", "manual", "acceptEdits", "auto")

# How hard the engine thinks, in the order the chip cycles.
#
# This replaces the permission chip in the interface, and the swap is not
# cosmetic. Every mode now spawns with the same tools and a shared allowlist,
# so the permission mode changes almost nothing a person would notice --
# whereas effort changes the answer. dev.md has asked for this routing since
# it was written ("default high; medium/low for mechanical or repetitive
# work; xhigh for genuine deep exploration") and no code ever passed it.
#
# It takes effect on the next turn, which is immediately: every turn is its
# own `claude -p` spawn, resumed by session id, so a flag chosen now governs
# the very next thing the session does. `max` is left out of the cycle for
# the same reason bypassPermissions is -- real, settable, but not something
# to land on by tapping a key.
EFFORT_CYCLE = ("low", "medium", "high", "xhigh")

# Who answers a permission request.
#
# "none" means nobody, and everything that would ask is refused -- which is
# what this was, and why the chip's labels were aspirational: a request went
# out and died. "host" hands the question to --permission-prompt-tool, which
# is the MCP tool below. That is what makes `manual` actually ask you, and so
# what makes the chip a control rather than a caption.
PERMISSION_PROMPTS = "host"

# The Noctis MCP server, attached to every spawn.
#
# It was built and verified in Stage 2 item 2 and then never wired to a
# session: no --mcp-config anywhere, no .mcp.json in any config dir. So every
# session has been running without the vault retrieval the whole design rests
# on -- `vault_search` existed and nothing could call it.
#
# Dependency-free by design, so the interpreter running the backend can run it
# directly and there is nothing to install.
MCP_SERVER = REPO_ROOT / "backend" / "mcp" / "server.py"

# The tool the CLI calls when it needs a decision. The name is the MCP
# convention: mcp__<server>__<tool>.
PERMISSION_TOOL = "mcp__noctis__permission_prompt"


def mcp_config() -> str:
    """--mcp-config takes a JSON string as readily as a file, and a string
    keeps the spawn self-describing: no generated file on disk to drift from
    the code that depends on it.

    Noctis's own server, plus whatever ~/.claude already has -- the config
    root is no longer redirected, so a server configured once for ordinary
    Claude Code use is available here too rather than needing a second entry.
    """
    return json.dumps({"mcpServers": {"noctis": {
        "command": sys.executable,
        "args": [str(MCP_SERVER)],
    }}})


def settings_config() -> str:
    """Permissions from the tracked file, plus the telemetry hooks.

    Inline JSON rather than a path, because the hooks need absolute
    interpreter and script paths and those cannot be committed -- which is
    exactly why they used to live in the per-mode settings.json that
    bootstrap generated and gitignored. That file is not read any more: it
    belonged to a CLAUDE_CONFIG_DIR this no longer points at, so the hooks
    would have silently stopped firing, and a telemetry hook that stops
    firing tells you nothing by staying quiet.

    Composing here keeps one tracked policy (permissions.json, reviewable in
    a diff) and one machine-specific part (these paths, derived not stored).
    """
    policy = json.loads(SHARED_SETTINGS.read_text())
    hook = lambda script: [{"matcher": "", "hooks": [{                # noqa: E731
        "type": "command",
        "command": f"{REPO_ROOT}/backend/.venv/bin/python3 "
                   f"{REPO_ROOT}/backend/hooks/{script}",
    }]}]
    policy["hooks"] = {
        "PostToolUse": hook("log_action.py"),
        "SessionEnd": hook("mark_session_end.py"),
    }
    return json.dumps(policy)

# Bash permissions, shared by every mode and tracked in git.
#
# Not in the per-mode CLAUDE_CONFIG_DIRs: `CLAUDE_CONFIG_DIR` redirects where
# user settings are read from, so ~/.claude/settings.json -- and every
# permission ever accumulated in it -- is invisible to a spawned session.
# Writing a block into each config dir instead would work and be untracked
# (backend/launch_config/* is gitignored), so it would vanish on the next
# bootstrap and drift between the five dirs in the meantime.
#
# **Bash is allowed whole, not command by command.** It used to be a curated
# list -- make, pytest, npm, a dozen git subcommands -- which meant every
# ordinary thing outside it (sed, find, mkdir, gh, curl) hit a prompt. The
# list could only ever be as complete as the last time someone remembered to
# extend it, and a session blocked on an unlisted command looks exactly like
# a session that had nothing to say. Same failure, smaller blast radius, so
# the same answer: a mode is not defined by what it cannot do.
#
# **git push is denied, not merely absent.** dev.md's "commits as work
# progresses, Shayne pushes" was a rule in a markdown file that a session
# could simply fail to follow; here it is a fact about what the process may
# do. The scheduler's vault push is backend Python calling git directly, not
# a session's Bash tool, so it is unaffected.
#
# The file carries no comment key of its own: under --print a settings file
# that fails validation is *silently ignored*, so an unrecognised key would
# drop every rule here without saying so.
SHARED_SETTINGS = Path(__file__).resolve().parent / "permissions.json"


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


@dataclass(frozen=True)
class Image:
    """An image sent with a turn, inline.

    Base64 in the message rather than a file on disk. Writing the image out
    and telling the session to Read it back worked, but it cost a tool call,
    put an absolute path in the transcript, and made the reply depend on a
    file still existing. Inline, the picture is simply part of what was said.
    """
    media_type: str
    data: str          # base64, no data: prefix


@dataclass
class SessionSpec:
    mode: str
    prompt: str
    permission_mode: str = "manual"
    resume_id: str | None = None
    cwd: Path | None = None
    vault_path: Path | None = None
    extra_args: Sequence[str] = field(default_factory=tuple)
    images: Sequence[Image] = field(default_factory=tuple)
    # Overrides the mode's default for this session only. None means the
    # mode decides, which is what almost every session wants.
    model: str | None = None
    # How hard the engine thinks. dev.md has always said "default high,
    # medium/low for mechanical work, xhigh for deep exploration" -- and
    # nothing passed it, so every session ran at whatever the CLI defaulted
    # to and the rule described a setting no code applied.
    effort: str = "high"
    # This spawn is the automatic close of a turn that did not close itself,
    # not work of its own. It exists to stop the obvious recursion: a
    # continuation is a turn, so without a way to tell them apart it would
    # qualify for its own continuation and never terminate.
    continuation: bool = False

    def __post_init__(self) -> None:
        if self.mode not in MODE_MODELS:
            raise ValueError(f"unknown mode: {self.mode}")
        known = {m["id"] for m in MODEL_CATALOG}
        if self.model is not None and self.model not in known:
            # Rejected here rather than passed through: an unknown model is a
            # spawn that fails seconds later with a less obvious message.
            raise ValueError(f"unknown model: {self.model}")
        if self.effort not in EFFORT_CYCLE:
            raise ValueError(f"unknown effort: {self.effort}")

    @property
    def resolved_model(self) -> str:
        return self.model or MODE_MODELS[self.mode]


def build_command(spec: SessionSpec) -> list[str]:
    """The exact argv for a spawn. Pure, so it can be asserted on.

    With images the prompt moves to stdin: `--input-format stream-json` takes
    a structured message, which is the only way to attach a picture to a turn
    without writing it to disk first. Text-only turns keep the positional
    prompt, which is simpler and is the overwhelmingly common case.
    """
    cmd = [claude_binary(), "-p"]
    if spec.images:
        cmd += ["--input-format", "stream-json"]
    else:
        cmd.append(spec.prompt)
    cmd += [
        "--model", spec.resolved_model,
        "--output-format", "stream-json",
        "--verbose",                 # required for stream-json to emit events
    ]
    if spec.permission_mode:
        cmd += ["--permission-mode", spec.permission_mode]
    cmd += ["--permission-prompts", PERMISSION_PROMPTS,
            "--permission-prompt-tool", PERMISSION_TOOL,
            "--mcp-config", mcp_config(),
            "--settings", settings_config(),
            "--effort", spec.effort]
    # The mode, as text rather than as a file. This is what used to be
    # written into a per-mode CLAUDE_CONFIG_DIR/CLAUDE.md on every launch,
    # and writing it was the only reason those dirs existed. In the argv it
    # cannot be raced by a concurrent session of the same mode, and it also
    # switches system-prompt snapshotting off -- so an edit to a mode's
    # methodology reaches a *resumed* session, which under the recorded
    # snapshot it never did.
    if methodology := mode_methodology(spec.mode):
        cmd += ["--append-system-prompt", methodology]
    if agents := mode_agents(spec.mode):
        cmd += ["--agents", agents]
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

    **CLAUDE_CONFIG_DIR is deliberately not set.** Sessions run against the
    real ~/.claude, the same config root an ordinary Claude Code session
    uses, and that is the whole point: the config root is where plugins,
    skills, subagents, slash commands, MCP servers, accumulated permissions
    and memory all live. Redirecting it did not override some settings, it
    replaced the entire surface -- so a Noctis session had none of them, and
    Faber was handed a methodology naming seven tools (Impeccable,
    code-review, the Critic, Playwright, shadcn/Magic MCP, CodeRabbit) that
    its own process could not reach.

    The redirect existed for one reason: the orchestrator rewrote each dir's
    CLAUDE.md on every launch, and two concurrent sessions sharing a dir
    would race on that file. That is solved better by not using a file --
    the mode's methodology now travels in the argv via
    --append-system-prompt, so there is nothing on disk to race on. (The
    second reason bootstrap gives, one Keychain login per dir, was never a
    reason for the split; it was its price.)
    """
    env = dict(os.environ)
    env.pop("CLAUDE_CONFIG_DIR", None)      # inherit ~/.claude, never a copy
    env["NOCTIS_MODE"] = spec.mode          # read by the telemetry hooks
    return env


# asyncio's StreamReader defaults to a 64KB line limit, and `stream-json`
# puts an entire tool result on one line. A Read of any sizeable file --
# a log, a base64 image -- overruns it, and readline() then raises
# "Separator is not found, and chunk exceed the limit", killing the session
# mid-turn. Found when a pasted screenshot did exactly that.
#
# 32MB because the ceiling here is a line the CLI already chose to emit, and
# refusing to read what it sent is not a limit worth enforcing at this layer.
STREAM_LIMIT = 32 * 1024 * 1024


def build_stdin(spec: SessionSpec) -> bytes | None:
    """One stream-json user message carrying the prompt and its images.

    None when there are no images, so the ordinary path stays a plain argv
    with nothing written to the process at all.
    """
    if not spec.images:
        return None
    content: list[dict[str, Any]] = [{"type": "text", "text": spec.prompt}]
    for image in spec.images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": image.media_type, "data": image.data},
        })
    message = {"type": "user", "message": {"role": "user", "content": content}}
    return (json.dumps(message) + "\n").encode()


async def launch(
    command: Sequence[str],
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: float | None = None,
    stdin_data: bytes | None = None,
) -> AsyncIterator[Event]:
    """Run a command emitting stream-json; yield normalized Events.

    Yields as lines arrive rather than collecting — a turn can run for
    minutes and the transcript should fill as it goes, which is the whole
    reason the UI hosts sessions instead of firing and forgetting.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if stdin_data else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(cwd) if cwd else None,
            limit=STREAM_LIMIT,
        )
    except (OSError, FileNotFoundError) as e:
        # Naming the binary matters: the bare errno says only "No such file
        # or directory", which reads like a bad cwd rather than a missing
        # engine and sends you looking in the wrong place.
        yield EngineError(f"could not start engine {command[0]!r}: {e}", fatal=True)
        return

    if stdin_data is not None and proc.stdin is not None:
        # Written and closed before reading: the engine waits for end-of-input
        # before it starts, so holding stdin open would hang the turn.
        proc.stdin.write(stdin_data)
        await proc.stdin.drain()
        proc.stdin.close()

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


async def with_turn_totals(events: AsyncIterator[Event]) -> AsyncIterator[Event]:
    """Fill in TurnEnd's `text_chars` and `tool_calls` as the turn streams.

    Separate from `run_session` so it can be tested against a synthetic
    stream rather than a spawned process -- the thing it detects is a turn
    that produces no text, and making a real engine do that on demand is not
    something a test can rely on.

    The parser cannot do this itself: it builds TurnEnd from the `result`
    event, which carries usage and timing and no knowledge of the text that
    came before it. Only something watching the whole stream can count.
    """
    text_chars = 0
    tool_calls = 0
    since_tool = 0        # text since the most recent tool call
    async for event in events:
        if isinstance(event, TextDelta):
            text_chars += len(event.text)
            since_tool += len(event.text)
        elif isinstance(event, ToolCall):
            tool_calls += 1
            since_tool = 0        # anything said before this does not close it
        elif isinstance(event, TurnEnd):
            event = replace(event, text_chars=text_chars, tool_calls=tool_calls,
                            text_after_last_tool=since_tool)
            # A run may carry more than one turn.
            text_chars = tool_calls = since_tool = 0
        yield event


async def run_session(spec: SessionSpec, timeout: float | None = 600) -> AsyncIterator[Event]:
    """Production entry point: spec → spawned session → Events."""
    config_dir = CONFIG_ROOT / spec.mode
    if not config_dir.is_dir():
        yield EngineError(
            f"config dir missing for '{spec.mode}' — run ./bootstrap/bootstrap.sh", fatal=True
        )
        return
    async for event in with_turn_totals(launch(
        build_command(spec), env=build_env(spec), cwd=spec.cwd, timeout=timeout,
        stdin_data=build_stdin(spec),
    )):
        yield event


def session_id_of(events: Sequence[Event]) -> str | None:
    """The id `--resume` takes, from a completed run's events."""
    for e in events:
        if isinstance(e, SessionStart) and e.session_id:
            return e.session_id
    return None


# A one-shot for short mechanical text, not a session.
#
# Deliberately outside the SessionManager: it does not belong in the
# concurrency budget (it is not work you are waiting on), it must not appear
# in history as a conversation, and queueing it behind two real sessions
# would make a recap arrive long after the transcript it describes.
# Sent when a mode session is opened with nothing typed, so the mode runs
# its own session-start routine rather than sitting empty. Owned here rather
# than by the shell: the backend titles the conversation, and a session
# titled with the opener's own text is how the brief came to report "Noctua
# opened this morning with no work yet recorded" as if it were news.
OPENING_PROMPT = (
    "Session starting, nothing asked yet. Follow your session-start routine: "
    "say which mode this is in one line, surface anything your methodology or "
    "state file says is due or parked, and ask what I want to work on. "
    "Do not begin any work yet."
)

RECAP_MODEL = os.environ.get("NOCTIS_RECAP_MODEL", "claude-haiku-4-5")


async def one_shot(prompt: str, timeout: float = 60) -> str:
    """Run a single prompt on the cheap tier and return its text.

    Tools are refused outright rather than left to the permission mode: this
    summarises text that is handed to it, and a summariser that can read the
    filesystem is a larger thing than the job needs.
    """
    command = [
        claude_binary(), "-p", prompt,
        "--model", RECAP_MODEL,
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "plan",
        "--disallowedTools", "Bash Edit Write Read Grep Glob WebSearch WebFetch Task",
    ]
    # No CLAUDE_CONFIG_DIR, for the same reason no spawn sets one -- and this
    # was the last place it survived. Pointing at launch_config/general also
    # made a one-line summariser depend on a directory that is otherwise dead
    # and safe to delete, which would have surfaced as "Not logged in" from
    # the recap of all things.
    env = dict(os.environ)
    env.pop("CLAUDE_CONFIG_DIR", None)

    parts: list[str] = []
    async for event in launch(command, env=env, timeout=timeout):
        if isinstance(event, TextDelta):
            parts.append(event.text)
    return "".join(parts).strip()
