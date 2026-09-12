"""Parser tests — Noctis v2 Stage 2 item 1.

Run against a real captured stream rather than hand-written JSON, so the
tests fail if the CLI's actual shape drifts (risk 10) instead of only if our
idea of it does. Regenerate the fixture with:

    claude -p "..." --output-format stream-json --verbose > fixture.jsonl
"""
import json
from pathlib import Path

import pytest

from orchestrator.events import (
    ContextSnapshot, EngineError, Limits, SessionStart, TextDelta,
    ThinkingDelta, ThinkingProgress, ToolCall, ToolResult, TurnEnd,
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


# --------------------------------------------------- multi-model turns

def _multi_model_result():
    """A real `result` line captured live on 2026-09-08, where the CLI billed
    a background haiku task alongside the opus turn."""
    return (Path(__file__).parent / "fixtures" / "result_multi_model.json").read_text()


def test_turn_end_names_the_model_that_actually_answered():
    """`modelUsage` is keyed by model and its first key was the *background*
    tier, so the turn was labelled haiku while the token counts beside it
    were opus's -- the name and the numbers disagreed."""
    (end,) = [e for e in parse_line(_multi_model_result()) if isinstance(e, TurnEnd)]
    assert end.usage.model == "claude-opus-5"


def test_background_model_tokens_are_not_silently_dropped():
    """Top-level `usage` is only the primary model's, so reporting it alone
    lost ~900 input tokens per turn from any lifetime total."""
    (end,) = [e for e in parse_line(_multi_model_result()) if isinstance(e, TurnEnd)]
    assert end.usage.aux_input_tokens == 903
    assert end.usage.aux_output_tokens == 12
    assert end.usage.total_input == end.usage.input_tokens + 903


def test_primary_falls_back_to_largest_output_when_nothing_matches():
    """The exact match is on top-level usage; if that shape ever stops
    holding, the model that produced the most output is the one that
    answered -- never dict order again."""
    line = json.dumps({
        "type": "result", "session_id": "s", "duration_ms": 1,
        "usage": {"input_tokens": 999, "output_tokens": 999},
        "modelUsage": {
            "cheap-model": {"inputTokens": 900, "outputTokens": 12},
            "real-model": {"inputTokens": 2, "outputTokens": 500},
        },
    })
    (end,) = [e for e in parse_line(line) if isinstance(e, TurnEnd)]
    assert end.usage.model == "real-model"


def test_single_model_turn_reports_no_aux():
    line = json.dumps({
        "type": "result", "session_id": "s", "duration_ms": 1,
        "usage": {"input_tokens": 2, "output_tokens": 4},
        "modelUsage": {"claude-opus-5": {"inputTokens": 2, "outputTokens": 4}},
    })
    (end,) = [e for e in parse_line(line) if isinstance(e, TurnEnd)]
    assert end.usage.model == "claude-opus-5"
    assert end.usage.aux_input_tokens == 0


def test_missing_model_usage_does_not_crash():
    line = json.dumps({"type": "result", "session_id": "s", "duration_ms": 1,
                       "usage": {"input_tokens": 1, "output_tokens": 1}})
    (end,) = [e for e in parse_line(line) if isinstance(e, TurnEnd)]
    assert end.usage.model == ""


def test_the_result_event_carries_a_window_but_no_occupancy():
    """The result's usage is cumulative over every API call the turn made, so
    it cannot say how full the window is. It used to try: input + cache reads
    + cache writes, divided by the window, which read 470% on a real turn that
    ran fifteen tools. Only the window survives here; occupancy comes from
    ContextSnapshot."""
    (end,) = [e for e in parse_line(_multi_model_result()) if isinstance(e, TurnEnd)]
    assert end.usage.context_window == 1_000_000
    assert not hasattr(end.usage, "context_tokens")


def test_unknown_context_window_is_not_reported_as_empty():
    """No window means unknown, and the UI must show it as unknown rather
    than as 0% -- which would read as a conversation with room to spare."""
    line = json.dumps({"type": "result", "session_id": "s", "duration_ms": 1,
                       "usage": {"input_tokens": 5, "output_tokens": 1}})
    (end,) = [e for e in parse_line(line) if isinstance(e, TurnEnd)]
    assert end.usage.context_window == 0


def test_an_assistant_message_reports_occupancy_at_that_moment():
    """Its usage describes the one call that produced it, so the prompt size
    is the window's occupancy right then -- the number the status bar wants."""
    line = json.dumps({"type": "assistant", "message": {
        "content": [{"type": "text", "text": "hi"}],
        "usage": {"input_tokens": 2, "cache_read_input_tokens": 7444,
                  "cache_creation_input_tokens": 19143, "output_tokens": 5},
    }})
    (snap,) = [e for e in parse_line(line) if isinstance(e, ContextSnapshot)]
    assert snap.tokens == 2 + 7444 + 19143


def test_repeated_snapshots_do_not_accumulate():
    """Each one replaces the last. Summing them is precisely the bug: fifteen
    tool calls re-sending a 170k prompt summed to 2.6M against a 1M window."""
    snaps = []
    for size in (100_000, 170_000, 170_000):
        line = json.dumps({"type": "assistant", "message": {
            "content": [{"type": "text", "text": "x"}],
            "usage": {"input_tokens": size},
        }})
        snaps += [e for e in parse_line(line) if isinstance(e, ContextSnapshot)]
    assert [s.tokens for s in snaps] == [100_000, 170_000, 170_000]


def test_an_assistant_message_without_usage_reports_nothing():
    """Absent usage must not become a snapshot of zero, which would render as
    an empty window mid-conversation."""
    line = json.dumps({"type": "assistant",
                       "message": {"content": [{"type": "text", "text": "hi"}]}})
    assert not [e for e in parse_line(line) if isinstance(e, ContextSnapshot)]


def test_cache_writes_are_counted():
    """Routinely the largest of the four token counts and the dominant cost
    driver, and it was reported nowhere -- so the totals on Stats could not
    be reconciled against the list-price figure printed beside them."""
    (end,) = [e for e in parse_line(_multi_model_result()) if isinstance(e, TurnEnd)]
    assert end.usage.cache_write_tokens == 19143
    assert end.usage.cached_tokens == 7444          # read, not write


def test_no_token_field_the_engine_reports_is_ignored():
    """The guard for the bug that produced this test.

    `cache_creation_input_tokens` existed in every payload and was captured
    nowhere — routinely the largest of the four counts and the dominant cost
    driver — so the totals on Stats could not be reconciled against the list
    price printed beside them, and were wrong by about 20x.

    Rather than assert the four names we happen to know, this walks whatever
    token fields the payload actually contains. If the engine adds a fifth,
    this fails, which is the only way that discovery does not depend on
    someone noticing a number looking odd.
    """
    payload = json.loads(_multi_model_result())
    reported = {
        k: v for k, v in payload["usage"].items()
        if isinstance(v, int) and k.endswith("_tokens")
    }

    (end,) = [e for e in parse_line(_multi_model_result()) if isinstance(e, TurnEnd)]
    captured = {
        "input_tokens": end.usage.input_tokens,
        "output_tokens": end.usage.output_tokens,
        "cache_read_input_tokens": end.usage.cached_tokens,
        "cache_creation_input_tokens": end.usage.cache_write_tokens,
    }

    missing = set(reported) - set(captured)
    assert not missing, (
        f"the engine reports token fields nothing captures: {sorted(missing)} — "
        "totals shown to the user will not reconcile against cost"
    )
    for field, value in reported.items():
        assert captured[field] == value, f"{field}: stored {captured[field]}, engine said {value}"


def test_the_captured_totals_account_for_the_whole_turn():
    """Every token the turn was billed for appears in exactly one category,
    so the four rows on Stats sum to the turn rather than to a subset."""
    payload = json.loads(_multi_model_result())
    engine_total = sum(
        v for k, v in payload["usage"].items()
        if isinstance(v, int) and k.endswith("_tokens")
    )

    (end,) = [e for e in parse_line(_multi_model_result()) if isinstance(e, TurnEnd)]
    shown = (end.usage.input_tokens + end.usage.output_tokens
             + end.usage.cached_tokens + end.usage.cache_write_tokens)
    assert shown == engine_total


def test_a_refused_tool_is_reported_not_dropped():
    """The engine has always sent `permission_denials` and nothing read it.

    That is why a caged Faber session rendered exactly like one with nothing
    to say: its mutating tools sat behind a permission prompt, every prompt
    went unanswered, and the refusals were in the stream the whole time.
    """
    events = parse_line(json.dumps({
        "type": "result", "subtype": "success", "session_id": "s",
        "duration_ms": 10, "is_error": False, "terminal_reason": "completed",
        "usage": {}, "modelUsage": {},
        "permission_denials": [
            {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}},
            {"tool_name": "Write", "tool_input": {"file_path": "/tmp/a.py"}},
        ],
    }))
    end = events[0]
    assert [d.tool for d in end.denials] == ["Bash", "Write"]
    assert end.denials[0].target == "git commit -m x"
    assert end.terminal_reason == "completed"


