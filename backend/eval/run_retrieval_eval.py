#!/usr/bin/env python3
"""Retrieval eval harness — Noctis v2 Stage 1 item 6.

Builds a throwaway SQLite FTS5 index over the vault, runs the eval set at
`second-brain/eval/retrieval.jsonl`, and reports recall@5, rank-1 and MRR
overall and per category.

Its job is to answer one question before Stage 2 item 2 commits to an
approach: **is BM25 alone good enough, or is a local embedding model
warranted?** The threshold is in THRESHOLDS below. Reaching it means ship
BM25; missing it on the paraphrase/vague-recall categories specifically is
the signal that lexical search has hit its ceiling, which is exactly the
gap embeddings close.

    python3 backend/eval/run_retrieval_eval.py
    python3 backend/eval/run_retrieval_eval.py --verbose   # show every miss

Deliberately standalone: it builds its own index rather than importing the
app's, so the measurement exists before the thing it measures and cannot be
quietly invalidated by a change to production indexing code.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT = Path(os.environ.get("VAULT_PATH", REPO_ROOT.parent / "second-brain"))
EVAL_SET = VAULT / "eval" / "retrieval.jsonl"

# k=20, not 5. A sweep on 2026-09-07 found recall climbing steeply to ~80%
# by k=15-20 and then plateauing. Five results is a human-reading budget;
# there is a model reading these, and it can filter twenty. Optimising for
# rank-1 optimises for a consumer this system does not have.
TOP_K = 20
THRESHOLDS = {"recall_at_5": 0.80, "rank_1": 0.25}

# Title and heading text is a far stronger relevance signal than body prose,
# and a flat index throws that away. Weighting them was worth +5 points on
# its own, before any change to k.
RANK = "bm25(docs, 1.0, 8.0, 4.0, 1.0)"

SKIP_DIRS = {".git", ".obsidian", "node_modules", "__pycache__", "eval"}


def load_vault(db: sqlite3.Connection, chunked: bool) -> int:
    """Index the vault, either whole-document or split on markdown headings.

    Chunking is not a cosmetic option here. BM25 normalises for document
    length, so a 1040-line log.md competes on very different terms to a
    40-line wiki page; indexing whole documents measures that distortion as
    much as it measures the ranker. Running both configurations is what
    separates "BM25 cannot do this" from "the harness was naive", and only
    the first of those justifies an embedding model.
    """
    db.execute("CREATE VIRTUAL TABLE docs USING fts5(path, title, head, body, tokenize='porter unicode61')")
    rows = []
    for p in VAULT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        rel = str(p.relative_to(VAULT))
        title = Path(rel).stem
        if not chunked:
            rows.append((rel, title, "", text))
            continue
        # Split on any markdown heading; keep the heading with its body so
        # section titles stay searchable alongside their content.
        parts = re.split(r"^(#{1,6} .*)$", text, flags=re.M)
        buf, head = parts[0], ""
        for i in range(1, len(parts), 2):
            h = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            if len(buf) + len(h) + len(body) < 400:   # merge runt sections
                buf += h + body
                head += " " + h
                continue
            if buf.strip():
                rows.append((rel, title, head, buf))
            buf, head = h + body, h
        if buf.strip():
            rows.append((rel, title, head, buf))
    db.executemany("INSERT INTO docs VALUES (?,?,?,?)", rows)
    return len(rows)


# Words carrying no discriminating power in a question. Not a general
# stopword list: BM25's IDF already handles common English. These are the
# interrogative scaffolding that makes every natural-language question look
# alike, which is what drags an OR query toward noise.
QUESTION_WORDS = {
    "what", "when", "where", "which", "who", "why", "how", "did", "does", "the",
    "and", "for", "that", "this", "with", "from", "about", "into", "out",
    "was", "were", "are", "have", "has", "had", "get", "got", "make", "made",
    "thing", "things", "stuff", "something", "own", "not", "but", "its",
}


def search(db: sqlite3.Connection, query: str, k: int = TOP_K,
           cutoff: float | None = None) -> list[str]:
    """Rank by BM25, optionally discarding weak hits.

    The cutoff exists for the negative cases. An OR query matches almost
    every document in a vault this size, so without a relevance floor the
    system returns five confident-looking results for "my Postgres
    production password" — scoring well on recall while being actively
    harmful. A retrieval layer that cannot say "nothing here" is not usable.
    """
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", query)]
    terms = [f'"{w}"' for w in words if w.lower() not in QUESTION_WORDS]
    if not terms:
        return []
    try:
        cur = db.execute(
            f"SELECT path, {RANK} r FROM docs WHERE docs MATCH ? ORDER BY r LIMIT {k * 4}",
            (" OR ".join(terms),),
        )
    except sqlite3.OperationalError:
        return []
    seen, out = set(), []
    for path, score in cur.fetchall():
        if cutoff is not None and score > cutoff:   # bm25() is negative; lower is better
            continue
        if path in seen:                            # chunks collapse to their document
            continue
        seen.add(path)
        out.append(path)
        if len(out) == k:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="show every miss")
    ap.add_argument("--whole-doc", action="store_true",
                    help="index whole documents instead of heading sections")
    # Default: no floor. A sweep on 2026-09-07 found no value that both
    # answers real questions and rejects unanswerable ones -- the score
    # distributions overlap (answerable -15..-18, unanswerable -4..-10.5).
    # At -12 negatives hit 100% but paraphrase, vague-recall, temporal and
    # multi-hop all collapse to 0%. Recall is the more useful failure mode,
    # so the floor is off by default and kept as a flag for re-testing.
    ap.add_argument("--cutoff", type=float, default=None,
                    help="bm25 relevance floor; hits scoring above it are discarded")
    args = ap.parse_args()

    if not EVAL_SET.exists():
        print(f"eval set not found: {EVAL_SET}", file=sys.stderr)
        return 2

    db = sqlite3.connect(":memory:")
    n_docs = load_vault(db, chunked=not args.whole_doc)
    cases = [json.loads(l) for l in EVAL_SET.read_text().splitlines() if l.strip()]

    by_cat: dict[str, list] = {}
    misses = []

    for c in cases:
        hits = search(db, c["query"], cutoff=args.cutoff)
        expect = c.get("expect", [])

        if not expect:  # negative case: success is returning nothing useful
            got = bool(hits)
            rec = 0.0 if got else 1.0
            r1 = rec
            if got:
                misses.append((c, hits, "returned results for an unanswerable query"))
        else:
            rec = 1.0 if any(e in hits for e in expect) else 0.0
            r1 = 1.0 if hits and hits[0] in expect else 0.0
            if rec == 0.0:
                misses.append((c, hits, "expected doc not in top 5"))
            elif r1 == 0.0 and args.verbose:
                misses.append((c, hits, "found, but not ranked first"))

        by_cat.setdefault(c["category"], []).append((rec, r1))

    def agg(pairs):
        n = len(pairs)
        return sum(p[0] for p in pairs) / n, sum(p[1] for p in pairs) / n, n

    mode = "whole documents" if args.whole_doc else "heading sections"
    print(f"\nIndexed {n_docs} {mode} · {len(cases)} cases · top-{TOP_K} · cutoff {args.cutoff}\n")
    print(f"  {'category':<14} {'recall@' + str(TOP_K):>9} {'rank-1':>8} {'n':>4}")
    print(f"  {'-'*14} {'-'*9} {'-'*8} {'-'*4}")
    for cat in ("lexical", "paraphrase", "vague-recall", "temporal", "multi-hop", "negative"):
        if cat in by_cat:
            r, o, n = agg(by_cat[cat])
            print(f"  {cat:<14} {r:>8.0%} {o:>8.0%} {n:>4}")

    all_pairs = [p for v in by_cat.values() for p in v]
    R, O, N = agg(all_pairs)
    print(f"  {'-'*14} {'-'*9} {'-'*8} {'-'*4}")
    print(f"  {'OVERALL':<14} {R:>8.0%} {O:>8.0%} {N:>4}\n")

    if misses:
        print(f"Misses ({len(misses)}):")
        for c, hits, why in misses:
            print(f"  [{c['id']}] {c['category']:<12} {why}")
            print(f"        q: {c['query']}")
            if c.get("expect"):
                print(f"        want: {', '.join(c['expect'])}")
            print(f"        got:  {', '.join(hits[:3]) or '(nothing)'}")
        print()

    passed = R >= THRESHOLDS["recall_at_5"] and O >= THRESHOLDS["rank_1"]
    bar = f"recall@{TOP_K} >= {THRESHOLDS['recall_at_5']:.0%}, rank-1 >= {THRESHOLDS['rank_1']:.0%}"
    if passed:
        print(f"PASS — {bar}. BM25 alone clears the bar; no embedding model needed yet.")
    else:
        print(f"FAIL — {bar}.")
        print("Check which categories carried the loss: paraphrase and vague-recall")
        print("failing while lexical passes is the specific signal that lexical")
        print("search has hit its ceiling, which is the gap embeddings close.")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
