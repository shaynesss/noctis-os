"""Reading the CLI's own transcripts instead of recording our own.

Fixtures rather than the developer's real ~/.claude, so the suite is the same
on a machine that has never run Claude Code -- the conftest lesson: a test
describing *this* machine passes alone and fails in CI.
"""
import json
from pathlib import Path


from orchestrator import jsonl


def _write(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "d39b0af7-0000-0000-0000-000000000000.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
    return p


def _assistant(text=None, thinking=None, tool=None, usage=None, **top):
    content = []
    if thinking is not None:
        content.append({"type": "thinking", "thinking": thinking, "signature": "x"})
    if text is not None:
        content.append({"type": "text", "text": text})
    if tool is not None:
        content.append({"type": "tool_use", "id": "t1", "name": tool, "input": {"a": 1}})
    msg = {"role": "assistant", "content": content, "model": "claude-opus-5"}
    if usage:
        msg["usage"] = usage
    return {"type": "assistant", "message": msg, **top}


USAGE = {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 300,
         "cache_creation_input_tokens": 40,
         "output_tokens_details": {"thinking_tokens": 7}}


def test_it_reconstructs_the_columns_the_store_holds(tmp_path):
    p = _write(tmp_path, [
        {"type": "user", "message": {"role": "user", "content": "go"},
         "timestamp": "2026-09-13T10:00:00Z", "cwd": "/repo", "gitBranch": "main"},
        _assistant(text="done", usage=USAGE, timestamp="2026-09-13T10:00:09Z"),
        {"type": "ai-title", "aiTitle": "A short conversation"},
    ])
    c = jsonl.read(p)
    assert c.engine_session_id == p.stem
    assert c.cwd == "/repo" and c.git_branch == "main"
    assert c.started_at == "2026-09-13T10:00:00Z"
    assert c.ended_at == "2026-09-13T10:00:09Z"
    # The CLI names its own conversations, so titling stops costing a call.
    assert c.title == "A short conversation"
    assert [m["role"] for m in c.messages] == ["user", "assistant"]


def test_thinking_survives_having_no_text(tmp_path):
    """The case that was silently dropped on first write.

    Models default to `display: "omitted"`, so reasoning is billed and never
    returned -- every thinking block in the first real transcript this was run
    against had empty text. The transcript renders thinking as a counter, not
    prose, so the block's existence is the whole signal and guarding on its
    text loses all of them.
    """
    p = _write(tmp_path, [_assistant(thinking="", text="hi", usage=USAGE)])
    roles = [m["role"] for m in jsonl.read(p).messages]
    assert "thinking" in roles, "an omitted-reasoning block must still be recorded"


def test_tool_calls_keep_the_id_that_matches_their_result(tmp_path):
    """Results interleave with text and can arrive out of order, so the id is
    what pairs them -- the same reason the transcript matches by id."""
    p = _write(tmp_path, [
        _assistant(tool="Bash", usage=USAGE),
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}},
    ])
    msgs = jsonl.read(p).messages
    call = next(m for m in msgs if m["role"] == "tool")
    result = next(m for m in msgs if m["role"] == "tool_result")
    assert json.loads(call["meta"])["id"] == json.loads(result["meta"])["id"] == "t1"


def test_lifetime_is_one_raw_number(tmp_path):
    """No split, no tiers. Every token the conversation spent, added up."""
    p = _write(tmp_path, [_assistant(text="a", usage=USAGE),
                          _assistant(text="b", usage=USAGE)])
    c = jsonl.read(p)
    assert len(c.turns) == 2
    # 10 + 20 + 300 + 40, twice.
    assert c.lifetime == 2 * 370


def test_a_half_written_final_line_costs_one_line_not_the_file(tmp_path):
    """The file is appended to live, so a read can land mid-write. Refusing
    the whole transcript for a torn line would make history vanish exactly
    while a session was busy producing it."""
    p = _write(tmp_path, [_assistant(text="kept", usage=USAGE)])
    p.write_text(p.read_text() + '\n{"type":"assistant","mess',  encoding="utf-8")
    c = jsonl.read(p)
    assert len(c.turns) == 1
    assert any(m["content"] == "kept" for m in c.messages)


def test_an_unreadable_file_is_empty_not_an_exception(tmp_path):
    assert jsonl.read(tmp_path / "nope.jsonl").messages == []


