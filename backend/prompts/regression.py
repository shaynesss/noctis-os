"""The prompt regression suite, as a module: scoped, recorded, cheap to run.

Answers one question -- does this prompt still produce the behaviour it is
supposed to? -- with `second-brain/prompts/regression.jsonl`: one case per
line, each a mode, a prompt, a deterministic string assertion and a `rule`
naming the behaviour it guards. Until 2026-09-15 the only way to run it was
the whole suite, thirteen sessions, whatever had changed. Now:

- **Scope follows composition.** `system.md` is composed into every mode,
  so editing it runs everything; an overlay is composed into one mode, so
  editing `faber.md` runs Faber's cases. `cases_for("faber")` is a pure
  function of what is composed into what, not a judgement.
- **A case runs against a prompt it can name.** Each result carries the
  hash of the composed prompt it ran on; a case whose prompt has changed
  since is `stale`, so "the suite is green" is a state you can see
  accumulate over small runs rather than a thirteen-session ceremony.
- **One failure is a flake, two is a signal.** A failing case reruns once
  before it counts. The suite already believed this -- its pass bar
  tolerated one failure in twelve -- but a budget can hide a real
  regression; a per-case retry cannot.
- **Three at a time.** Cases are independent sessions; a scoped run takes
  one case's wall time, not four. Bounded so a full run does not do to the
  5-hour window what thirteen serial sessions did.

Results live in `backend/data/regression.json`, machine state beside the
history store. Reading the suite is free and never runs a case.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from orchestrator.store import DATA_DIR
from prompts.render import MODES, VAULT, compose

REGRESSION = VAULT / "prompts" / "regression.jsonl"
RESULTS = DATA_DIR / "regression.json"

# Test each mode on the model it actually runs. An earlier version tested
# everything on Haiku, which measured a configuration four of the five modes
# do not ship -- and produced 12/12 then 9/12 on identical input, noise wide
# enough that the suite could not gate anything.
MODE_MODELS = {
    "general": "claude-opus-5",
    "faber": "claude-opus-5",
    "noctua": "claude-opus-5",
    "vesper": "claude-opus-5",
    "maintenance": "claude-haiku-4-5",
}
DEFAULT_MODEL = os.environ.get("REGRESSION_MODEL")      # override for a cheap smoke run
DISALLOWED = "Bash Edit Write WebFetch WebSearch Read Grep Glob"
PARALLEL = 3
# A neutral working directory: the session's cwd CLAUDE.md loads alongside
# what the runner injects, so running from inside noctis-os would set
# dev.md against the overlay under test.
NEUTRAL_CWD = Path(os.environ.get("TMPDIR", "/tmp")) / "noctis-regression-cwd"

Ask = Callable[[str, str], str]


# ------------------------------------------------------------------ cases

def load_cases(path: Path | None = None) -> list[dict]:
    text = (path or REGRESSION).read_text(encoding="utf-8")
    cases = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            cases.append(json.loads(line))
        except ValueError:
            continue
    return cases


def cases_for(scope: str, cases: list[dict] | None = None,
              results_path: Path | None = None) -> list[dict]:
    """The cases an edit to `scope` can affect. `system` and `all` are the
    whole suite; a mode is that mode's cases; a `rule:<name>` is every case
    guarding that rule across modes."""
    cases = load_cases() if cases is None else cases
    if scope in ("system", "all"):
        return cases
    # What the record no longer speaks for: stale results and cases never
    # run. The scope you want after an edit, because re-proving the nine
    # cases an edit could not have touched costs nine sessions to learn
    # nothing.
    if scope == "not current":
        # The results path travels with it. Reading the module-level RESULTS
        # here regardless of what the caller passed made this the one scope
        # whose answer depended on a file the caller had not named.
        return _not_current(cases, results_path)
    if scope.startswith("rule:"):
        rule = scope[len("rule:"):]
        return [c for c in cases if c.get("rule") == rule]
    return [c for c in cases if c.get("mode") == scope]


def _not_current(cases: list[dict], results_path: Path | None = None) -> list[dict]:
    """Cases whose last result was run against a prompt that has since
    changed, plus those never run at all."""
    stored = _load_results(results_path or RESULTS)
    out = []
    for c in cases:
        r = stored.get(c["id"])
        if not r:
            out.append(c)
            continue
        current = prompt_hash(c["mode"]) if (VAULT / "prompts" / "overlays" / f"{c['mode']}.md").exists() else None
        if current and r.get("prompt_hash") != current:
            out.append(c)
    return out


def prompt_hash(mode: str) -> str:
    """The composed prompt a case runs against, as a fingerprint. Changes
    when `system.md` or the mode's overlay changes; nothing else moves it."""
    return hashlib.sha256(compose(mode).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- running

def ask(prompt: str, mode: str) -> str:
    """One `-p` session with the mode's composed prompt in the argv --
    exactly as `interactive.py` hands it to a hosted session."""
    model = DEFAULT_MODEL or MODE_MODELS.get(mode, "claude-opus-5")
    cmd = ["claude", "-p", prompt, "--model", model, "--disallowedTools", DISALLOWED,
           "--output-format", "json", "--append-system-prompt", compose(mode)]
    try:
        NEUTRAL_CWD.mkdir(parents=True, exist_ok=True)
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                             env=dict(os.environ), cwd=NEUTRAL_CWD)
        return json.loads(out.stdout).get("result", "")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, OSError):
        return ""


