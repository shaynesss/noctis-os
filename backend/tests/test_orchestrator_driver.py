"""Driver and manager tests — Noctis v2 Stage 2 item 1.

The streaming path is exercised end to end with `cat fixture.jsonl` instead
of the real CLI: same async subprocess, same line reading, same parsing, no
quota and no network. `build_command` is pure and asserted directly.
"""
import asyncio
import json
from pathlib import Path

import pytest

from orchestrator.driver import (
    MODE_MODELS, MODE_TOOLS, Image, SessionSpec, build_command, build_env, build_stdin,
    claude_binary, launch,
    session_id_of, with_turn_totals,
)
from orchestrator.events import (EngineError, SessionStart, TextDelta, ToolCall,
                                 ToolResult, TurnEnd, Usage)
from orchestrator.manager import SessionManager

FIXTURE = Path(__file__).parent / "fixtures" / "stream_with_tools.jsonl"


async def _collect(agen):
    return [e async for e in agen]


# ---------------------------------------------------------------- command

def test_command_carries_the_flags_stream_json_needs():
    cmd = build_command(SessionSpec(mode="faber", prompt="go"))
    # Resolved path, not the bare name -- see test_engine_is_resolved_...
    assert Path(cmd[0]).name == "claude"
    assert cmd[1:3] == ["-p", "go"]
    assert "--output-format" in cmd and "stream-json" in cmd
    # stream-json emits nothing useful without --verbose; easy to lose in a
    # refactor and the failure looks like an empty session.
    assert "--verbose" in cmd


def test_engine_is_resolved_to_a_path_not_left_to_path_lookup(monkeypatch):
    """launchd starts processes with a bare /usr/bin:/bin:/usr/sbin:/sbin --
    no Homebrew, no npm prefix. A backend started by the scheduler would
    therefore fail to find `claude` even though it runs fine from a
    terminal, which is exactly what happened on 2026-09-08."""
    monkeypatch.setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    monkeypatch.delenv("NOCTIS_CLAUDE_BIN", raising=False)
    resolved = claude_binary()
    # Either an absolute fallback was found, or the bare name is returned so
    # the caller can report a proper EngineError -- never a silent crash.
    assert resolved.endswith("claude")


def test_explicit_binary_override_wins(monkeypatch):
    monkeypatch.setenv("NOCTIS_CLAUDE_BIN", "/custom/path/claude")
    assert claude_binary() == "/custom/path/claude"


def test_failed_spawn_names_the_binary_it_tried(monkeypatch):
    """A bare errno reads like a bad cwd rather than a missing engine."""
    events = asyncio.run(_collect(launch(["/nope/definitely-not-real"])))
    assert "/nope/definitely-not-real" in events[0].message


def test_each_mode_gets_its_production_model():
    for mode, model in MODE_MODELS.items():
        cmd = build_command(SessionSpec(mode=mode, prompt="x"))
        assert cmd[cmd.index("--model") + 1] == model


def test_resume_passes_the_engine_session_id():
    cmd = build_command(SessionSpec(mode="vesper", prompt="more", resume_id="abc-123"))
    assert cmd[cmd.index("--resume") + 1] == "abc-123"


def test_every_mode_keeps_the_full_tool_surface():
    """No mode is spawned with a cage. Maintenance included: its
    propose-never-apply rule now rests on its methodology and on the
    permission chip, not on a tool list that also stopped it reading a repo
    it was asked to audit."""
    for mode in MODE_MODELS:
        cmd = build_command(SessionSpec(mode=mode, prompt="x"))
        assert "--disallowedTools" not in cmd


def test_unknown_mode_is_rejected_at_construction():
    with pytest.raises(ValueError):
        SessionSpec(mode="nonsense", prompt="x")


def test_sessions_inherit_the_real_config_root(monkeypatch):
    """No CLAUDE_CONFIG_DIR, deliberately.

    The config root is where plugins, skills, subagents, slash commands, MCP
    servers, accumulated permissions and memory live. Pointing at a private
    copy did not override some settings, it replaced all of them -- which is
    how Faber came to be reading a methodology naming seven tools its own
    process could not reach. Unset even when the environment already has one,
    so a backend started from a shell that exports it does not quietly get
    the old behaviour back.
    """
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/somewhere/else")
    env = build_env(SessionSpec(mode="noctua", prompt="x"))
    assert "CLAUDE_CONFIG_DIR" not in env
    assert env["NOCTIS_MODE"] == "noctua"      # the telemetry hooks read this


def test_the_mode_travels_in_the_argv_not_in_a_file(monkeypatch):
    """What used to be a per-mode CLAUDE.md rewritten on every launch.

    Writing it was the only real reason for the split config dirs -- two
    concurrent sessions of one mode would race on the file. In the argv there
    is no file to race on, and --append-system-prompt also turns snapshotting
    off, so an edited methodology reaches a resumed session instead of being
    shadowed by the prompt it was born with.
    """
    import orchestrator.driver as driver
    monkeypatch.setattr(driver, "mode_methodology", lambda mode, job=None: f"# {mode} method")
    cmd = build_command(SessionSpec(mode="faber", prompt="x"))
    assert cmd[cmd.index("--append-system-prompt") + 1] == "# faber method"


