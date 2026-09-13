"""Conversation store — Noctis v2 Stage 2 item 1.

SQLite, not the vault. The vault is the sole source of truth for
*knowledge*; transcripts are *application data*, and the distinction is not
pedantry: markdown transcripts would make every message a git diff and the
daily auto-commit would churn over noise forever.

What earns a place in the vault is *promoted* deliberately (`promote()`),
mirroring how `raw/` → `wiki/` already works. Curation is the point — a
vault that accumulates every transcript automatically stops being a vault.

Search uses FTS5 with the same BM25 ranking as vault retrieval, so history
and vault search behave identically rather than being two different search
experiences bolted together.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the indexer imports this module; a runtime import would cycle
    from .jsonl import Conversation

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("NOCTIS_DATA_DIR", REPO_ROOT / "backend" / "data"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id                INTEGER PRIMARY KEY,
    engine_session_id TEXT UNIQUE,
    mode              TEXT NOT NULL,
    state             TEXT NOT NULL DEFAULT 'running',
    title             TEXT,
    cwd               TEXT,
    started_at        TEXT NOT NULL,
    ended_at          TEXT,
    -- One-line reminder of what this conversation is about, and the message
    -- count it was written from. Cached because generating it costs an
    -- engine call, and regenerated only once the conversation has moved on
    -- enough for the old one to be misleading.
    recap             TEXT,
    recap_at          INTEGER NOT NULL DEFAULT 0,
    -- Which door the row came in through: 'recorder' folded stream events
    -- as Noctis hosted the session, 'transcript' read the CLI's own file
    -- afterwards. The migration's gate compares the two, and a row the
    -- indexer wrote agrees with its transcript by construction -- so the
    -- comparison has to know which rows are a real test and which are not.
    source            TEXT NOT NULL DEFAULT 'recorder'
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    role       TEXT NOT NULL,          -- user | assistant | tool | thinking
    content    TEXT NOT NULL,
    meta       TEXT,                   -- JSON: tool name, args, error flag
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);

-- Per turn, for Stats. No cost column: under a subscription engine the
-- figure is notional and never charged, so storing it would invite a UI
-- that presents quota as spend.
CREATE TABLE IF NOT EXISTS usage (
    id            INTEGER PRIMARY KEY,
    session_id    INTEGER NOT NULL REFERENCES sessions(id),
    mode          TEXT NOT NULL,
    model         TEXT,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    -- What the turn also spent on the CLI's background tier. Stored because
    -- omitting it is how the parser lost ~900 input tokens per turn until
    -- 2026-09-08; a lifetime total that reads only the primary columns
    -- reproduces that undercount one layer down.
    aux_input_tokens  INTEGER NOT NULL DEFAULT 0,
    aux_output_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    -- API list price for this turn. Never a charge; see events.Usage.
    list_cost_usd REAL NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_created ON usage(created_at);

-- Conversations deleted on purpose. History is indexed from transcripts the
-- CLI keeps on disk, and deleting a row does not delete the file -- so
-- without this the next indexing pass filed a deleted conversation straight
-- back, as `general`, under a title nobody chose. A tombstone on the engine
-- id, not a hidden flag on a row: the row is really gone, and this is what
-- keeps it gone.
CREATE TABLE IF NOT EXISTS forgotten (
    engine_session_id TEXT PRIMARY KEY,
    at                TEXT NOT NULL
);

-- Contribution grid + lifetime tokens read from `usage`. Claude Code's own
-- stats-cache.json can seed history but is a periodic cache (observed three
-- months stale), so these rows are authoritative for anything Noctis ran.

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
    USING fts5(content, session_id UNINDEXED, content=messages, content_rowid=id,
               tokenize='porter unicode61');

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, session_id)
    VALUES (new.id, new.content, new.session_id);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, session_id)
    VALUES ('delete', old.id, old.content, old.session_id);
END;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConversationStore:
    def __init__(self, path: Path | str | None = None):
        if path is None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            path = DATA_DIR / "history.db"
        self.path = str(path)
        self._local = threading.local()
        self.db.executescript(SCHEMA)
        self._add_missing_columns()
        self.db.commit()

    def _add_missing_columns(self) -> None:
        """Bring an existing database up to the current schema.

        `CREATE TABLE IF NOT EXISTS` is a no-op on a database that already
        has the table, so a column added later never appears and the next
        INSERT fails on a machine that has been running the older build.

        This is deliberately not a migration framework -- CLAUDE.md rules
        those out, and the vault is the database of record. It is an
        idempotent add-column pass: safe to run on every open, and doing
        nothing when the columns are already there.
        """
        session_cols = {r["name"] for r in self.db.execute("PRAGMA table_info(sessions)")}
        if "source" not in session_cols:
            # Every row that exists before this column did was written by the
            # recorder -- the indexer did not exist yet -- so the default is
            # also the truth for them.
            self.db.execute(
                "ALTER TABLE sessions ADD COLUMN source TEXT NOT NULL DEFAULT 'recorder'")

        usage_cols = {r["name"] for r in self.db.execute("PRAGMA table_info(usage)")}
        for column in ("aux_input_tokens", "aux_output_tokens"):
            if column not in usage_cols:
                self.db.execute(
                    f"ALTER TABLE usage ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
                )
        if "cache_write_tokens" not in usage_cols:
            self.db.execute(
                "ALTER TABLE usage ADD COLUMN cache_write_tokens INTEGER NOT NULL DEFAULT 0"
            )
        if "list_cost_usd" not in usage_cols:
            self.db.execute("ALTER TABLE usage ADD COLUMN list_cost_usd REAL NOT NULL DEFAULT 0")

        session_cols = {r["name"] for r in self.db.execute("PRAGMA table_info(sessions)")}
        if "recap" not in session_cols:
            self.db.execute("ALTER TABLE sessions ADD COLUMN recap TEXT")
        if "recap_at" not in session_cols:
            self.db.execute("ALTER TABLE sessions ADD COLUMN recap_at INTEGER NOT NULL DEFAULT 0")
        if "indexed_bytes" not in session_cols:
            # How much of the transcript this row was read from. Zero for
            # every row that predates the column, which is deliberate: the
            # next pass sees a file larger than zero and re-reads it, so
            # a row filed while its session was still live -- frozen at
            # that moment, 3,387 messages of a 4,219-message conversation
            # when this was found -- heals on the first pass after upgrade.
            self.db.execute(
                "ALTER TABLE sessions ADD COLUMN indexed_bytes INTEGER NOT NULL DEFAULT 0")

    @property
    def db(self) -> sqlite3.Connection:
        """This thread's connection, opened on first use.

        A single shared connection raises "SQLite objects created in a thread
        can only be used in that same thread" -- and FastAPI runs sync routes
        on a threadpool, so a store opened at import time is never on the
        thread that later reads it. One connection per thread is the standard
        answer and keeps every call site unchanged.

        WAL lets a reader (the Stats page) run while a session is writing,
        instead of the two blocking each other; the busy timeout covers the
        moment two writers do overlap.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        """Close this thread's connection. Others close with their thread."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ---------------------------------------------------------- writing
    def open_session(self, mode: str, cwd: str | None = None, title: str | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO sessions (mode, cwd, title, started_at) VALUES (?,?,?,?)",
            (mode, cwd, title, _now()),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def message_count(self, session_id: int) -> int:
        return int(self.db.execute(
            "SELECT COUNT(*) c FROM messages WHERE session_id=?", (session_id,)
        ).fetchone()["c"])

    def save_recap(self, session_id: int, recap: str, at_messages: int) -> None:
        self.db.execute(
            "UPDATE sessions SET recap=?, recap_at=? WHERE id=?",
            (recap, at_messages, session_id),
        )
        self.db.commit()

    def transcript_state(self, engine_session_id: str) -> tuple[int, str, int] | None:
        """(row id, source, bytes read) for a filed session, or None.

        What `index_new` needs to decide between skip, refresh and leave
        alone: a row the recorder wrote has no transcript to be behind, and
        a row the indexer wrote is behind whenever the file has grown.
        """
        row = self.db.execute(
            "SELECT id, source, indexed_bytes FROM sessions WHERE engine_session_id=?",
            (engine_session_id,)).fetchone()
        return (int(row["id"]), str(row["source"]), int(row["indexed_bytes"])) if row else None

    def find_by_engine_id(self, engine_session_id: str) -> int | None:
        """The row for an existing engine session, if we have one."""
        row = self.db.execute(
            "SELECT id FROM sessions WHERE engine_session_id=?", (engine_session_id,)
        ).fetchone()
        return int(row["id"]) if row else None

    def reopen(self, row_id: int) -> None:
        """Mark a finished conversation live again for another turn."""
        self.db.execute(
            "UPDATE sessions SET state='running', ended_at=NULL WHERE id=?", (row_id,)
        )
        self.db.commit()

    def add_message(self, session_id: int, role: str, content: str,
                    meta: dict[str, Any] | None = None) -> None:
        if not content.strip():
            return          # empty thinking blocks are the common case; skip
        self.db.execute(
            "INSERT INTO messages (session_id, role, content, meta, created_at) VALUES (?,?,?,?,?)",
            (session_id, role, content, json.dumps(meta) if meta else None, _now()),
        )
        self.db.commit()

    def ingest(self, conv: "Conversation", mode: str, transcript_bytes: int = 0) -> int | None:
        """Take a conversation read from the CLI's own transcript.

        The only door into these tables now. There used to be a recorder
        that folded stream events as Noctis hosted a session; it could only
        see sessions Noctis streamed, and the comparison in `jsonl.diff_against`
        showed it undercounting every one of them. Terminal sessions, VS Code
        sessions, anything the CLI ran: all arrive here, from the transcript
        the CLI itself wrote.

        Idempotent on the engine id, so re-running over the same files is
        free. Returns the row id when it wrote one, None when it declined.
        """
        if not conv.engine_session_id or not conv.turns:
            return None
        if self.find_by_engine_id(conv.engine_session_id) is not None:
            return None

        try:
            cur = self.db.execute(
                "INSERT INTO sessions (engine_session_id, mode, state, title, cwd,"
                " started_at, ended_at, source, indexed_bytes)"
                " VALUES (?,?,?,?,?,?,?,'transcript',?)",
                (conv.engine_session_id, mode, "done", conv.title, conv.cwd,
                 conv.started_at or _now(), conv.ended_at or _now(), transcript_bytes),
            )
        except sqlite3.IntegrityError:
            # engine_session_id is UNIQUE. Losing this race means another
            # pass filed the same transcript between the check above and
            # here -- the row exists, which is the outcome wanted, so this
            # declines the same way it would have had it seen the row first.
            self.db.rollback()
            return None
        row_id = int(cur.lastrowid)
        self._write_body(row_id, conv, mode)
        return row_id

    def refresh(self, row_id: int, conv: "Conversation", transcript_bytes: int,
                mode: str | None = None) -> None:
        """Bring a filed session up to its transcript.

        A transcript is appended to for as long as its session runs, and a
        session can be filed at any point in that -- Stats indexes on every
        visit, and every terminal that ends indexes for all of them. The
        first version filed once and never looked again, so a session
        indexed mid-life was a truncated conversation in history for good.
        Messages and turns are replaced wholesale rather than appended: the
        CLI rewrites nothing, but reasoning about "the part after byte N"
        across a line the last read cut in half is not worth a few
        milliseconds. The recap is left alone; it already knows how far the
        conversation has moved since it was written (`recap_at`).

        `mode` is only applied when given: a row filed as `general` because
        the status line had not yet said which mode launched it takes the
        mode once known, and never loses one it has.
        """
        self.db.execute("DELETE FROM messages WHERE session_id=?", (row_id,))
        self.db.execute("DELETE FROM usage WHERE session_id=?", (row_id,))
        self.db.execute(
            "UPDATE sessions SET title=?, cwd=?, ended_at=?, indexed_bytes=?,"
            " mode=COALESCE(?, mode) WHERE id=?",
            (conv.title, conv.cwd, conv.ended_at or _now(), transcript_bytes, mode, row_id))
        row_mode = str(self.db.execute(
            "SELECT mode FROM sessions WHERE id=?", (row_id,)).fetchone()["mode"])
        self._write_body(row_id, conv, row_mode)

    def _write_body(self, row_id: int, conv: "Conversation", mode: str) -> None:
        for m in conv.messages:
            meta = m.get("meta")
            self.db.execute(
                "INSERT INTO messages (session_id, role, content, meta, created_at)"
                " VALUES (?,?,?,?,?)",
                (row_id, m["role"], m["content"], meta, conv.started_at or _now()),
            )
        for t in conv.turns:
            # One raw count, no split: aux_* are written as zero, which is what
            # they become once the migration retires them.
            self.db.execute(
                "INSERT INTO usage (session_id, mode, model, input_tokens, output_tokens,"
                " cached_tokens, cache_write_tokens, aux_input_tokens, aux_output_tokens,"
                " duration_ms, list_cost_usd, created_at)"
                " VALUES (?,?,?,?,?,?,?,0,0,0,0,?)",
                (row_id, mode, t.model, t.input_tokens, t.output_tokens,
                 t.cached_tokens, t.cache_write_tokens, conv.ended_at or _now()),
            )
        self.db.commit()

    def forget(self, engine_session_id: str) -> None:
        """Mark an engine id as deleted on purpose, so the indexer will not
        file its transcript again. Idempotent."""
        self.db.execute(
            "INSERT OR IGNORE INTO forgotten (engine_session_id, at) VALUES (?, ?)",
            (engine_session_id, _now()))
        self.db.commit()

    def is_forgotten(self, engine_session_id: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM forgotten WHERE engine_session_id=?",
            (engine_session_id,)).fetchone() is not None

    def tokens_for_engine_id(self, engine_session_id: str) -> int | None:
        """What the recorder counted for one session, for comparison with what
        the transcript says. None when the recorder never saw it.

        Recorder rows only. A session the indexer filed has usage rows copied
        from its transcript, so comparing those against the transcript is a
        tautology that would pad the agreement count with rows that tested
        nothing -- on first run 30/45 "agreed" and an unknown share of those
        were exactly that.
        """
        row = self.db.execute(
            "SELECT sum(u.input_tokens+u.output_tokens+u.cached_tokens+u.cache_write_tokens)"
            " FROM usage u JOIN sessions s ON s.id=u.session_id"
            " WHERE s.engine_session_id=? AND s.source='recorder'",
            (engine_session_id,)).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def close_session(self, session_id: int, state: str = "done") -> None:
        self.db.execute("UPDATE sessions SET state=?, ended_at=? WHERE id=?",
                        (state, _now(), session_id))
        self.db.commit()

    # ---------------------------------------------------------- reading
    def search(self, query: str, limit: int = 20) -> list[sqlite3.Row]:
        """Ranked search over the transcript. Same BM25 mechanism as vault
        retrieval, and the same k: recall matters more than precision when a
        model does the filtering."""
        terms = [f'"{w}"' for w in query.split() if len(w) > 2]
        if not terms:
            return []
        try:
            return self.db.execute(
                "SELECT m.id, m.session_id, m.role, m.content, m.created_at, s.mode,"
                "       bm25(messages_fts) AS rank"
                "  FROM messages_fts JOIN messages m ON m.id = messages_fts.rowid"
                "  JOIN sessions s ON s.id = m.session_id"
                " WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?",
                (" OR ".join(terms), limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    def transcript(self, session_id: int) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT role, content, meta, created_at FROM messages"
            " WHERE session_id=? ORDER BY id", (session_id,)).fetchall()

    def recent_sessions(
        self, limit: int = 20, mode: str | None = None, resumable_only: bool = False
    ) -> list[sqlite3.Row]:
        """The newest conversations, optionally only one mode's and only the
        ones that can be continued.

        Filtered in SQL rather than by the caller, because the limit applies
        *before* any filtering a caller could do: the shell asked for twenty
        rows and looked through them for the newest resumable General
        session, so a run of twenty newer rows of any other shape hid a
        session that was there the whole time.

        `resumable_only` matches the flag the route publishes -- an engine id
        we know, and not a failed spawn -- rather than `resumable()` below,
        which additionally requires state='done' and so would exclude a
        conversation cut short by a closed window.
        """
        sql = "SELECT * FROM sessions"
        where, args = [], []
        if mode:
            where.append("mode=?")
            args.append(mode)
        if resumable_only:
            where.append("engine_session_id IS NOT NULL AND state != 'failed'")
        if where:
            sql += " WHERE " + " AND ".join(where)
        args.append(limit)
        return self.db.execute(sql + " ORDER BY started_at DESC LIMIT ?", args).fetchall()

    def resumable(self, mode: str | None = None) -> list[sqlite3.Row]:
        sql = ("SELECT * FROM sessions WHERE engine_session_id IS NOT NULL"
               " AND state='done'")
        args: tuple = ()
        if mode:
            sql += " AND mode=?"
            args = (mode,)
        return self.db.execute(sql + " ORDER BY started_at DESC", args).fetchall()

    # ---------------------------------------------------------- stats
    def daily_activity(self, days: int = 365) -> list[sqlite3.Row]:
        """Sessions per day, for the contribution grid."""
        return self.db.execute(
            "SELECT date(started_at) AS day, COUNT(*) AS sessions"
            "  FROM sessions WHERE started_at >= date('now', ?)"
            " GROUP BY day ORDER BY day", (f"-{days} days",)).fetchall()

    def lifetime_tokens(self) -> sqlite3.Row:
        """Totals across every turn Noctis has run.

        `input`/`output` include the background tier: this is the
        what-did-my-day-cost question, where leaving it out is simply an
        undercount. The primary-only columns stay available separately for
        the per-turn view, which is the other question.
        """
        return self.db.execute(
            "SELECT COALESCE(SUM(input_tokens + aux_input_tokens),0) AS input,"
            "       COALESCE(SUM(output_tokens + aux_output_tokens),0) AS output,"
            "       COALESCE(SUM(input_tokens),0) AS primary_input,"
            "       COALESCE(SUM(output_tokens),0) AS primary_output,"
            "       COALESCE(SUM(cached_tokens),0) AS cached,"
            "       COALESCE(SUM(cache_write_tokens),0) AS cache_write,"
            "       COALESCE(SUM(list_cost_usd),0) AS list_cost,"
            "       SUM(CASE WHEN list_cost_usd > 0 THEN 1 ELSE 0 END) AS priced_turns,"
            "       COUNT(*) AS turns,"
            "       MIN(created_at) AS since FROM usage").fetchone()

    def recent_cwds(self, limit: int = 8) -> list[str]:
        """Working directories actually used, most recent first.

        The launcher offered a hardcoded list of three, which was fiction
        wearing the shape of history — it named the same directories whether
        or not you had ever opened them, and would not learn a new project.
        """
        # Ordered by id, not by started_at: the timestamp has one-second
        # resolution, so two sessions begun in the same second tie and the
        # order becomes arbitrary. The id is monotonic and cannot.
        rows = self.db.execute(
            "SELECT cwd, MAX(id) AS last FROM sessions"
            " WHERE cwd IS NOT NULL AND cwd != ''"
            " GROUP BY cwd ORDER BY last DESC LIMIT ?", (limit,)).fetchall()
        return [r["cwd"] for r in rows]

    def promote(self, session_id: int, vault_path: Path, rel_path: str,
                title: str, note: str = "") -> Path:
        """Write a session's transcript into the vault as a real note.

        The deliberate half of "SQLite with promotion": nothing reaches the
        vault automatically. Refuses to overwrite, because a promoted note
        may have been edited by hand after promotion and silently replacing
        that would lose work the store never saw.
        """
        target = vault_path / rel_path
        if target.exists():
            raise FileExistsError(f"{rel_path} already exists — promotion never overwrites")
        s = self.db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if s is None:
            raise ValueError(f"no session {session_id}")

        lines = [f"# {title}", "",
                 f"> Promoted from a {s['mode']} session on {_now()[:10]}. "
                 f"Transcript lives in the conversation store; this note is the curated part.", ""]
        if note:
            lines += [note, "", "---", ""]
        for m in self.transcript(session_id):
            if m["role"] == "thinking":
                continue                      # empty by default, and noise when not
            label = {"user": "**You**", "assistant": "**Claude**"}.get(m["role"], f"`{m['role']}`")
            lines += [f"{label} — {m['content']}", ""]

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines))
        return target
