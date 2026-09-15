#!/usr/bin/env python3
"""System-prompt regression runner — the CLI over `prompts/regression.py`.

    python3 backend/prompts/run_regression.py                 # every case
    python3 backend/prompts/run_regression.py --scope faber   # one mode's cases
    python3 backend/prompts/run_regression.py --scope rule:attribution
    python3 backend/prompts/run_regression.py --verbose       # show replies

Scope follows composition: `system` (or `all`) is the whole suite because
`system.md` is composed into every mode; a mode name is that mode's cases;
`rule:<name>` is every case guarding one rule. Each case reruns once on
failure, three run at a time, and every result is recorded per case in
`backend/data/regression.json` with the hash of the prompt it ran against
-- the same record the Settings card reads.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prompts import regression  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="all", help="all | system | <mode> | rule:<name>")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cases = regression.cases_for(args.scope)
    if not cases:
        print(f"no cases in scope {args.scope!r}")
        return 1
    shown = regression.DEFAULT_MODEL or "per-mode (opus-5, maintenance haiku)"
    print(f"\n{len(cases)} case(s) in scope {args.scope!r} · model {shown} · {regression.PARALLEL} at a time\n")

    def show(r: dict) -> None:
        mark = "PASS" if r["passed"] else "FAIL"
        again = f" (on attempt {r['attempts']})" if r["passed"] and r["attempts"] > 1 else ""
        print(f"  [{r['id']}] {mark}{again}  {r['mode']:<12} {r['rule'] or ''}")
        if not r["passed"]:
            print(f"        {r['why']}")
        if args.verbose and r["reply"]:
            print(f"        {r['reply'][:160].replace(chr(10), ' ')}")

    results = regression.run(args.scope, on_result=show)
    passed = sum(r["passed"] for r in results)
    print(f"\n  {passed}/{len(results)} passed\n")
    if passed == len(results):
        print("PASS — the prompt still produces the behaviour it is meant to.")
        return 0
    print("FAIL — a behaviour the prompt is responsible for has regressed (each failure was tried twice).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