def test_a_silent_turn_with_denials_reads_as_blocked_not_quiet():
    """The distinction the whole thing exists for: refused is not the same
    as declined, and only one of the two names something fixable."""
    events = parse_line(json.dumps({
        "type": "result", "subtype": "success", "session_id": "s",
        "duration_ms": 10, "is_error": False, "usage": {}, "modelUsage": {},
        "permission_denials": [{"tool_name": "Bash", "tool_input": {}}],
    }))
    end = events[0]
    assert end.silent and end.blocked


def test_a_malformed_denial_does_not_cost_the_turn_its_usage():
    """This field was unread until 2026-09-11, so its shape is unexercised."""
    events = parse_line(json.dumps({
        "type": "result", "subtype": "success", "session_id": "s",
        "duration_ms": 10, "is_error": False, "usage": {"input_tokens": 7},
        "modelUsage": {}, "permission_denials": ["nonsense", None, {}],
    }))
    end = events[0]
    assert end.usage.input_tokens == 7
    assert [d.tool for d in end.denials] == ["?"]


def test_running_out_of_room_is_not_the_same_as_finishing():
    """`stop_reason` has been parsed and carried since the orchestrator was
    written, and read by nothing. A turn cut off at the output ceiling looked
    exactly like one that had said its piece."""
    def end(reason):
        return parse_line(json.dumps({
            "type": "result", "subtype": "success", "session_id": "s",
            "duration_ms": 1, "is_error": False, "usage": {}, "modelUsage": {},
            "stop_reason": reason,
        }))[0]
    assert end("max_tokens").truncated
    assert not end("end_turn").truncated
    assert not end(None).truncated
