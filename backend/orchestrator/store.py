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

from .events import (
    Event, Limits, SessionStart, TextDelta, ThinkingDelta, ToolCall,
    ToolResult, TurnEnd,
)

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
    recap_at          INTEGER NOT NULL DEFAULT 0
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
        usage_cols = {r["name"] for r in self.db.execute("PRAGMA table_info(usage)")}
        for column in ("aux_input_tokens", "aux_output_tokens"):
            if column not in usage_cols:
                self.db.execute(
                    f"ALTER TABLE usage ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0"
                )
        if "list_cost_usd" not in usage_cols:
            self.db.execute("ALTER TABLE usage ADD COLUMN list_cost_usd REAL NOT NULL DEFAULT 0")

        session_cols = {r["name"] for r in self.db.execute("PRAGMA table_info(sessions)")}
        if "recap" not in session_cols:
            self.db.execute("ALTER TABLE sessions ADD COLUMN recap TEXT")
        if "recap_at" not in session_cols:
            self.db.execute("ALTER TABLE sessions ADD COLUMN recap_at INTEGER NOT NULL DEFAULT 0")

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

    def record(self, session_id: int, mode: str, event: Event) -> None:
        """Fold one Event into the store. The manager streams; this listens."""
        if isinstance(event, SessionStart) and event.session_id:
            self.db.execute(
                "UPDATE sessions SET engine_session_id=? WHERE id=?",
                (event.session_id, session_id),
            )
            self.db.commit()
        elif isinstance(event, TextDelta):
            self.add_message(session_id, "assistant", event.text)
        elif isinstance(event, ThinkingDelta):
            self.add_message(session_id, "thinking", event.text)
        elif isinstance(event, ToolCall):
            self.add_message(session_id, "tool", f"{event.name} {event.summary}".strip(),
                             {"tool": event.name, "args": event.args, "id": event.id})
        elif isinstance(event, ToolResult):
            self.add_message(session_id, "tool_result", event.content[:4000],
                             {"id": event.id, "is_error": event.is_error})
        elif isinstance(event, TurnEnd):
            u = event.usage
            self.db.execute(
                "INSERT INTO usage (session_id, mode, model, input_tokens, output_tokens,"
                " cached_tokens, aux_input_tokens, aux_output_tokens, duration_ms,"
                " list_cost_usd, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (session_id, mode, u.model, u.input_tokens, u.output_tokens,
                 u.cached_tokens, u.aux_input_tokens, u.aux_output_tokens,
                 event.duration_ms, u.list_cost_usd, _now()),
            )
            self.db.commit()

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

    def recent_sessions(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()

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
            "       COALESCE(SUM(list_cost_usd),0) AS list_cost,"
            "       COUNT(*) AS turns,"
            "       MIN(created_at) AS since FROM usage").fetchone()

    def usage_by_mode(self) -> list[sqlite3.Row]:
        """Which modes the tokens actually went to."""
        return self.db.execute(
            "SELECT mode,"
            "       COALESCE(SUM(input_tokens + aux_input_tokens),0) AS input,"
            "       COALESCE(SUM(output_tokens + aux_output_tokens),0) AS output,"
            "       COUNT(*) AS turns FROM usage"
            " GROUP BY mode ORDER BY output DESC").fetchall()

    # ---------------------------------------------------------- promotion
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


def fold(store: ConversationStore, session_id: int, mode: str,
         events: Iterable[Event]) -> None:
    for e in events:
        store.record(session_id, mode, e)
