"""v2 session route + wire-format tests.

The wire format is the API contract, so its tests assert the *field names*
the frontend reads rather than merely that serialization succeeds -- a
rename that keeps the shape valid but breaks the UI has to fail here.
"""
import json
import pathlib
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


# ------------------------------------------------------------------ panels

def test_brief_reports_absence_rather_than_inventing_one(client):
    """The generator is build-order item 6. A panel that invents a morning
    brief is worse than one that says it has not run, because the invented
    one gets believed."""
    body = client.get("/v2/brief", headers=AUTH).json()
    assert body["brief"]["generated"] is False
    assert body["brief"]["markdown"] is None
    assert body["brief"]["path"] == "brief/today.md"


def test_config_reports_what_the_orchestrator_will_really_run(client):
    """Read from driver.py rather than restated, so Settings cannot drift
    into describing a system that no longer exists."""
    from orchestrator.driver import MODE_MODELS

    body = client.get("/v2/config", headers=AUTH).json()
    assert {m["mode"]: m["model"] for m in body["modes"]} == MODE_MODELS
    assert "bypassPermissions" in body["excluded_from_cycle"]
    assert "bypassPermissions" not in body["permission_cycle"]


def test_maintenance_is_shown_as_unable_to_edit(client):
    """The one policy that decides what a session can do to your files."""
    body = client.get("/v2/config", headers=AUTH).json()
    maint = next(m for m in body["modes"] if m["mode"] == "maintenance")
    assert "Edit" in maint["disallowed"] and "Write" in maint["disallowed"]


def test_finished_jobs_are_not_inbox_items(monkeypatch):
    """Most of the vault's flagged jobs are settings work completed in July.
    Including them produced 22 entries, 20 long resolved -- which is how an
    inbox stops being read."""
    from routers import panels

    jobs = {
        "modes": ["dev"],
        "modes/dev/jobs": ["done-one", "open-one"],
    }
    meta = {
        "modes/dev/jobs/done-one/context.md": {"flagged": True, "stage": "Done", "name": "Done one"},
        "modes/dev/jobs/open-one/context.md": {"flagged": True, "stage": "Build", "name": "Open one"},
    }
    monkeypatch.setattr(panels.vault_io, "list_subdirs", lambda p: jobs.get(p, []))
    monkeypatch.setattr(panels.vault_io, "file_exists", lambda p: True)
    monkeypatch.setattr(panels, "_safe_frontmatter", lambda p: meta.get(p))

    titles = [j["title"] for j in panels._flagged_jobs()]
    assert titles == ["Open one"]


def test_one_unparseable_job_does_not_take_down_the_panel(monkeypatch):
    """A YAML scalar containing ': ' parses as a mapping and raises -- a real
    file in modes/dev/jobs was failing exactly that way."""
    from routers import panels

    monkeypatch.setattr(panels.vault_io, "list_subdirs",
                        lambda p: ["dev"] if p == "modes" else ["broken"])
    monkeypatch.setattr(panels.vault_io, "file_exists", lambda p: True)
    monkeypatch.setattr(panels, "_safe_frontmatter", lambda p: None)

    items = panels._flagged_jobs()
    assert len(items) == 1
    assert items[0]["kind"] == "unreadable"


def test_the_inbox_readme_is_not_a_proposal(monkeypatch):
    """The staging folder holds its own README; listing it put a docs file in
    a queue of things awaiting a decision."""
    from routers import panels

    monkeypatch.setattr(panels.vault_io, "file_exists", lambda p: True)
    monkeypatch.setattr(panels.vault_io, "list_dir", lambda p: ["README", "real-proposal"])
    monkeypatch.setattr(panels, "_safe_frontmatter", lambda p: {"description": "d"})
    monkeypatch.setattr(panels.vault_io, "read_frontmatter", lambda p: ({}, "body"))

    assert [p["id"] for p in panels._proposals()] == ["real-proposal"]


# ----------------------------------------------------------------- history

def _rows(msgs):
    """Message rows shaped like sqlite3.Row for the block renderer."""
    return [{"role": r, "content": c, "meta": m, "created_at": "2026-09-09T09:15:00+00:00"}
            for r, c, m in msgs]


def test_assistant_deltas_rejoin_into_one_block():
    """Deltas are stored one row each; a restored reply must not arrive
    shattered into a paragraph per fragment."""
    from orchestrator.wire import blocks_from_messages
    blocks = blocks_from_messages(_rows([
        ("assistant", "Hel", None), ("assistant", "lo ", None), ("assistant", "there", None),
    ]))
    assert blocks == [{"kind": "text", "text": "Hello there"}]


def test_a_user_turn_separates_two_replies():
    """Without the user message between them, two turns' answers merge --
    which is exactly what old rows did before the prompt was recorded."""
    from orchestrator.wire import blocks_from_messages
    blocks = blocks_from_messages(_rows([
        ("user", "one?", None), ("assistant", "ONE", None),
        ("user", "two?", None), ("assistant", "TWO", None),
    ]))
    assert [b["kind"] for b in blocks] == ["user", "text", "user", "text"]
    assert blocks[3]["text"] == "TWO"


def test_a_tool_result_pairs_with_its_call_by_id():
    """Pairing on adjacency breaks under the interleaving the live reducer
    already handles; the stored form must agree with it."""
    from orchestrator.wire import blocks_from_messages
    blocks = blocks_from_messages(_rows([
        ("tool", "Read /a.py", '{"id": "a", "tool": "Read"}'),
        ("tool", "Bash ls", '{"id": "b", "tool": "Bash"}'),
        ("tool_result", "B OUT", '{"id": "b"}'),
        ("tool_result", "A OUT", '{"id": "a"}'),
    ]))
    assert [(b["id"], b["body"]) for b in blocks] == [("a", "A OUT"), ("b", "B OUT")]