def test_a_modes_subagents_are_registered(monkeypatch):
    """dev.md lists the Critic in its subagent roster and no Faber session
    could ever call it: a subagent has to be registered in the config root,
    and the config root was a copy with no agents dir in it."""
    import orchestrator.driver as driver
    monkeypatch.setattr(driver, "mode_agents", lambda mode: '{"critic": {}}')
    cmd = build_command(SessionSpec(mode="faber", prompt="x"))
    assert json.loads(cmd[cmd.index("--agents") + 1]) == {"critic": {}}


def test_an_unreadable_vault_costs_the_overlay_not_the_session(monkeypatch):
    """Non-fatal by design, and the flags are omitted rather than sent empty.

    A session with the base prompt and no overlay is a worse session; a
    session that fails to spawn is no session at all. Passing "" would be the
    third and worst option -- the CLI taking an empty override seriously.
    """
    import orchestrator.driver as driver
    monkeypatch.setattr(driver, "mode_methodology", lambda mode, job=None: "")
    monkeypatch.setattr(driver, "mode_agents", lambda mode: "")
    cmd = build_command(SessionSpec(mode="faber", prompt="x"))
    assert "--append-system-prompt" not in cmd and "--agents" not in cmd


def test_effort_is_passed_and_defaults_high():
    """dev.md has said "default high" since it was written, and nothing ever
    passed it -- so every session ran at the CLI's default and the rule
    described a setting no code applied."""
    cmd = build_command(SessionSpec(mode="faber", prompt="x"))
    assert cmd[cmd.index("--effort") + 1] == "high"
    cmd = build_command(SessionSpec(mode="faber", prompt="x", effort="xhigh"))
    assert cmd[cmd.index("--effort") + 1] == "xhigh"
    with pytest.raises(ValueError):
        SessionSpec(mode="faber", prompt="x", effort="turbo")


def test_the_telemetry_hooks_survive_the_config_root_change():
    """They lived in the per-mode settings.json, which is not read any more.

    Worth a test precisely because the failure is silent: a hook that stops
    firing reports nothing, and the action feed would simply have gone quiet.
    """
    from orchestrator.driver import settings_config
    hooks = json.loads(settings_config())["hooks"]
    assert set(hooks) == {"PostToolUse", "SessionEnd"}
    for event in hooks.values():
        command = event[0]["hooks"][0]["command"]
        assert Path(command.split()[0]).is_absolute()
        assert Path(command.split()[1]).exists(), "hook script must be there"


# ---------------------------------------------------------------- streaming

def test_streams_events_from_a_real_captured_stream():
    events = asyncio.run(_collect(launch(["cat", str(FIXTURE)])))
    assert isinstance(events[0], SessionStart)
    assert any(isinstance(e, TurnEnd) for e in events)
    assert session_id_of(events)


def test_missing_binary_reports_instead_of_raising():
    events = asyncio.run(_collect(launch(["definitely-not-a-real-binary-xyz"])))
    assert len(events) == 1
    assert isinstance(events[0], EngineError) and events[0].fatal


def test_nonzero_exit_is_surfaced_after_a_clean_stream():
    events = asyncio.run(_collect(launch(["sh", "-c", f"cat {FIXTURE}; exit 3"])))
    assert isinstance(events[-1], EngineError)
    assert "exited 3" in events[-1].message


def test_timeout_kills_a_silent_process():
    events = asyncio.run(_collect(launch(["sh", "-c", "sleep 30"], timeout=0.4)))
    assert isinstance(events[-1], EngineError) and events[-1].fatal
    assert "no output" in events[-1].message


# ---------------------------------------------------------------- manager

def _fake_runner(spec):
    async def gen():
        async for e in launch(["cat", str(FIXTURE)]):
            yield e
    return gen()


def test_manager_records_the_engine_id_so_the_session_can_resume():
    async def go():
        m = SessionManager(runner=_fake_runner)
        handle = None
        async for h, _ in m.start(SessionSpec(mode="faber", prompt="x")):
            handle = h
        return m, handle

    m, handle = asyncio.run(go())
    assert handle.state == "done"
    assert handle.resumable
    assert m.resume_spec(handle, "carry on", "manual").resume_id == handle.session_id


def test_manager_marks_a_fatal_run_failed_not_done():
    """A crashed session must never look identical to a clean one."""
    def failing(spec):
        async def gen():
            async for e in launch(["definitely-not-a-real-binary-xyz"]):
                yield e
        return gen()

    async def go():
        m = SessionManager(runner=failing)
        async for h, _ in m.start(SessionSpec(mode="faber", prompt="x")):
            pass
        return m

    m = asyncio.run(go())
    assert m.sessions[max(m.sessions)].state == "failed"


