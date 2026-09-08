"""v2 session route + wire-format tests.

The wire format is the API contract, so its tests assert the *field names*
the frontend reads rather than merely that serialization succeeds -- a
rename that keeps the shape valid but breaks the UI has to fail here.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from orchestrator.events import (
    EngineError, Limits, SessionStart, TextDelta, ThinkingDelta,
    ThinkingProgress, ToolCall, ToolResult, TurnEnd, Usage,
)
from orchestrator.wire import MAX_RESULT_CHARS, to_dict, to_sse


# ------------------------------------------------------------------ wire

def test_every_event_type_has_a_mapping():
    """A missing mapping is a hole in the transcript, so the union is walked
    exhaustively rather than sampled."""
    usage = Usage(input_tokens=1, output_tokens=2, cached_tokens=3, model="opus-5")
    events = [
        SessionStart(session_id="s", model="m", cwd="/tmp", tools=["Read"]),
        TextDelta(text="hi"),
        ThinkingDelta(text="", tokens=5),
        ThinkingProgress(estimated_tokens=50),
        ToolCall(id="1", name="Read", args={"file_path": "/a/b.py"}),
        ToolResult(id="1", content="x", is_error=False),
        Limits(five_hour_used=0.1, five_hour_resets_at=1, seven_day_used=0.2, seven_day_resets_at=2),
        TurnEnd(session_id="s", usage=usage, duration_ms=10),
        EngineError(message="boom", fatal=True),
    ]
    tags = [to_dict(e)["t"] for e in events]
    assert tags == ["start", "text", "thinking", "thinking_progress", "tool_call",
                    "tool_result", "limits", "turn_end", "error"]


def test_unmapped_type_raises_rather_than_dropping():
    with pytest.raises(TypeError):
        to_dict(object())  # type: ignore[arg-type]


def test_tool_call_carries_the_computed_summary():
    """Computed server-side so the transcript and the runtime log describe a
    call the same way, rather than each deriving its own."""
    d = to_dict(ToolCall(id="1", name="Read", args={"file_path": "/a/b.py"}))
    assert d["summary"] == "/a/b.py"


def test_long_tool_result_is_truncated_and_says_so():
    """A prefix presented as the whole result is a quiet lie; the flag is
    what lets the UI say 'truncated'."""
    d = to_dict(ToolResult(id="1", content="x" * (MAX_RESULT_CHARS + 500)))
    assert len(d["content"]) == MAX_RESULT_CHARS
    assert d["truncated"] is True


def test_short_tool_result_is_not_flagged():
    assert to_dict(ToolResult(id="1", content="ok"))["truncated"] is False


def test_omitted_thinking_still_sends_the_field():
    """Empty text is the normal case, not an absence -- the field being
    present is how the frontend tells 'omitted' from 'no thinking'."""
    d = to_dict(ThinkingDelta(text="", tokens=12))
    assert d["text"] == "" and d["tokens"] == 12


def test_turn_end_nests_usage_under_the_names_the_ui_reads():
    usage = Usage(input_tokens=10, output_tokens=20, cached_tokens=30, model="opus-5",
                  aux_input_tokens=900, aux_output_tokens=12)
    d = to_dict(TurnEnd(session_id="s", usage=usage, duration_ms=7))
    assert d["usage"] == {"input": 10, "output": 20, "cached": 30, "model": "opus-5",
                          "aux_input": 900, "aux_output": 12}


def test_sse_frame_is_one_json_line_then_a_blank():
    frame = to_sse(TextDelta(text="hello"))
    assert frame.startswith("data: ") and frame.endswith("\n\n")
    assert json.loads(frame[6:].strip())["text"] == "hello"


def test_sse_payload_has_no_raw_newlines():
    """A newline inside the payload would split one frame into two and
    desynchronise the stream."""
    frame = to_sse(TextDelta(text="a\nb"))
    assert frame.count("\n") == 2  # only the two terminators


# ------------------------------------------------------------------ routes

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NOCTIS_API_TOKEN", "test-token")
    from main import app
    return TestClient(app)


AUTH = {"Authorization": "Bearer test-token"}


def test_launch_rejects_an_unknown_mode(client):
    r = client.post("/v2/sessions", headers=AUTH,
                    json={"mode": "nope", "prompt": "x", "cwd": str(Path.home())})
    assert r.status_code == 404


def test_launch_refuses_bypass_permissions_over_the_wire(client):
    """It is excluded from the UI's cycle; a guard that exists only in the
    client is not a guard."""
    r = client.post("/v2/sessions", headers=AUTH,
                    json={"mode": "faber", "prompt": "x", "cwd": str(Path.home()),
                          "permission_mode": "bypassPermissions"})
    assert r.status_code == 400


def test_cwd_outside_home_is_refused(client):
    """cwd reaches exec as a working directory -- the same class of input as
    the job_slug traversal caught in the 2026-07-21 review."""
    r = client.post("/v2/sessions", headers=AUTH,
                    json={"mode": "faber", "prompt": "x", "cwd": "/etc"})
    assert r.status_code == 403


def test_nonexistent_cwd_is_refused(client):
    r = client.post("/v2/sessions", headers=AUTH,
                    json={"mode": "faber", "prompt": "x", "cwd": "~/definitely-not-here-xyz"})
    assert r.status_code == 400


def test_symlink_out_of_home_cannot_smuggle_a_path(client, tmp_path, monkeypatch):
    """Resolution happens before the containment check, so a link inside
    home that points outside it is still refused."""
    link = Path.home() / ".noctis-test-escape-link"
    try:
        link.symlink_to("/etc")
        r = client.post("/v2/sessions", headers=AUTH,
                        json={"mode": "faber", "prompt": "x", "cwd": str(link)})
        assert r.status_code == 403
    finally:
        link.unlink(missing_ok=True)


def test_empty_prompt_is_rejected(client):
    r = client.post("/v2/sessions", headers=AUTH,
                    json={"mode": "faber", "prompt": "", "cwd": str(Path.home())})
    assert r.status_code == 422


def test_routes_require_auth(client):
    assert client.get("/v2/sessions").status_code == 401
    assert client.get("/v2/sessions/limits").status_code == 401


def test_limits_distinguishes_unknown_from_zero(client):
    """Zero utilisation and 'not yet reported' must not render alike: the
    difference decides whether there is room to start a session."""
    body = client.get("/v2/sessions/limits", headers=AUTH).json()
    assert body["known"] is False
    assert body["five_hour"] is None


def test_session_list_reports_the_concurrency_budget(client):
    body = client.get("/v2/sessions", headers=AUTH).json()
    assert body["max_concurrent"] == 2
    assert body["running"] == 0


# ------------------------------------------------------------------- stats

def test_stats_lifetime_includes_the_background_tier(tmp_path):
    """The parser lost ~900 input tokens a turn by reading only the primary
    model. A lifetime total that sums only the primary columns reproduces
    that same undercount one layer down."""
    from orchestrator.events import TurnEnd, Usage
    from orchestrator.store import ConversationStore

    store = ConversationStore(tmp_path / "h.db")
    sid = store.open_session("faber", cwd="/tmp")
    store.record(sid, "faber", TurnEnd(
        session_id="s", duration_ms=1,
        usage=Usage(input_tokens=2, output_tokens=52, cached_tokens=7444,
                    model="claude-opus-5", aux_input_tokens=903, aux_output_tokens=12),
    ))
    life = store.lifetime_tokens()
    assert life["input"] == 905          # 2 primary + 903 background
    assert life["output"] == 64          # 52 + 12
    assert life["primary_input"] == 2    # still available for the per-turn view
    store.close()


def test_usage_by_mode_attributes_tokens_to_the_mode_that_spent_them(tmp_path):
    from orchestrator.events import TurnEnd, Usage
    from orchestrator.store import ConversationStore

    store = ConversationStore(tmp_path / "h.db")
    for mode, out in (("faber", 100), ("vesper", 30)):
        sid = store.open_session(mode, cwd="/tmp")
        store.record(sid, mode, TurnEnd(
            session_id="s", duration_ms=1,
            usage=Usage(input_tokens=1, output_tokens=out, cached_tokens=0, model="m"),
        ))
    rows = {r["mode"]: r["output"] for r in store.usage_by_mode()}
    assert rows == {"faber": 100, "vesper": 30}
    store.close()


def test_an_older_database_gains_the_new_columns(tmp_path):
    """CREATE TABLE IF NOT EXISTS is a no-op on a database that already has
    the table, so without the add-column pass the next INSERT fails on any
    machine that ran the older build."""
    import sqlite3
    from orchestrator.store import SCHEMA, ConversationStore

    old = SCHEMA.replace("    aux_input_tokens  INTEGER NOT NULL DEFAULT 0,\n", "")
    old = old.replace("    aux_output_tokens INTEGER NOT NULL DEFAULT 0,\n", "")
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript(old)
    con.commit()
    con.close()

    store = ConversationStore(path)
    cols = {r[1] for r in store.db.execute("PRAGMA table_info(usage)")}
    assert {"aux_input_tokens", "aux_output_tokens"} <= cols
    store.close()


def test_stats_route_shape(client):
    body = client.get("/v2/sessions/stats", headers=AUTH).json()
    assert set(body) == {"lifetime", "by_mode", "activity"}
    assert set(body["lifetime"]) >= {"input", "output", "cached", "turns", "aux_input"}


def test_stats_requires_auth(client):
    assert client.get("/v2/sessions/stats").status_code == 401
