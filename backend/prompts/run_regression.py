#!/usr/bin/env python3
"""System-prompt regression runner — Noctis v2 Stage 1 item 7.

Runs `second-brain/prompts/regression.jsonl` against the composed prompt for
each case's mode and asserts on the reply. Answers one question: **does this
prompt still produce the behaviour it is supposed to?**

    python3 backend/prompts/run_regression.py
    python3 backend/prompts/run_regression.py --verbose      # show replies
    python3 backend/prompts/run_regression.py --config-dir   # production path

Assertions are deterministic string checks, not a model-as-judge. That is a
deliberate trade: a judge would catch nuance this misses, but it doubles the
cost, adds its own variance, and turns a regression suite into something you
stop running. Cheap and boring is what gets run.

Injection: by default the composed prompt goes in via `--append-system-prompt`,
because the per-mode config dirs are created but not yet logged in (Claude Code
keys credentials to the config-dir path). `--config-dir` uses the production
path instead and should be preferred once those logins exist. The two are not
identical mechanisms -- project memory vs. an appended system prompt -- so a
green run under the default is evidence about the prompt's *content*, not
final proof of the production wiring.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from render import CONFIG_ROOT, VAULT, compose  # noqa: E402

REGRESSION = VAULT / "prompts" / "regression.jsonl"
MODEL = os.environ.get("REGRESSION_MODEL", "claude-haiku-4-5")
PASS_BAR = 11 / 12  # 11 of 12; one flake tolerated, two is a real signal

DISALLOWED = "Bash Edit Write WebFetch WebSearch Read Grep Glob"


# A neutral working directory. The session's cwd project CLAUDE.md loads
# alongside whatever this runner injects, so running from inside noctis-os
# means dev.md's methodology competes with the mode overlay under test --
# observed directly on 2026-09-07, when a maintenance-mode case replied by
# quoting the global CLAUDE.md instead.
NEUTRAL_CWD = Path(os.environ.get("TMPDIR", "/tmp")) / "noctis-regression-cwd"


def ask(prompt: str, mode: str, use_config_dir: bool) -> str:
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--disallowedTools", DISALLOWED,
           "--output-format", "json"]
    env = dict(os.environ)
    if use_config_dir:
        env["CLAUDE_CONFIG_DIR"] = str(CONFIG_ROOT / mode)
    else:
        cmd += ["--append-system-prompt", compose(mode)]
    try:
        NEUTRAL_CWD.mkdir(parents=True, exist_ok=True)
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                             env=env, cwd=NEUTRAL_CWD)
        return json.loads(out.stdout).get("result", "")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--config-dir", action="store_true",
                    help="inject via CLAUDE_CONFIG_DIR (needs those dirs logged in)")
    args = ap.parse_args()

    cases = [json.loads(l) for l in REGRESSION.read_text().splitlines() if l.strip()]
    inject = "CLAUDE_CONFIG_DIR" if args.config_dir else "--append-system-prompt"
    print(f"\n{len(cases)} cases · model {MODEL} · injected via {inject}\n")

    passed, failures = 0, []
    for c in cases:
        reply = ask(c["prompt"], c["mode"], args.config_dir)
        low = reply.lower()

        missing_absent = [a for a in c.get("absent", []) if a.lower() in low]
        # `contains` is any-of: several phrasings can express the same
        # correct behaviour, and demanding one exact wording would make the
        # suite fail on paraphrase rather than on regression.
        wanted = c.get("contains", [])
        hit_contains = (not wanted) or any(w.lower() in low for w in wanted)

        ok = hit_contains and not missing_absent
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"  [{c['id']}] {mark}  {c['mode']:<12} {c['tests'][:52]}")
        if not ok:
            why = []
            if not hit_contains:
                why.append(f"none of {wanted} in reply")
            if missing_absent:
                why.append(f"forbidden present: {missing_absent}")
            failures.append((c, reply, "; ".join(why)))
        if args.verbose and reply:
            print(f"        {reply[:160].replace(chr(10), ' ')}")

    rate = passed / len(cases)
    print(f"\n  {passed}/{len(cases)} passed ({rate:.0%}) · bar {PASS_BAR:.0%}\n")

    if failures:
        print("Failures:")
        for c, reply, why in failures:
            print(f"  [{c['id']}] {why}")
            print(f"        prompt: {c['prompt'][:70]}")
            print(f"        reply:  {(reply[:150] or '(empty)').replace(chr(10), ' ')}\n")

    if rate >= PASS_BAR:
        print("PASS — the prompt still produces the behaviour it is meant to.")
        return 0
    print("FAIL — a behaviour the prompt is responsible for has regressed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