def test_third_session_queues_rather_than_running_or_being_refused():
    """The cap is a budget on the 5h window, not a resource limit -- so the
    third launch waits its turn instead of being rejected at the moment
    someone is trying to start work."""
    async def go():
        m = SessionManager(max_concurrent=2, runner=_slow_runner)
        seen = {}

        async def drive(tag):
            async for _h, _e in m.start(SessionSpec(mode="faber", prompt=tag)):
                seen.setdefault(tag, len(m.running))
                await asyncio.sleep(0)

        task = asyncio.gather(drive("a"), drive("b"), drive("c"))
        await asyncio.sleep(0.15)
        peak = len(m.running)
        queued_existed = peak == 2 and len(m.sessions) == 3
        await task
        return peak, queued_existed

    peak, queued_existed = asyncio.run(go())
    assert peak <= 2, f"concurrency budget exceeded: {peak} running"
    assert queued_existed, "third session should have been tracked while waiting"


def _slow_runner(spec):
    async def gen():
        async for e in launch(["sh", "-c", f"sleep 0.25; cat {FIXTURE}"]):
            yield e
    return gen()


def test_manager_keeps_the_latest_limits_for_the_status_line():
    async def go():
        m = SessionManager(runner=_fake_runner)
        async for _h, _e in m.start(SessionSpec(mode="faber", prompt="x")):
            pass
        return m

    m = asyncio.run(go())
    assert m.limits is not None
    assert 0.0 <= m.limits.five_hour_used <= 1.0


# ------------------------------------------------------- permission modes

def test_permission_mode_reaches_the_command_line():
    cmd = build_command(SessionSpec(mode="faber", prompt="x", permission_mode="plan"))
    assert cmd[cmd.index("--permission-mode") + 1] == "plan"


def test_default_permission_mode_asks():
    """Defaulting to anything more permissive would make the safest state the
    one you have to opt into."""
    assert SessionSpec(mode="faber", prompt="x").permission_mode == "manual"


def test_bypass_is_not_in_the_cycle():
    """It stays a settable flag, but must not be reachable by tapping a key."""
    from orchestrator.driver import PERMISSION_CYCLE
    assert "bypassPermissions" not in PERMISSION_CYCLE
    assert PERMISSION_CYCLE[0] == "plan"


def test_resume_takes_the_current_permission_mode_not_the_original():
    """The chip is a live control, not a birth certificate.

    This used to assert the opposite -- that a resume inherits the mode the
    session started with -- which would pin a session opened in `manual` to
    `manual` forever, however many times the chip was cycled afterwards. The
    old test passed and described a bug.
    """
    async def go():
        m = SessionManager(runner=_fake_runner)
        spec = SessionSpec(mode="faber", prompt="x", permission_mode="manual")
        async for h, _ in m.start(spec):
            handle = h
        return m.resume_spec(handle, "more", "acceptEdits")

    assert asyncio.run(go()).permission_mode == "acceptEdits"


# ------------------------------------------------- pre-allowed tools

def test_read_and_web_tools_are_pre_allowed():
    """Anything that would prompt is denied, because this driver passes
    --permission-prompts none: there is no host to answer. WebSearch failed
    with 'you haven't granted it yet' and no way to grant it, so the tools a
    mode should always have are allowed at spawn."""
    cmd = build_command(SessionSpec(mode="general", prompt="x"))
    allowed = cmd[cmd.index("--allowedTools") + 1]
    assert "WebSearch" in allowed and "Read" in allowed


def test_every_mode_gets_the_same_tools():
    """Capability is not the axis the modes vary on -- methodology is.

    Each mode reads its own composed CLAUDE.md, and that is what makes Noctua
    research and Faber build. Varying the tool surface on top of it produced a
    mode handed a task it could not perform, with no way to say so: the turn
    tried, was refused, ended with nothing done, and drew a blank transcript
    that looked exactly like a crash.
    """
    surfaces = {mode: MODE_TOOLS[mode]["allowed"] for mode in MODE_MODELS}
    assert len(set(surfaces.values())) == 1, f"modes differ in capability: {surfaces}"


def test_no_mode_is_caged():
    """--disallowedTools is gone. A guardrail that belongs to everyone lives
    in permissions.json; one that belongs to a single mode was the bug."""
    for mode in MODE_MODELS:
        assert not MODE_TOOLS[mode].get("disallowed"), f"{mode} is still caged"
        cmd = build_command(SessionSpec(mode=mode, prompt="x"))
        assert "--disallowedTools" not in cmd


def test_every_mode_can_actually_do_the_work():
    """The tools a session needs to change anything, present for all five."""
    for mode in MODE_MODELS:
        allowed = MODE_TOOLS[mode]["allowed"]
        for tool in ("Bash", "Edit", "Write", "Read", "WebSearch"):
            assert tool in allowed, f"{mode} cannot use {tool}"


# ------------------------------------------------- who answers a prompt

def test_permission_requests_are_routed_to_the_prompt_tool():
    """The flag decides *who answers*. It was "none" -- nobody -- so every
    request was refused and the chip's labels were fiction: manual meant
    never, and acceptEdits could not write. "host" hands the question to the
    prompt tool, which asks the person."""
    cmd = build_command(SessionSpec(mode="faber", prompt="x"))
    assert cmd[cmd.index("--permission-prompts") + 1] == "host"
    assert cmd[cmd.index("--permission-prompt-tool") + 1] == "mcp__noctis__permission_prompt"


