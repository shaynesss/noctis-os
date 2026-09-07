"""Vault index — Noctis v2 Stage 2 item 2.

BM25 over SQLite FTS5, built to the configuration measured in Stage 1 item 6
rather than re-derived. Those numbers were not guessable, so they are
recorded here as constants with the evidence attached:

  * **Chunk on headings, not whole documents.** BM25 normalises for length,
    so a 1040-line log.md competing with a 40-line wiki page distorts
    everything. Measured 48% -> 55% overall, and lexical 80% -> 100%.

  * **Weight title and heading columns 1/8/4/1.** A flat index throws away
    the strongest relevance signal a markdown vault has. Worth +5 points on
    its own.

  * **Return k=20, not k=5.** Recall climbs steeply to k≈15-20 then
    plateaus flat through k=40. Five results is a human-reading budget and
    no human reads these — a session reads twenty and picks. This single
    change was worth +20 points, and optimising for rank-1 instead was
    optimising for a consumer this system does not have.

Final measured baseline: **80% recall@20**, with lexical, vague-recall,
temporal and multi-hop all at 100%. The eval harness imports this module, so
that number describes what actually ships rather than a parallel
implementation that can drift.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

TOP_K = 20
RANK = "bm25(chunks, 1.0, 8.0, 4.0, 1.0)"        # path / title / head / body
MIN_CHUNK_CHARS = 400
SKIP_DIRS = {".git", ".obsidian", "node_modules", "__pycache__", "eval", "data"}

# Interrogative scaffolding, not a general stopword list — BM25's IDF already
# handles common English. These are the words that make every natural-language
# question look alike, which drags an OR query toward noise.
QUESTION_WORDS = {
    "what", "when", "where", "which", "who", "why", "how", "did", "does", "the",
    "and", "for", "that", "this", "with", "from", "about", "into", "out",
    "was", "were", "are", "have", "has", "had", "get", "got", "make", "made",
    "thing", "things", "stuff", "something", "own", "not", "but", "its",
}

SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks
USING fts5(path, title, head, body, tokenize='porter unicode61');
"""


@dataclass(frozen=True)
class Hit:
    path: str
    heading: str
    excerpt: str
    score: float


def chunk_markdown(rel_path: str, text: str) -> list[tuple[str, str, str, str]]:
    """Split on markdown headings, keeping each heading with its body.

    Runt sections are merged forward so a document of one-line subheadings
    does not become dozens of near-empty rows, which would dilute IDF.
    """
    title = Path(rel_path).stem
    parts = re.split(r"^(#{1,6} .*)$", text, flags=re.M)
    rows: list[tuple[str, str, str, str]] = []
    buf, head = parts[0], ""
    for i in range(1, len(parts), 2):
        h = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        if len(buf) + len(h) + len(body) < MIN_CHUNK_CHARS:
            buf += h + body
            head += " " + h
            continue
        if buf.strip():
            rows.append((rel_path, title, head.strip(), buf))
        buf, head = h + body, h
    if buf.strip():
        rows.append((rel_path, title, head.strip(), buf))
    return rows


class VaultIndex:
    """A derived cache. Rebuildable from the vault; deleting it loses
    nothing, which is what keeps the vault the sole source of truth."""

    def __init__(self, vault_path: Path, db_path: Path | str = ":memory:"):
        self.vault_path = Path(vault_path)
        self.db = sqlite3.connect(str(db_path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def rebuild(self) -> int:
        """Index every markdown file. Returns the chunk count."""
        self.db.execute("DELETE FROM chunks")
        rows: list[tuple[str, str, str, str]] = []
        for p in sorted(self.vault_path.rglob("*.md")):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            try:
                text = p.read_text(errors="ignore")
            except OSError:
                continue
            rows.extend(chunk_markdown(str(p.relative_to(self.vault_path)), text))
        self.db.executemany("INSERT INTO chunks VALUES (?,?,?,?)", rows)
        self.db.commit()
        return len(rows)

    def search(self, query: str, k: int = TOP_K, per_document: bool = True) -> list[Hit]:
        """Ranked hits. `per_document` collapses several chunks of one file to
        its best chunk, so twenty results mean twenty documents rather than
        twenty slices of the same long note."""
        terms = [f'"{w}"' for w in (w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", query))
                 if w not in QUESTION_WORDS]
        if not terms:
            return []
        try:
            rows = self.db.execute(
                f"SELECT path, head, body, {RANK} AS score FROM chunks"
                f" WHERE chunks MATCH ? ORDER BY score LIMIT ?",
                (" OR ".join(terms), k * 4),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

        seen: set[str] = set()
        hits: list[Hit] = []
        for r in rows:
            if per_document and r["path"] in seen:
                continue
            seen.add(r["path"])
            hits.append(Hit(
                path=r["path"],
                heading=(r["head"] or "").strip().lstrip("#").strip(),
                excerpt=_excerpt(r["body"]),
                score=r["score"],
            ))
            if len(hits) == k:
                break
        return hits

    def close(self) -> None:
        self.db.close()


def _excerpt(body: str, limit: int = 300) -> str:
    text = " ".join(body.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
