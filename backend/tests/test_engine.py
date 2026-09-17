"""What survives of the driver: where the engine is, what it runs as, and the
one-shot call. Asserted on argv and composed config, never by launching."""
import json
from pathlib import Path

import engine


def test_the_binary_override_wins(monkeypatch):
    monkeypatch.setenv("NOCTIS_CLAUDE_BIN", "/custom/claude")
    assert engine.claude_binary() == "/custom/claude"


def test_the_binary_is_resolved_not_left_to_path_lookup(monkeypatch):
    """launchd starts processes with a bare PATH containing no Homebrew, so a
    backend started by the scheduler would fail to find `claude` even though
    it runs fine from a terminal -- which is what happened on 2026-09-08."""
    monkeypatch.setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    monkeypatch.delenv("NOCTIS_CLAUDE_BIN", raising=False)
    # Either an absolute fallback was found, or the bare name is returned so
    # the caller can say what it looked for -- never a raise.
    assert engine.claude_binary().endswith("claude")


def test_one_shot_is_a_script_not_a_session():
    """The one place `-p` remains, and the right use of it: a scripting mode
    used for a script. Every tool refused, one JSON object back."""
    cmd = engine.one_shot_command("summarise this")
    assert cmd[1:3] == ["-p", "summarise this"]
    assert cmd[cmd.index("--output-format") + 1] == "json", \
        "a one-shot has no events worth watching, only a result"
    assert "stream-json" not in cmd and "--verbose" not in cmd
    disallowed = cmd[cmd.index("--disallowedTools") + 1].split()
    for tool in ("Bash", "Edit", "Write", "Read"):
        assert tool in disallowed


def test_one_shot_leaves_nothing_behind():
    """A recap is not a conversation and must not fire the repo's hooks.

    Each of these was found live on 2026-09-14: recap transcripts filed into
    history as `general` sessions, and the backend's cwd -- this repo --
    applying its `--mode dev` SessionEnd hook to every one-shot, clearing
    Faber's busy marker under a running session.
    """
    cmd = engine.one_shot_command("summarise this")
    assert "--no-session-persistence" in cmd, "a script writes no transcript"
    assert cmd[cmd.index("--setting-sources") + 1] == "user", \
        "project hooks belong to sessions opened in the project, not to scripts"


def test_every_mode_has_a_model():
    for mode, model in engine.MODE_MODELS.items():
        assert model.startswith("claude-"), mode
    assert set(engine.MODE_TOOLS) == set(engine.MODE_MODELS)


def test_settings_config_is_the_tracked_policy_and_registers_no_hooks():
    """It carried a `hooks` block that nothing read, once the `-p` path that
    passed it as `--settings` was deleted. Its survival is why two documents
    told readers that a hosted session gets its telemetry hooks from here; it
    gets them from the project's own settings file. Hooks that must hold
    everywhere go through `interactive.statusline_settings` instead, which is
    pinned by test_guard_shared_tree."""
    tracked = json.loads(engine.SHARED_SETTINGS.read_text())
    composed = json.loads(engine.settings_config())
    assert composed == tracked
    assert "hooks" not in composed


def test_the_mcp_config_points_at_a_server_that_exists():
    cfg = json.loads(engine.mcp_config())
    assert str(engine.MCP_SERVER) in cfg["mcpServers"]["noctis"]["args"]
    assert engine.MCP_SERVER.exists()