def test_the_mcp_server_is_attached_to_every_spawn():
    """It was built in Stage 2 item 2 and never wired to a session: no
    --mcp-config, no .mcp.json in any config dir. vault_search existed and
    nothing could call it, so sessions ran without the retrieval the design
    rests on -- and the permission tool needs the same channel."""
    import json as _json
    from orchestrator.driver import MCP_SERVER
    cmd = build_command(SessionSpec(mode="faber", prompt="x"))
    cfg = _json.loads(cmd[cmd.index("--mcp-config") + 1])
    assert str(MCP_SERVER) in cfg["mcpServers"]["noctis"]["args"]
    assert MCP_SERVER.exists(), "the spawn points at a server that is not there"


def test_the_tracked_policy_reaches_the_spawn():
    """Passed as inline JSON rather than a path: the hooks composed in beside
    it need absolute machine paths, which is exactly what cannot be committed.
    The policy half stays a tracked file so it is reviewable in a diff."""
    from orchestrator.driver import SHARED_SETTINGS, settings_config
    cmd = build_command(SessionSpec(mode="faber", prompt="x"))
    sent = json.loads(cmd[cmd.index("--settings") + 1])
    assert SHARED_SETTINGS.exists(), "the tracked policy must be there"
    assert sent["permissions"] == json.loads(SHARED_SETTINGS.read_text())["permissions"]
    assert settings_config()


def test_inbound_peer_messages_are_accepted_by_decision():
    """Set explicitly, because the default reaches the same place by accident.

    With the key absent, delivery falls out of comparing permission mode
    classes: only bypassPermissions counts as bypassing, PERMISSION_CYCLE
    excludes it, so a spawned session sits in the prompting class and messages
    arrive. Right answer, wrong reason -- it survives only while an unrelated
    tuple keeps its contents, and a `-p` session cannot approve anything that
    does get held, so a held message expires unseen in five minutes.

    The value is checked against the engine's own enum rather than merely
    being non-empty: an unrecognised value does not fail the settings parse
    (the field catches to undefined), it silently reverts to holding, which is
    the failure this test exists to catch early.
    """
    from orchestrator.driver import SHARED_SETTINGS
    tracked = json.loads(SHARED_SETTINGS.read_text())
    assert tracked.get("crossSessionInbound") == "accept"
    for mode in MODE_MODELS:
        cmd = build_command(SessionSpec(mode=mode, prompt="x"))
        sent = json.loads(cmd[cmd.index("--settings") + 1])
        assert sent.get("crossSessionInbound") in ("accept", "hold", "refuse"), mode
        assert sent["crossSessionInbound"] == "accept", mode


def test_composing_the_hooks_keeps_every_other_policy_key():
    """The hooks are added to the tracked policy, not substituted for it.

    `settings_config` loads the file and assigns one key. Anything else in
    there -- crossSessionInbound today, whatever is added next -- has to
    survive that, and a `{"permissions": ..., "hooks": ...}` literal built
    fresh would drop it without failing anything.
    """
    from orchestrator.driver import SHARED_SETTINGS, settings_config
    tracked = json.loads(SHARED_SETTINGS.read_text())
    composed = json.loads(settings_config())
    for key, value in tracked.items():
        assert composed[key] == value, f"{key} was lost composing the hooks"


def test_every_mode_gets_the_same_permission_plumbing():
    """One file, five modes, no per-mode special case.

    The whole defect this replaced was permissions that silently applied to
    nothing, so "it happens to be unconditional today" is not good enough: a
    mode added later, or a well-meant `if spec.mode == ...`, would reintroduce
    exactly the failure -- one mode quietly unable to act while the interface
    says otherwise.
    """
    from orchestrator.driver import PERMISSION_TOOL, SHARED_SETTINGS
    for mode in MODE_MODELS:
        cmd = build_command(SessionSpec(mode=mode, prompt="x"))
        assert cmd[cmd.index("--permission-prompts") + 1] == "host", mode
        assert cmd[cmd.index("--permission-prompt-tool") + 1] == PERMISSION_TOOL, mode
        assert json.loads(cmd[cmd.index("--settings") + 1])["permissions"] == \
            json.loads(SHARED_SETTINGS.read_text())["permissions"], mode
        assert "--mcp-config" in cmd, mode


def _shared_permissions() -> dict:
    import json
    from orchestrator.driver import SHARED_SETTINGS
    return json.loads(SHARED_SETTINGS.read_text())["permissions"]


