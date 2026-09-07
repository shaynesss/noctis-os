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

**Imports the production indexer** (`retrieval.index`) rather than carrying
its own copy. That reverses an earlier decision, deliberately: standalone
made sense while production did not exist, but now it would let the shipped
indexer drift while the eval kept passing against code nobody runs. Sharing
turns this into a real regression test — change the ranking and this tells
you what it cost.
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
sys.path.insert(0, str(REPO_ROOT / "backend"))
VAULT = Path(os.environ.get("VAULT_PATH", REPO_ROOT.parent / "second-brain"))
EVAL_SET = VAULT / "eval" / "retrieval.jsonl"

from retrieval.index import TOP_K, VaultIndex  # noqa: E402

# Recall gates; rank-1 is reported but does not. Gating on rank-1 would
# contradict the design it is measuring: k=20 exists precisely because a
# model reranks, so precision-at-1 describes a consumer this system does not
# have. Reported anyway because a collapse in it would still be a signal
# worth seeing.
THRESHOLDS = {"recall_at_20": 0.80}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="show every miss")


    args = ap.parse_args()

    if not EVAL_SET.exists():
        print(f"eval set not found: {EVAL_SET}", file=sys.stderr)
        return 2

    index = VaultIndex(VAULT)
    n_docs = index.rebuild()
    cases = [json.loads(l) for l in EVAL_SET.read_text().splitlines() if l.strip()]

    by_cat: dict[str, list] = {}
    misses = []

    for c in cases:
        hits = [h.path for h in index.search(c["query"])]
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

    print(f"\nIndexed {n_docs} heading sections · {len(cases)} cases · top-{TOP_K}\n")
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

    passed = R >= THRESHOLDS["recall_at_20"]
    bar = f"recall@{TOP_K} >= {THRESHOLDS['recall_at_20']:.0%} (rank-1 reported, not gated)"
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
