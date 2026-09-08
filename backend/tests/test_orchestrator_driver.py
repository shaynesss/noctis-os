"""Driver and manager tests — Noctis v2 Stage 2 item 1.

The streaming path is exercised end to end with `cat fixture.jsonl` instead
of the real CLI: same async subprocess, same line reading, same parsing, no
quota and no network. `build_command` is pure and asserted directly.
"""
import asyncio
from pathlib import Path

import pytest

from orchestrator.driver import (
    MODE_MODELS, SessionSpec, build_command, build_env, claude_binary, launch,
    session_id_of,
)
from orchestrator.events import EngineError, SessionStart, TurnEnd
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


def test_maintenance_is_caged_not_merely_instructed():
    """propose-never-apply failed a plainly-worded request in the regression
    suite, so the tool policy enforces it rather than trusting the prompt."""
    cmd = build_command(SessionSpec(mode="maintenance", prompt="x"))
    disallowed = cmd[cmd.index("--disallowedTools") + 1]
    assert "Edit" in disallowed and "Write" in disallowed


def test_faber_keeps_the_full_tool_surface():
    cmd = build_command(SessionSpec(mode="faber", prompt="x"))
    assert "--disallowedTools" not in cmd


def test_unknown_mode_is_rejected_at_construction():
    with pytest.raises(ValueError):
        SessionSpec(mode="nonsense", prompt="x")


def test_env_points_at_the_modes_own_config_dir():
    env = build_env(SessionSpec(mode="noctua", prompt="x"))
    assert env["CLAUDE_CONFIG_DIR"].endswith("launch_config/noctua")
    assert env["NOCTIS_MODE"] == "noctua"      # the telemetry hooks read this


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
    assert m.resume_spec(handle, "carry on").resume_id == handle.session_id


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


def test_resume_preserves_the_permission_mode():
    async def go():
        m = SessionManager(runner=_fake_runner)
        spec = SessionSpec(mode="faber", prompt="x", permission_mode="acceptEdits")
        async for h, _ in m.start(spec):
            handle = h
        return m.resume_spec(handle, "more")

    assert asyncio.run(go()).permission_mode == "acceptEdits"
