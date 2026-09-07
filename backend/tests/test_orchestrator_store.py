"""Conversation store tests — Noctis v2 Stage 2 item 1."""
import asyncio
from pathlib import Path

import pytest

from orchestrator.driver import launch
from orchestrator.events import (
    SessionStart, TextDelta, ThinkingDelta, ToolCall, ToolResult, TurnEnd, Usage,
)
from orchestrator.store import ConversationStore, fold

FIXTURE = Path(__file__).parent / "fixtures" / "stream_with_tools.jsonl"


@pytest.fixture
def store(tmp_path):
    s = ConversationStore(tmp_path / "t.db")
    yield s
    s.close()


def _events():
    async def go():
        return [e async for e in launch(["cat", str(FIXTURE)])]
    return asyncio.run(go())


def test_folding_a_real_stream_records_transcript_and_usage(store):
    sid = store.open_session("faber", cwd="/tmp")
    fold(store, sid, "faber", _events())
    store.close_session(sid)

    roles = {r["role"] for r in store.transcript(sid)}
    assert {"assistant", "tool", "tool_result"} <= roles
    life = store.lifetime_tokens()
    assert life["turns"] == 1 and life["cached"] > 0


def test_engine_session_id_is_captured_so_the_session_can_be_resumed(store):
    sid = store.open_session("faber")
    fold(store, sid, "faber", _events())
    store.close_session(sid)
    row = store.db.execute("SELECT engine_session_id FROM sessions WHERE id=?", (sid,)).fetchone()
    assert row["engine_session_id"]
    assert store.resumable("faber")


def test_empty_thinking_blocks_are_not_stored(store):
    """Thinking text is empty under display:'omitted' -- storing those rows
    would fill the transcript with blanks and pollute search."""
    sid = store.open_session("faber")
    store.record(sid, "faber", ThinkingDelta(text=""))
    store.record(sid, "faber", TextDelta("real content"))
    assert [r["role"] for r in store.transcript(sid)] == ["assistant"]


def test_history_search_ranks_by_relevance(store):
    sid = store.open_session("vesper")
    store.add_message(sid, "assistant", "Railway was chosen for persistent backends")
    store.add_message(sid, "assistant", "the cat sat on the mat")
    store.add_message(sid, "assistant", "Vercel suits static frontends only")

    hits = store.search("Railway persistent backends")
    assert hits and "Railway" in hits[0]["content"]
    assert all("mat" not in h["content"] for h in hits[:1])


def test_search_survives_punctuation_and_short_words(store):
    sid = store.open_session("general")
    store.add_message(sid, "assistant", "the propose-never-apply guardrail")
    assert store.search("propose-never-apply guardrail")
    assert store.search("a of to") == []      # nothing meaningful to match


def test_usage_has_no_cost_column(store):
    """A notional dollar figure that is never charged invites a UI that
    presents quota as spend."""
    cols = {r[1] for r in store.db.execute("PRAGMA table_info(usage)")}
    assert not any("cost" in c for c in cols)


def test_daily_activity_feeds_the_contribution_grid(store):
    for _ in range(3):
        store.close_session(store.open_session("faber"))
    rows = store.daily_activity()
    assert rows and rows[-1]["sessions"] == 3


def test_promote_writes_a_curated_note_into_the_vault(store, tmp_path):
    sid = store.open_session("vesper")
    store.add_message(sid, "user", "which host for a persistent backend?")
    store.add_message(sid, "assistant", "Railway — it holds connections.")
    store.record(sid, "vesper", ThinkingDelta(text=""))
    store.close_session(sid)

    vault = tmp_path / "vault"
    out = store.promote(sid, vault, "wiki/Hosting.md", "Hosting verdict", note="Locked.")
    text = out.read_text()
    assert "# Hosting verdict" in text and "Railway" in text and "Locked." in text
    assert "thinking" not in text


def test_promote_refuses_to_overwrite(store, tmp_path):
    sid = store.close_session(store.open_session("vesper")) or 1
    sid = store.open_session("vesper")
    store.add_message(sid, "assistant", "x")
    vault = tmp_path / "vault"
    store.promote(sid, vault, "wiki/A.md", "A")
    with pytest.raises(FileExistsError):
        store.promote(sid, vault, "wiki/A.md", "A")


def test_store_is_not_the_vault(store):
    """The whole point of the split: nothing here writes markdown unless
    promote() is called deliberately."""
    assert store.path.endswith(".db")
