"""Reading the CLI's own transcripts instead of recording our own.

Fixtures rather than the developer's real ~/.claude, so the suite is the same
on a machine that has never run Claude Code -- the conftest lesson: a test
describing *this* machine passes alone and fails in CI.
"""
import json
import textwrap
from pathlib import Path

import pytest

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