def test_shared_settings_allow_edit_and_write_and_this_costs_the_chip():
    """A recorded concession, not a preference.

    This asserted the opposite first: that Edit and Write must never be listed
    here, because the chip has to keep meaning something in *both* directions
    and a blanket allow makes `manual` and `plan` permit edits anyway.

    It was tried and it does not work. With `--permission-prompts none` and
    the chip on acceptEdits, writes were still refused -- so leaving Edit and
    Write to the permission mode leaves Faber unable to write at all, which is
    a worse failure than a chip that under-blocks. Verified live: the same
    session could write before the shared file took precedence and not after.

    So the allow list grants them, and the price is real -- `manual` and `plan`
    no longer refuse edits. The honest fix is a host that answers permission
    requests (--permission-prompt-tool), at which point this test should go
    back to asserting absence. Until then it exists to make sure the trade
    stays deliberate rather than becoming a thing nobody remembers choosing.
    """
    allowed = _shared_permissions()["allow"]
    assert "Edit" in allowed and "Write" in allowed


def test_shared_settings_deny_git_push():
    """dev.md's 'commits as work progresses, Shayne pushes' was a rule in a
    markdown file that a session could simply not follow. Here it is a fact
    about what the process may do."""
    assert any("git push" in rule for rule in _shared_permissions()["deny"])


def test_the_shared_allowlist_applies_to_every_mode():
    """One tracked list, not five config dirs that drift. Whatever is granted
    is granted identically everywhere -- which is the whole point of moving
    the difference between modes into their methodology."""
    from orchestrator.driver import SHARED_SETTINGS
    for mode in MODE_MODELS:
        cmd = build_command(SessionSpec(mode=mode, prompt="x"))
        assert json.loads(cmd[cmd.index("--settings") + 1])["permissions"] == \
            json.loads(SHARED_SETTINGS.read_text())["permissions"]


def test_a_line_larger_than_asyncios_default_is_read(tmp_path):
    """stream-json puts a whole tool result on one line, and asyncio's
    StreamReader defaults to 64KB. A Read of any sizeable file overran it and
    readline() raised "Separator is not found, and chunk exceed the limit",
    killing the session mid-turn -- found when a pasted screenshot did it."""
    import json as _json

    big = "x" * (300 * 1024)          # ~5x the old limit
    line = _json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": big}]},
    })
    fixture = tmp_path / "big.jsonl"
    fixture.write_text(line + "\n")

    events = asyncio.run(_collect(launch(["cat", str(fixture)])))
    texts = [e for e in events if isinstance(e, TextDelta)]
    assert texts and len(texts[0].text) == len(big)
    assert not any(isinstance(e, EngineError) for e in events)


# ------------------------------------------------------- inline images

def _png() -> Image:
    return Image(media_type="image/png", data="aGVsbG8=")


def test_a_turn_with_images_takes_its_prompt_on_stdin():
    """--input-format stream-json is the only way to attach a picture to a
    turn without writing it to disk first, and it takes the message from
    stdin rather than argv."""
    cmd = build_command(SessionSpec(mode="general", prompt="what is this?", images=[_png()]))
    assert "--input-format" in cmd and cmd[cmd.index("--input-format") + 1] == "stream-json"
    assert "what is this?" not in cmd          # the prompt is not on the command line


def test_a_text_turn_keeps_the_simple_command():
    cmd = build_command(SessionSpec(mode="general", prompt="hello"))
    assert "--input-format" not in cmd
    assert cmd[2] == "hello"


def test_stdin_carries_the_text_and_every_image():
    import json as _json

    spec = SessionSpec(mode="general", prompt="two pictures", images=[_png(), _png()])
    content = _json.loads(build_stdin(spec))["message"]["content"]
    assert content[0] == {"type": "text", "text": "two pictures"}
    assert [c["type"] for c in content] == ["text", "image", "image"]
    assert content[1]["source"] == {"type": "base64", "media_type": "image/png", "data": "aGVsbG8="}


def test_a_text_turn_writes_nothing_to_the_process():
    """No images means the ordinary path, with nothing written at all."""
    assert build_stdin(SessionSpec(mode="general", prompt="hello")) is None


# --------------------------------------------------- per-session model

def test_a_session_can_override_its_mode_model():
    """dev.md's effort routing expressed as model routing, made reachable
    rather than a launcher-only override."""
    cmd = build_command(SessionSpec(mode="faber", prompt="x", model="claude-haiku-4-5"))
    assert cmd[cmd.index("--model") + 1] == "claude-haiku-4-5"


def test_without_an_override_the_mode_decides():
    spec = SessionSpec(mode="faber", prompt="x")
    assert spec.resolved_model == MODE_MODELS["faber"]


def test_an_unknown_model_is_refused_at_construction():
    """Passing it through means a spawn that fails seconds later with a much
    less obvious message."""
    with pytest.raises(ValueError):
        SessionSpec(mode="faber", prompt="x", model="gpt-9")


def test_the_vault_is_reachable_from_any_session():
    """The engine sandboxes file access to the working directory. Without
    the vault added, a Faber session in a repo cannot read its own
    methodology, job context or lessons — the half of the system it is meant
    to think with. The flag existed and nothing set it."""
    from pathlib import Path as _Path

    cmd = build_command(SessionSpec(mode="faber", prompt="x", vault_path=_Path("/vault")))
    assert cmd[cmd.index("--add-dir") + 1] == "/vault"