def test_transcript_path_finds_a_session_without_knowing_its_project(monkeypatch, tmp_path):
    """A session that changed directory still lives in the project dir it
    started in, which the caller usually does not have."""
    proj = tmp_path / "-Users-someone-repo"
    proj.mkdir()
    (proj / "abc-123.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(jsonl, "PROJECTS", tmp_path)
    assert jsonl.transcript_path("abc-123") == proj / "abc-123.jsonl"
    assert jsonl.transcript_path("missing") is None


def test_an_untitled_transcript_is_named_after_the_first_question(tmp_path):
    """The CLI names only some conversations -- 125 of 140 on the machine
    this first ran on had no aiTitle -- and an untitled row in history is a
    row nobody can pick out. The first thing asked is what they came for."""
    p = _write(tmp_path, [
        {"type": "user", "message": {"role": "user",
                                     "content": "why does the batcher only flush on the next read?\nmore context"}},
        _assistant(text="because", usage=USAGE),
    ])
    assert jsonl.read(p).title == "why does the batcher only flush on the next read"


def test_a_long_first_question_is_cut_with_an_ellipsis(tmp_path):
    p = _write(tmp_path, [{"type": "user", "message": {"role": "user", "content": "x" * 200}},
                          _assistant(text="ok", usage=USAGE)])
    t = jsonl.read(p).title
    assert t.endswith("…") and len(t) <= 61


def test_an_ai_title_still_wins(tmp_path):
    p = _write(tmp_path, [{"type": "user", "message": {"role": "user", "content": "first question"}},
                          _assistant(text="ok", usage=USAGE),
                          {"type": "ai-title", "aiTitle": "The CLI's name"}])
    assert jsonl.read(p).title == "The CLI's name"


def test_scan_usage_agrees_with_read_to_the_token(tmp_path):
    """The lifetime figure is summed from `scan_usage`, which walks the same
    records as `read` but keeps no text. If the two ever disagree, Stats and
    history disagree about what a session cost."""
    import json
    from orchestrator import jsonl
    p = tmp_path / "s.jsonl"
    rows = [
        {"type": "user", "timestamp": "2026-09-14T01:00:00Z", "cwd": "/x",
         "message": {"role": "user", "content": "hi"}},
        {"type": "assistant", "timestamp": "2026-09-14T00:59:00Z",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "yo"}],
                     "usage": {"input_tokens": 3, "output_tokens": 5,
                               "cache_read_input_tokens": 7, "cache_creation_input_tokens": 11}}},
        {"type": "assistant", "timestamp": "2026-09-14T01:01:00Z",
         "message": {"role": "assistant", "content": [], "usage": {"output_tokens": 2}}},
        "not json at all",
    ]
    p.write_text("\n".join(json.dumps(r) if isinstance(r, dict) else r for r in rows) + "\n")
    c, u = jsonl.read(p), jsonl.scan_usage(p)
    assert u.turns == len(c.turns) == 2
    assert u.lifetime == c.lifetime == 28
    assert u.started_at == c.started_at == "2026-09-14T00:59:00Z"
    assert (u.input_tokens, u.output_tokens, u.cached_tokens, u.cache_write_tokens) == \
        (sum(t.input_tokens for t in c.turns), sum(t.output_tokens for t in c.turns),
         sum(t.cached_tokens for t in c.turns), sum(t.cache_write_tokens for t in c.turns))


# ------------------------------------------------------------------ pricing

def test_a_turn_is_priced_at_list_from_its_own_model():
    """Four rates per model, cache writes at the hour TTL the CLI uses. The
    figures are the ones the `-p` engine reported for its own turns: 71
    output and 28,533 cache-write tokens on Opus 5 came back as $0.2871, and
    that is what the table gives."""
    from orchestrator import pricing
    assert round(pricing.list_price("claude-opus-5", 2, 71, 0, 28_533), 4) == 0.2871
    # Sonnet 5: 227 out, 37,645 cache reads, 86 written -- the engine said $0.0101.
    assert round(pricing.list_price("claude-sonnet-5", 2, 227, 37_645, 86), 4) == 0.0101
    # Fable 5.1 reads its cache at a quarter of the usual tenth.
    assert pricing.list_price("claude-fable-5-1", 0, 0, 4_000_000, 0) == 1.0


def test_a_dated_model_id_prices_as_its_family():
    from orchestrator import pricing
    assert pricing.rates("claude-haiku-4-5-20251001") == pricing.rates("claude-haiku-4-5")


def test_an_unknown_model_is_a_gap_unless_it_spent_nothing():
    """`<synthetic>` rows carry every count at zero: priced, at zero, rather
    than reported as turns the figure does not cover."""
    from orchestrator import pricing
    assert pricing.list_price("<synthetic>", 0, 0, 0, 0) == 0.0
    assert pricing.list_price("claude-mystery-9", 1, 0, 0, 0) is None


def test_scan_usage_prices_each_turn_and_counts_the_ones_it_cannot(tmp_path):
    p = _write(tmp_path, [
        _assistant(text="a", usage={"input_tokens": 1_000_000}),               # Opus 5: $5
        {"type": "assistant", "message": {"role": "assistant", "model": "who",
                                          "content": [], "usage": {"output_tokens": 1}}},
    ])
    u = jsonl.scan_usage(p)
    assert (u.turns, u.unpriced_turns, u.list_cost) == (2, 1, 5.0)


def test_the_recorder_row_carries_the_same_price(tmp_path):
    """Indexing a transcript writes the table's price into `list_cost_usd`,
    so a row in the store and the figure Stats quotes never disagree."""
    from orchestrator.store import ConversationStore
    p = _write(tmp_path, [{"type": "user", "timestamp": "2026-09-14T00:00:00Z", "cwd": "/x",
                           "message": {"role": "user", "content": "hi"}},
                          _assistant(text="a", usage={"input_tokens": 1_000_000},
                                     timestamp="2026-09-14T00:00:01Z")])
    store = ConversationStore(tmp_path / "h.db")
    store.ingest(jsonl.read(p), "faber")
    assert store.lifetime_tokens()["list_cost"] == 5.0
    store.close()