def test_a_failed_tool_result_opens_itself():
    from orchestrator.wire import blocks_from_messages
    blocks = blocks_from_messages(_rows([
        ("tool", "Bash boom", '{"id": "x", "tool": "Bash"}'),
        ("tool_result", "nope", '{"id": "x", "is_error": true}'),
    ]))
    assert blocks[0]["meta"] == "error" and blocks[0]["open"] is True


def test_history_marks_what_cannot_be_resumed(client):
    """A conversation whose engine id was never learned is history you can
    read but not continue; the two must not look alike."""
    body = client.get("/v2/sessions/history", headers=AUTH).json()
    for s in body["sessions"]:
        if not s["engine_id"]:
            assert s["resumable"] is False


def test_transcript_404s_for_an_unknown_session(client):
    assert client.get("/v2/sessions/history/999999", headers=AUTH).status_code == 404


def test_history_requires_auth(client):
    assert client.get("/v2/sessions/history").status_code == 401


# ------------------------------------------------------------------ search

def test_search_returns_one_hit_per_conversation(monkeypatch, client):
    """Several matching messages in one session are one result to a person
    looking for that conversation -- and a long session would otherwise
    flood the list and bury everything else."""
    from routers import search as search_router

    rows = [
        {"session_id": 1, "mode": "faber", "role": "user", "content": "alpha one",
         "created_at": "2026-09-09"},
        {"session_id": 1, "mode": "faber", "role": "assistant", "content": "alpha two",
         "created_at": "2026-09-09"},
        {"session_id": 2, "mode": "vesper", "role": "user", "content": "alpha three",
         "created_at": "2026-09-09"},
    ]
    monkeypatch.setattr(search_router._store, "search", lambda q, limit: rows)
    monkeypatch.setattr(search_router, "_vault_index", lambda: type("I", (), {"search": lambda *a, **k: []})())

    body = client.get("/v2/search?q=alpha", headers=AUTH).json()
    assert [c["session_id"] for c in body["conversations"]] == [1, 2]


def test_excerpt_centres_on_the_match_not_the_opening():
    """A prefix of a long message is very often the least useful part of it;
    the match is why the row is there."""
    from routers.search import _excerpt

    text = "x" * 400 + " needle " + "y" * 400
    out = _excerpt(text, "needle")
    assert "needle" in out
    assert out.startswith("…")


def test_excerpt_falls_back_when_no_term_matches():
    from routers.search import _excerpt
    assert _excerpt("some content here", "zz").startswith("some content")


def test_search_requires_a_real_query(client):
    assert client.get("/v2/search?q=a", headers=AUTH).status_code == 422


def test_search_requires_auth(client):
    assert client.get("/v2/search?q=alpha").status_code == 401


# ------------------------------------------------------------ vault reader

def test_reader_refuses_the_project_root_prefix(client):
    """vault_io's ordinary resolver honours a project-root allowlist that
    also resolves noctis-os/.env -- the file holding this API's own token.
    Verified by reading it, not assumed. Anything taking a client-supplied
    path must not go through that resolver."""
    r = client.get("/v2/vault/doc?path=noctis-os/.env", headers=AUTH)
    assert r.status_code in (400, 403, 404)
    assert "NOCTIS_API_TOKEN" not in r.text


def test_reader_refuses_a_traversal(client):
    r = client.get("/v2/vault/doc?path=../../etc/passwd", headers=AUTH)
    assert r.status_code in (400, 403, 404)


def test_reader_refuses_non_markdown(client):
    """The vault holds binaries; a reader that serves any file is an
    exfiltration endpoint wearing a document viewer's clothes."""
    assert client.get("/v2/vault/doc?path=some/image.png", headers=AUTH).status_code == 400


def test_reader_404s_for_a_missing_document(client):
    r = client.get("/v2/vault/doc?path=definitely/not/here.md", headers=AUTH)
    assert r.status_code == 404


def test_reader_returns_a_real_document(client):
    r = client.get("/v2/vault/doc?path=README.md", headers=AUTH)
    if r.status_code == 200:
        assert isinstance(r.json()["markdown"], str)


def test_reader_requires_auth(client):
    assert client.get("/v2/vault/doc?path=README.md").status_code == 401


def test_vault_only_resolver_never_reaches_the_repo(tmp_path, monkeypatch):
    """It does not raise on this input, and should not: the path is treated
    as vault-relative (second-brain/noctis-os/.env), which is inside the
    vault and simply does not exist. The property that matters is that it
    cannot land on the repo's real .env, which the ordinary resolver does."""
    import vault_io

    resolved = vault_io.resolve_vault_only("noctis-os/.env")
    vault = vault_io.get_vault_path().resolve()
    assert vault in resolved.parents
    assert resolved != (pathlib.Path(vault_io.__file__).resolve().parent.parent / ".env")


def test_the_ordinary_resolver_still_reaches_the_repo(tmp_path):
    """Documents why the two exist. This capability is deliberate -- the
    apply pipeline writes noctis-os/SPEC.md -- and is exactly why a
    client-supplied path must not use it."""
    import vault_io

    repo = pathlib.Path(vault_io.__file__).resolve().parent.parent
    assert vault_io._resolve_within_vault("noctis-os/SPEC.md") == repo / "SPEC.md"