def test_only_the_vault_is_added():
    """Widening further would trade away the sandbox, which is doing real
    work: a session refusing to read the home folder is it behaving."""
    cmd = build_command(SessionSpec(mode="faber", prompt="x", vault_path=Path("/vault")))
    assert cmd.count("--add-dir") == 1


# ------------------------------------------------------- silent turns

def _turn_end() -> TurnEnd:
    return TurnEnd(session_id="s", usage=Usage(0, 0, 0, "m"), duration_ms=1)


async def _stream(*events):
    for e in events:
        yield e


def test_a_turn_that_says_nothing_is_marked_silent():
    """The failure this exists for: tool calls, no text, turn over.

    The shell renders the transcript, so this turn drew a blank screen that
    looked exactly like a dead backend. It is a legal shape, and the only fix
    that holds is making it a fact on the event rather than an absence.
    """
    events = asyncio.run(_collect(with_turn_totals(_stream(
        ToolCall(id="1", name="Bash", args={"command": "ls"}),
        ToolResult(id="1", content="a.txt"),
        ToolCall(id="2", name="Read", args={"file_path": "a.txt"}),
        ToolResult(id="2", content="hello"),
        _turn_end(),
    ))))
    end = events[-1]
    assert end.silent
    assert end.text_chars == 0
    assert end.tool_calls == 2


def test_a_turn_that_replies_is_not_silent():
    events = asyncio.run(_collect(with_turn_totals(_stream(
        ToolCall(id="1", name="Bash", args={"command": "ls"}),
        TextDelta("here is what I found"),
        _turn_end(),
    ))))
    end = events[-1]
    assert not end.silent
    assert end.text_chars == len("here is what I found")
    assert end.tool_calls == 1


def test_counts_reset_between_turns_in_one_run():
    """A resumed run carries several turns; a reply in the first must not
    make a silent second one look answered."""
    events = asyncio.run(_collect(with_turn_totals(_stream(
        TextDelta("first turn spoke"),
        _turn_end(),
        ToolCall(id="1", name="Bash", args={"command": "ls"}),
        _turn_end(),
    ))))
    first, second = [e for e in events if isinstance(e, TurnEnd)]
    assert not first.silent
    assert second.silent and second.tool_calls == 1


def test_whitespace_only_text_still_counts_as_a_reply():
    """Deliberate: the check is "did the engine emit text", not a judgement
    about whether the text was worth reading. Anything cleverer would be the
    same guesswork this replaced."""
    events = asyncio.run(_collect(with_turn_totals(_stream(
        TextDelta(" "), _turn_end(),
    ))))
    assert not events[-1].silent


def test_a_turn_that_narrates_then_stops_on_a_tool_is_still_unfinished():
    """The shape the first version of this missed, and the common one.

    Counting text across the whole turn made any mid-turn narration mark the
    turn as fine. But whether it spoke earlier says nothing about whether it
    finished: run six tools with commentary, run a seventh, stop, and what is
    on screen is "Ran 1 shell command" with no word about what it found.
    Observed live on 2026-09-12, a day after the narrow fix shipped.
    """
    events = asyncio.run(_collect(with_turn_totals(_stream(
        TextDelta("Now verifying — the original repro and both suites:"),
        ToolCall(id="1", name="Bash", args={"command": "make test"}),
        TextDelta("0/24 failures. Now the end-to-end HTTP test:"),
        ToolCall(id="2", name="Bash", args={"command": "curl ..."}),
        _turn_end(),
    ))))
    end = events[-1]
    assert not end.silent, "it spoke, so the narrow check cannot catch this"
    assert end.unclosed, "and it still ended without saying what happened"
    assert end.text_after_last_tool == 0


def test_a_turn_closed_after_its_last_tool_is_finished():
    events = asyncio.run(_collect(with_turn_totals(_stream(
        ToolCall(id="1", name="Bash", args={"command": "make test"}),
        TextDelta("All green: 426 backend, 79 frontend."),
        _turn_end(),
    ))))
    assert not events[-1].unclosed


def test_a_turn_with_no_tools_is_never_unclosed():
    """Plain conversation closes itself. Only a trailing tool call leaves
    something dangling."""
    events = asyncio.run(_collect(with_turn_totals(_stream(
        TextDelta("here you go"), _turn_end(),
    ))))
    assert not events[-1].unclosed


def test_the_trailing_counter_resets_between_turns():
    events = asyncio.run(_collect(with_turn_totals(_stream(
        ToolCall(id="1", name="Bash", args={}), TextDelta("closed properly"),
        _turn_end(),
        ToolCall(id="2", name="Bash", args={}),
        _turn_end(),
    ))))
    first, second = [e for e in events if isinstance(e, TurnEnd)]
    assert not first.unclosed
    assert second.unclosed


# ------------------------------------------- closing a turn that did not

