"""The second door into history, and the seam it shares with the first.

`store.record` folds stream events while Noctis hosts a session; `store.ingest`
takes a conversation read from the CLI's own transcript afterwards. The
migration's gate compares what the two counted, so the tests here are mostly
about the comparison staying honest.
"""
import json
from pathlib import Path

import pytest

from orchestrator import jsonl
from orchestrator.store import ConversationStore


@pytest.fixture
def store(tmp_path):
    return ConversationStore(tmp_path / "h.db")


def _recorded(store, row, engine_id, tokens=None):
    """A row the way the old recorder left it: engine id set, source
    'recorder', and a usage row per turn. The recorder is gone; the rows it
    wrote are still in real databases, and the seam has to keep treating
    them as what they were."""
    store.db.execute("UPDATE sessions SET engine_session_id=? WHERE id=?", (engine_id, row))
    if tokens:
        i, o, cr, cw = tokens
        store.db.execute(
            "INSERT INTO usage (session_id, mode, model, input_tokens, output_tokens,"
            " cached_tokens, cache_write_tokens, duration_ms, created_at)"
            " VALUES (?,?,?,?,?,?,?,1,'2026-09-13T10:00:00+00:00')", (row, "faber", "m", i, o, cr, cw))
    store.db.commit()


def _conv(sid="abc-1", tokens=(10, 20, 300, 40)):
    i, o, cr, cw = tokens
    return jsonl.Conversation(
        engine_session_id=sid, cwd="/repo", title="A title",
        started_at="2026-09-13T10:00:00Z", ended_at="2026-09-13T10:05:00Z",
        messages=[{"role": "user", "content": "go", "meta": None},
                  {"role": "assistant", "content": "done", "meta": None}],
        turns=[jsonl.Turn(model="m", input_tokens=i, output_tokens=o,
                          cached_tokens=cr, cache_write_tokens=cw)],
    )


def test_ingest_files_a_transcript_as_a_transcript(store):
    row = store.ingest(_conv(), "vesper")
    assert row is not None
    s = store.db.execute("SELECT mode, title, source, state FROM sessions WHERE id=?",
                         (row,)).fetchone()
    assert (s["mode"], s["title"], s["source"], s["state"]) == \
        ("vesper", "A title", "transcript", "done")
    assert store.db.execute("SELECT count(*) FROM messages WHERE session_id=?",
                            (row,)).fetchone()[0] == 2
    assert store.db.execute("SELECT count(*) FROM usage WHERE session_id=?",
                            (row,)).fetchone()[0] == 1


def test_ingest_is_idempotent_on_the_engine_id(store):
    """Run beside the recorder, this must not duplicate what the recorder
    already wrote -- and running twice must not duplicate itself."""
    assert store.ingest(_conv("same"), "faber") is not None
    assert store.ingest(_conv("same"), "faber") is None
    assert store.db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1


def test_ingest_declines_a_session_the_recorder_already_has(store):
    row = store.open_session("faber", cwd="/repo", title="live")
    _recorded(store, row, "rec-1")
    assert store.ingest(_conv("rec-1"), "faber") is None
    assert store.db.execute("SELECT source FROM sessions WHERE id=?",
                            (row,)).fetchone()["source"] == "recorder"


def test_the_comparison_only_tests_what_the_recorder_wrote(store):
    """The gate must not be padded with tautologies.

    A session the indexer filed has usage rows copied from its transcript, so
    comparing those against the transcript proves nothing. On first live run
    30 of 45 sessions "agreed", and an unknown share of those were exactly
    this. `tokens_for_engine_id` answers only for recorder rows, so the diff
    skips the rest.
    """
    # Recorded by the recorder: a real comparison.
    row = store.open_session("faber", cwd="/repo", title="live")
    _recorded(store, row, "rec-1", tokens=(10, 20, 300, 40))
    assert store.tokens_for_engine_id("rec-1") == 370

    # Filed from a transcript: not a comparison at all.
    store.ingest(_conv("idx-1"), "vesper")
    assert store.tokens_for_engine_id("idx-1") is None


