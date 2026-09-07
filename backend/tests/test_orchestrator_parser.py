"""Parser tests — Noctis v2 Stage 2 item 1.

Run against a real captured stream rather than hand-written JSON, so the
tests fail if the CLI's actual shape drifts (risk 10) instead of only if our
idea of it does. Regenerate the fixture with:

    claude -p "..." --output-format stream-json --verbose > fixture.jsonl
"""
from pathlib import Path

import pytest

from orchestrator.events import (
    EngineError, Limits, SessionStart, TextDelta, ThinkingDelta,
    ThinkingProgress, ToolCall, ToolResult, TurnEnd,
)
from orchestrator.parser import parse_line, parse_stream

FIXTURE = Path(__file__).parent / "fixtures" / "stream_with_tools.jsonl"


@pytest.fixture(scope="module")
def events():
    return list(parse_stream(FIXTURE.read_text().splitlines()))


def _of(events, cls):
    return [e for e in events if isinstance(e, cls)]


def test_fixture_yields_every_event_type(events):
    for cls in (SessionStart, ThinkingDelta, ToolCall, ToolResult, TextDelta, Limits, TurnEnd):
        assert _of(events, cls), f"no {cls.__name__} parsed from the fixture"


def test_session_start_is_first_and_carries_resume_id(events):
    assert isinstance(events[0], SessionStart)
    assert events[0].session_id  # what --resume takes
    assert events[0].model


def test_tool_call_and_result_pair_up_by_id(events):
    calls = {c.id for c in _of(events, ToolCall)}
    results = {r.id for r in _of(events, ToolResult)}
    assert calls and results
    assert results <= calls, "a tool_result arrived with no matching tool_use id"


def test_tool_result_comes_from_a_user_event_not_an_assistant_one():
    """The shape most likely to be got wrong when writing from assumption."""
    line = (
        '{"type":"user","message":{"content":[{"type":"tool_result",'
        '"tool_use_id":"tu_1","content":"hello"}]}}'
    )
    (ev,) = parse_line(line)
    assert isinstance(ev, ToolResult)
    assert ev.id == "tu_1" and ev.content == "hello"


def test_one_assistant_line_can_yield_several_events():
    line = (
        '{"type":"assistant","message":{"content":['
        '{"type":"thinking","thinking":"weighing it up"},'
        '{"type":"tool_use","id":"tu_9","name":"Read","input":{"file_path":"/tmp/x.py"}},'
        '{"type":"text","text":"done"}]}}'
    )
    out = parse_line(line)
    assert [type(e) for e in out] == [ThinkingDelta, ToolCall, TextDelta]


def test_tool_call_summary_picks_the_meaningful_argument():
    (call,) = parse_line(
        '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t",'
        '"name":"Read","input":{"file_path":"/very/long/path.py","limit":10}}]}}'
    )
    assert call.summary == "/very/long/path.py"


def test_limits_carry_both_windows(events):
    (lim,) = _of(events, Limits)
    assert 0.0 <= lim.five_hour_used <= 1.0
    assert lim.five_hour_resets_at > 0
    assert lim.seven_day_resets_at > 0


def test_turn_end_reports_usage_without_a_cost_field(events):
    (end,) = _of(events, TurnEnd)
    assert end.usage.cached_tokens > 0, "cache reads dominate this workload"
    assert not hasattr(end.usage, "cost_usd")


def test_flattens_list_shaped_tool_result_content():
    (ev,) = parse_line(
        '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t",'
        '"content":[{"type":"text","text":"line one"},{"type":"text","text":"line two"}]}]}}'
    )
    assert ev.content == "line one\nline two"


def test_error_result_reports_the_failure_and_keeps_the_usage():
    out = parse_line(
        '{"type":"result","subtype":"error","is_error":true,"result":"boom",'
        '"session_id":"s1","duration_ms":5,"usage":{"input_tokens":1,"output_tokens":2}}'
    )
    assert isinstance(out[0], TurnEnd)
    assert isinstance(out[1], EngineError) and out[1].fatal


def test_malformed_line_becomes_an_error_not_an_exception():
    (ev,) = parse_line("{not json at all")
    assert isinstance(ev, EngineError) and not ev.fatal


def test_blank_and_bookkeeping_lines_yield_nothing():
    assert parse_line("") == []
    assert parse_line('{"type":"system","subtype":"hook_started"}') == []
    assert parse_line('{"type":"system","subtype":"status"}') == []


def test_thinking_text_is_empty_by_default_and_that_is_expected(events):
    """Models default to display:"omitted" -- reasoning is billed but never
    returned, and the CLI exposes no flag to change it. The block is still
    emitted because its presence means the model reasoned."""
    blocks = _of(events, ThinkingDelta)
    assert blocks, "thinking blocks should still be emitted"
    assert all(b.text == "" for b in blocks), (
        "thinking text became available -- the UI can show real reasoning now; "
        "revisit the 'visible activity, not visible text' note in the spec"
    )


def test_thinking_progress_gives_a_live_counter():
    (ev,) = parse_line('{"type":"system","subtype":"thinking_tokens","estimated_tokens":250}')
    assert isinstance(ev, ThinkingProgress) and ev.estimated_tokens == 250