def _unclosed_run(prompt_seen: list):
    """A runner whose first turn ends on a tool call and whose continuation
    closes properly — the shape observed live on 2026-09-12."""
    async def runner(spec):
        prompt_seen.append(spec.prompt)
        if spec.continuation:
            yield TextDelta("Ran the suite: 431 passing. Nothing left open.")
            yield TurnEnd(session_id="s1", usage=Usage(0, 0, 0, "m"), duration_ms=1,
                          text_chars=48, tool_calls=0, text_after_last_tool=48)
            return
        yield SessionStart(session_id="s1", model="m", cwd="/x")
        yield TextDelta("Now verifying:")
        yield ToolCall(id="1", name="Bash", args={"command": "make test"})
        yield TurnEnd(session_id="s1", usage=Usage(0, 0, 0, "m"), duration_ms=1,
                      text_chars=14, tool_calls=1, text_after_last_tool=0)
    return runner


def test_a_turn_that_does_not_close_itself_gets_closed():
    """The Stop hook Noctis cannot have. `Stop` fires at the end of every turn
    and can refuse the stop, but not under --print, and the SDK that does
    support hooks needs API-key auth — the metered path the architecture
    exists to avoid. So the manager does it where a turn's end is known."""
    seen: list = []
    mgr = SessionManager(runner=_unclosed_run(seen))

    async def go():
        return [e async for _h, e in mgr.start(SessionSpec(mode="faber", prompt="build"))]

    events = asyncio.run(go())
    assert len(seen) == 2, "the continuation should have been sent"
    assert "handback" in seen[1], "and it should carry system.md's rule"
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "431 passing" in text, "the close lands in the same transcript"


def test_the_continuation_cannot_trigger_another():
    """The loop guard, and the reason it is needed: a continuation is itself
    a turn, so without a flag it qualifies for a continuation of its own."""
    seen: list = []

    async def always_unclosed(spec):
        seen.append(spec.continuation)
        yield SessionStart(session_id="s1", model="m", cwd="/x")
        yield ToolCall(id="1", name="Bash", args={})
        yield TurnEnd(session_id="s1", usage=Usage(0, 0, 0, "m"), duration_ms=1,
                      text_chars=0, tool_calls=1, text_after_last_tool=0)

    mgr = SessionManager(runner=always_unclosed)

    async def go():
        return [e async for _h, e in mgr.start(SessionSpec(mode="faber", prompt="x"))]

    asyncio.run(go())
    assert seen == [False, True], "exactly one continuation, never a third"


def test_a_turn_that_already_closed_answers_closed_and_shows_nothing():
    """Every working turn is asked, because whether prose amounts to a
    handback is not mechanically decidable -- the only reader qualified to
    judge is the one that wrote it. A turn that did close answers `closed`,
    and that word must never reach the transcript."""
    async def runner(spec):
        if spec.continuation:
            yield TextDelta("closed")
            yield TurnEnd(session_id="s1", usage=Usage(0, 0, 0, "m"), duration_ms=1)
            return
        yield SessionStart(session_id="s1", model="m", cwd="/x")
        yield ToolCall(id="1", name="Bash", args={})
        yield TextDelta("Done — all green. Next: push.")
        yield TurnEnd(session_id="s1", usage=Usage(0, 0, 0, "m"), duration_ms=1,
                      text_chars=29, tool_calls=1, text_after_last_tool=29)

    mgr = SessionManager(runner=runner)

    async def go():
        return [e async for _h, e in mgr.start(SessionSpec(mode="faber", prompt="x"))]

    events = asyncio.run(go())
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert "closed" not in text.lower(), "the escape word is not transcript content"
    assert "all green" in text


def test_a_turn_with_no_tools_is_not_asked_to_close():
    """Plain conversation closes itself by existing. Asking would spend a
    spawn to be told nothing."""
    seen: list = []

    async def chat(spec):
        seen.append(spec.continuation)
        yield SessionStart(session_id="s1", model="m", cwd="/x")
        yield TextDelta("Here is the answer.")
        yield TurnEnd(session_id="s1", usage=Usage(0, 0, 0, "m"), duration_ms=1,
                      text_chars=19, tool_calls=0, text_after_last_tool=19)

    mgr = SessionManager(runner=chat)

    async def go():
        return [e async for _h, e in mgr.start(SessionSpec(mode="faber", prompt="x"))]

    asyncio.run(go())
    assert seen == [False], "no continuation for a turn that used no tools"


def test_a_failing_close_leaves_the_turn_it_was_helping():
    """The close is a courtesy on top of a turn that already happened. If the
    engine will not spawn, the right outcome is the transcript the user
    already has -- not an error about the thing that was trying to help."""
    async def runner(spec):
        if spec.continuation:
            yield EngineError("could not start engine", fatal=True)
            return
        yield SessionStart(session_id="s1", model="m", cwd="/x")
        yield TextDelta("real work")
        yield ToolCall(id="1", name="Bash", args={})
        yield TurnEnd(session_id="s1", usage=Usage(0, 0, 0, "m"), duration_ms=1,
                      text_chars=9, tool_calls=1, text_after_last_tool=0)

    mgr = SessionManager(runner=runner)

    async def go():
        return [e async for _h, e in mgr.start(SessionSpec(mode="faber", prompt="x"))]

    events = asyncio.run(go())
    assert not any(isinstance(e, EngineError) for e in events)
    assert any(isinstance(e, TextDelta) for e in events)