def test_an_old_database_gains_the_source_column(tmp_path):
    """A database from before the indexer existed has no `source` column, and
    every row in it was the recorder's -- so the default is also the truth."""
    import sqlite3
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE sessions (id INTEGER PRIMARY KEY, engine_session_id TEXT UNIQUE,
            mode TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'running', title TEXT,
            cwd TEXT, started_at TEXT NOT NULL, ended_at TEXT, recap TEXT,
            recap_at INTEGER NOT NULL DEFAULT 0);
        INSERT INTO sessions (engine_session_id, mode, started_at)
            VALUES ('legacy', 'faber', '2026-09-01T00:00:00Z');
    """)
    db.commit(); db.close()

    store = ConversationStore(path)
    assert store.db.execute("SELECT source FROM sessions WHERE engine_session_id='legacy'"
                            ).fetchone()["source"] == "recorder"


def test_index_new_files_unknown_transcripts_with_their_mode(store, tmp_path, monkeypatch):
    """Terminal sessions never pass through the recorder. This is how they
    reach history, and the statusLine's mode map is how they get a mode --
    a transcript it does not know is filed as general rather than guessed."""
    proj = tmp_path / "-Users-x-repo"
    proj.mkdir()
    rec = {"type": "assistant", "timestamp": "2026-09-13T10:00:00Z", "cwd": "/repo",
           "message": {"role": "assistant", "model": "m",
                       "content": [{"type": "text", "text": "hi"}],
                       "usage": {"input_tokens": 1, "output_tokens": 2}}}
    (proj / "known.jsonl").write_text(json.dumps(rec), encoding="utf-8")
    (proj / "stranger.jsonl").write_text(json.dumps(rec), encoding="utf-8")
    monkeypatch.setattr(jsonl, "PROJECTS", tmp_path)

    taken = jsonl.index_new(store, {"known": "noctua"})
    assert sorted(taken) == ["known", "stranger"]
    modes = dict(store.db.execute("SELECT engine_session_id, mode FROM sessions"))
    assert modes == {"known": "noctua", "stranger": "general"}
    # And again: nothing new to take.
    assert jsonl.index_new(store, {"known": "noctua"}) == []


def test_diff_skips_sessions_only_the_indexer_wrote(store, tmp_path, monkeypatch):
    proj = tmp_path / "-Users-x-repo"
    proj.mkdir()
    rec = {"type": "assistant", "timestamp": "2026-09-13T10:00:00Z",
           "message": {"role": "assistant", "model": "m",
                       "content": [{"type": "text", "text": "hi"}],
                       "usage": {"input_tokens": 1, "output_tokens": 2}}}
    (proj / "only-indexed.jsonl").write_text(json.dumps(rec), encoding="utf-8")
    monkeypatch.setattr(jsonl, "PROJECTS", tmp_path)
    jsonl.index_new(store, {})

    d = jsonl.diff_against(store)
    assert d["compared"] == 0, "an indexed-only session is not a comparison"


def test_a_second_indexing_pass_yields_to_the_one_running(store, monkeypatch):
    """Stats calls index_new on every visit and the shell calls it when a
    terminal ends. Twelve concurrent passes under a sweep all found the same
    new transcript, all tried to file it, and the writers queued on SQLite's
    lock past its busy timeout -- the stats route answered 500. A pass that
    is running will file everything; a second one returns at once."""
    assert jsonl._indexing.acquire(blocking=False)
    try:
        assert jsonl.index_new(store, {}) == []
    finally:
        jsonl._indexing.release()


def test_losing_the_unique_race_declines_like_seeing_the_row(store, monkeypatch):
    """Between the existence check and the insert, another pass can file the
    same transcript. engine_session_id is UNIQUE, so the insert raises; the
    row exists, which is the outcome wanted, so this returns None."""
    monkeypatch.setattr(store, "find_by_engine_id", lambda _eid: None)
    assert store.ingest(_conv("raced"), "faber") is not None
    # Now the row exists but the (patched) check says it does not.
    assert store.ingest(_conv("raced"), "faber") is None
    assert store.db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1


def test_a_forgotten_transcript_is_not_filed_again(store, tmp_path, monkeypatch):
    """History is indexed from files the CLI keeps, and deleting a row does
    not delete the file. The end-to-end sweep deleted a conversation and the
    next pass filed it straight back as `general` under a title nobody chose.
    The tombstone is what makes delete mean it."""
    proj = tmp_path / "-Users-x-repo"; proj.mkdir()
    rec = {"type": "assistant", "timestamp": "2026-09-14T10:00:00Z",
           "message": {"role": "assistant", "model": "m",
                       "content": [{"type": "text", "text": "hi"}],
                       "usage": {"input_tokens": 1, "output_tokens": 2}}}
    (proj / "gone.jsonl").write_text(json.dumps(rec), encoding="utf-8")
    monkeypatch.setattr(jsonl, "PROJECTS", tmp_path)

    assert jsonl.index_new(store, {}) == ["gone"]
    store.forget("gone")
    store.db.execute("DELETE FROM sessions WHERE engine_session_id='gone'"); store.db.commit()
    assert jsonl.index_new(store, {}) == [], "a deleted conversation came back"
    assert store.forget("gone") is None          # idempotent