def judge(case: dict, reply: str) -> tuple[bool, str]:
    """Deterministic: `absent` strings must not appear; `contains` is
    any-of, since several phrasings express one correct behaviour."""
    low = reply.lower()
    forbidden = [a for a in case.get("absent", []) if a.lower() in low]
    wanted = case.get("contains", [])
    hit = (not wanted) or any(w.lower() in low for w in wanted)
    why = []
    if not hit:
        why.append(f"none of {wanted} in reply")
    if forbidden:
        why.append(f"forbidden present: {forbidden}")
    return (hit and not forbidden), "; ".join(why)


def run_case(case: dict, ask_fn: Ask = ask, retries: int = 1) -> dict:
    """One case, rerun once on failure: one failure is a flake, two is a
    signal. The record says how many attempts it took."""
    attempts = 0
    reply, why, passed = "", "", False
    while attempts <= retries:
        attempts += 1
        reply = ask_fn(case["prompt"], case["mode"])
        passed, why = judge(case, reply)
        if passed:
            break
    return {
        "id": case["id"], "mode": case["mode"], "rule": case.get("rule"),
        "passed": passed, "why": why, "attempts": attempts,
        "reply": reply[:300],
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prompt_hash": prompt_hash(case["mode"]),
    }


def _load_results(path: Path) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_results(path: Path, results: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=1), encoding="utf-8")


def run(scope: str = "all", ask_fn: Ask = ask, parallel: int = PARALLEL,
        results_path: Path | None = None, on_result: Callable[[dict], None] | None = None) -> list[dict]:
    """Run the cases `scope` covers, `parallel` at a time, recording each
    result as it lands so a run cut short still leaves its cases current."""
    results_path = results_path or RESULTS
    cases = cases_for(scope)
    lock = threading.Lock()
    out: list[dict] = []

    def one(case: dict) -> dict:
        r = run_case(case, ask_fn)
        with lock:
            stored = _load_results(results_path)
            stored[r["id"]] = r
            _save_results(results_path, stored)
            out.append(r)
        if on_result:
            on_result(r)
        return r

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        list(pool.map(one, cases))
    return sorted(out, key=lambda r: r["id"])


# ----------------------------------------------------------------- status

def status(results_path: Path | None = None, cases: list[dict] | None = None) -> dict:
    """Every case with its last result, and whether that result still
    speaks for the prompt as it is now. Never runs anything."""
    cases = load_cases() if cases is None else cases
    stored = _load_results(results_path or RESULTS)
    hashes = {m: prompt_hash(m) for m in MODES if (VAULT / "prompts" / "overlays" / f"{m}.md").exists()}
    rows = []
    for c in cases:
        r = stored.get(c["id"])
        current = hashes.get(c["mode"])
        rows.append({
            "id": c["id"], "mode": c["mode"], "rule": c.get("rule"), "tests": c.get("tests"),
            "prompt": c.get("prompt"),
            "last": None if not r else {
                "passed": r["passed"], "why": r["why"], "attempts": r["attempts"],
                "ran_at": r["ran_at"], "reply": r["reply"],
                # Ran against a prompt that has since changed: the result is
                # history, not evidence about the prompt as it is now.
                "stale": bool(current) and r.get("prompt_hash") != current,
            },
        })
    scopes = {s: len(cases_for(s, cases)) for s in ["system", *sorted({c["mode"] for c in cases})]}
    # Offered first when there is anything in it: it is the cheap run, and
    # the one that answers "is the record true now".
    not_current = len(_not_current(cases, results_path))
    if not_current:
        scopes = {"not current": not_current, **scopes}
    return {"cases": rows, "scopes": scopes, "path": "prompts/regression.jsonl", "sessions": len(cases)}