def test_no_session_id_means_nothing_to_resume():
    """A run that died before reporting one cannot be continued, and must not
    raise trying."""
    async def runner(spec):
        yield TurnEnd(session_id="", usage=Usage(0, 0, 0, "m"), duration_ms=1,
                      text_chars=0, tool_calls=1, text_after_last_tool=0)

    mgr = SessionManager(runner=runner)

    async def go():
        return [e async for _h, e in mgr.start(SessionSpec(mode="faber", prompt="x"))]

    asyncio.run(go())      # must not raise


def test_the_recap_helper_also_uses_the_real_config_root(monkeypatch):
    """It was the last place the redirect survived. A summariser pointed at
    launch_config/general depended on a directory that is otherwise dead and
    safe to delete -- which would have surfaced as "Not logged in" from the
    recap, of all things.

    Its tool cage is a different thing and stays: `one_shot` summarises text
    handed to it, and a summariser that can read the filesystem is a larger
    thing than the job needs. That is a cage on a helper, not on a mode.
    """
    import inspect

    import orchestrator.driver as driver
    source = inspect.getsource(driver.one_shot)
    assert 'env["CLAUDE_CONFIG_DIR"]' not in source
    assert "--disallowedTools" in source, "the summariser stays caged"


def test_the_concurrency_cap_is_a_budget_not_a_constant(monkeypatch):
    """It was 2, and 2 was never chosen on its merits: each mode had a config
    dir whose CLAUDE.md was rewritten per launch, so two sessions of one mode
    would have raced on that file. Nothing per-mode is written to disk now, so
    the reason the number was small is gone -- and the number itself depends
    on the plan rather than on the code.

    Read at construction rather than at import: a module constant binds into
    `__init__`'s default before `.env` is necessarily loaded, so the setting
    would work or not depending on import order.
    """
    from orchestrator.manager import DEFAULT_MAX_CONCURRENT

    assert DEFAULT_MAX_CONCURRENT >= 2, "never fewer than the old default"
    assert SessionManager().max_concurrent == DEFAULT_MAX_CONCURRENT

    monkeypatch.setenv("NOCTIS_MAX_CONCURRENT", "7")
    assert SessionManager().max_concurrent == 7, "no reload required"

    monkeypatch.setenv("NOCTIS_MAX_CONCURRENT", "nonsense")
    assert SessionManager().max_concurrent == DEFAULT_MAX_CONCURRENT, "bad value falls back"

    monkeypatch.setenv("NOCTIS_MAX_CONCURRENT", "0")
    assert SessionManager().max_concurrent == 1, "a cap of zero would run nothing"


def test_the_setting_has_a_ceiling_and_says_when_it_bites(monkeypatch, caplog):
    """An unbounded env var is how a typo becomes a quota incident: `=40`
    would be honoured silently and spend the 5-hour window in an afternoon.

    Clamped rather than refused -- starting with fewer beats not starting --
    and the warning names the constant to change, because the capability is
    only useful if you can find it a month later.
    """
    from orchestrator.manager import MAX_CONCURRENT_CEILING

    monkeypatch.setenv("NOCTIS_MAX_CONCURRENT", str(MAX_CONCURRENT_CEILING))
    assert SessionManager().max_concurrent == MAX_CONCURRENT_CEILING, "the ceiling itself is fine"

    monkeypatch.setenv("NOCTIS_MAX_CONCURRENT", "40")
    with caplog.at_level("WARNING"):
        assert SessionManager().max_concurrent == MAX_CONCURRENT_CEILING
    assert "MAX_CONCURRENT_CEILING" in caplog.text, "the warning must name what to change"


def test_two_sessions_of_one_mode_run_together():
    """Same-mode concurrency, which the per-mode config dirs made unsafe and
    their removal made ordinary. Two Faber tabs on two repositories is the
    case; two on one repository is the other."""
    async def runner(spec):
        yield SessionStart(session_id=f"s-{spec.cwd}", model="m", cwd=str(spec.cwd))
        yield TextDelta("done")
        yield TurnEnd(session_id=f"s-{spec.cwd}", usage=Usage(0, 0, 0, "m"),
                      duration_ms=1, text_chars=4, tool_calls=0,
                      text_after_last_tool=4)

    mgr = SessionManager(runner=runner)

    async def go():
        a = [e async for _h, e in mgr.start(SessionSpec(mode="faber", prompt="x",
                                                        cwd=Path("/one")))]
        b = [e async for _h, e in mgr.start(SessionSpec(mode="faber", prompt="y",
                                                        cwd=Path("/two")))]
        return a, b

    a, b = asyncio.run(go())
    assert any(isinstance(e, TextDelta) for e in a)
    assert any(isinstance(e, TextDelta) for e in b)
    assert len(mgr.by_mode("faber")) == 2, "both handles are tracked, not one replacing the other"
