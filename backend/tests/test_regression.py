"""The regression suite as a module: scope follows composition, a failure
reruns once, results are recorded per case against the prompt they ran on.
Nothing here starts a session -- `ask` is always replaced."""
from pathlib import Path

import pytest

from prompts import regression

CASES = [
    {"id": "r01", "mode": "faber", "rule": "attribution", "prompt": "commit msg", "absent": ["Co-Authored-By"], "tests": "attribution"},
    {"id": "r02", "mode": "faber", "rule": "confusion-protocol", "prompt": "add caching", "contains": ["assum", "clarif"], "tests": "cp"},
    {"id": "r07", "mode": "maintenance", "rule": "propose-never-apply", "prompt": "fix it", "contains": ["propose"], "tests": "pna"},
    {"id": "r13", "mode": "general", "rule": "mode-identity", "prompt": "who are you", "absent": ["Faber here"], "tests": "identity"},
]


def test_scope_follows_composition():
    """system.md is composed into every mode, so it scopes to everything;
    an overlay is composed into one mode; a rule crosses modes."""
    assert [c["id"] for c in regression.cases_for("system", CASES)] == ["r01", "r02", "r07", "r13"]
    assert [c["id"] for c in regression.cases_for("all", CASES)] == ["r01", "r02", "r07", "r13"]
    assert [c["id"] for c in regression.cases_for("faber", CASES)] == ["r01", "r02"]
    assert [c["id"] for c in regression.cases_for("rule:attribution", CASES)] == ["r01"]
    assert regression.cases_for("vesper", CASES) == []


def test_judge_is_deterministic_and_any_of():
    ok, why = regression.judge(CASES[0], "Fix null check in auth.py")
    assert ok and why == ""
    ok, why = regression.judge(CASES[0], "Fix it\n\nCo-Authored-By: someone")
    assert not ok and "forbidden" in why
    # `contains` is any-of: one phrasing of the right behaviour is enough.
    assert regression.judge(CASES[1], "I'd want to clarify the target first")[0]
    assert not regression.judge(CASES[1], "Done, added Redis.")[0]


def test_a_failure_reruns_once_and_the_record_says_so(monkeypatch):
    """One failure is a flake, two is a signal. The retry is per case, so a
    real regression cannot hide inside a suite-wide tolerance."""
    monkeypatch.setattr(regression, "prompt_hash", lambda m: "h1")
    replies = iter(["Co-Authored-By: x", "clean"])
    r = regression.run_case(CASES[0], ask_fn=lambda p, m: next(replies))
    assert r["passed"] and r["attempts"] == 2
    always_bad = lambda p, m: "Co-Authored-By: x"   # noqa: E731
    r = regression.run_case(CASES[0], ask_fn=always_bad)
    assert not r["passed"] and r["attempts"] == 2 and "forbidden" in r["why"]
    assert r["prompt_hash"] == "h1"


def test_run_records_each_case_as_it_lands(tmp_path, monkeypatch):
    monkeypatch.setattr(regression, "prompt_hash", lambda m: "h1")
    monkeypatch.setattr(regression, "load_cases", lambda path=None: CASES)
    landed = []
    out = regression.run("faber", ask_fn=lambda p, m: "I would clarify; no trailer",
                         parallel=2, results_path=tmp_path / "r.json", on_result=landed.append)
    assert [r["id"] for r in out] == ["r01", "r02"] and all(r["passed"] for r in out)
    assert sorted(r["id"] for r in landed) == ["r01", "r02"]
    stored = regression._load_results(tmp_path / "r.json")
    assert set(stored) == {"r01", "r02"}


def test_status_marks_a_result_stale_when_the_prompt_moved(tmp_path, monkeypatch):
    """A result speaks for the prompt it ran against. Once the prompt
    changes, the result is history, and the card must not show it as a
    current pass."""
    hashes = {"faber": "h1", "maintenance": "m1", "general": "g1"}
    monkeypatch.setattr(regression, "prompt_hash", lambda m: hashes[m])
    monkeypatch.setattr(regression, "MODES", ("faber", "maintenance", "general"))
    monkeypatch.setattr(regression, "VAULT", tmp_path)
    for m in hashes:
        (tmp_path / "prompts" / "overlays").mkdir(parents=True, exist_ok=True)
        (tmp_path / "prompts" / "overlays" / f"{m}.md").write_text("x")
    regression._save_results(tmp_path / "r.json", {
        "r01": {"passed": True, "why": "", "attempts": 1, "ran_at": "t", "reply": "", "prompt_hash": "h1"},
        "r07": {"passed": True, "why": "", "attempts": 1, "ran_at": "t", "reply": "", "prompt_hash": "OLD"},
    })
    s = regression.status(results_path=tmp_path / "r.json", cases=CASES)
    by = {c["id"]: c for c in s["cases"]}
    assert by["r01"]["last"]["passed"] and not by["r01"]["last"]["stale"]
    assert by["r07"]["last"]["stale"]                       # maintenance.md moved on
    assert by["r13"]["last"] is None                        # never run
    assert s["scopes"] == {"system": 4, "faber": 2, "general": 1, "maintenance": 1}
    assert s["sessions"] == 4


def test_reading_never_runs_and_running_is_one_at_a_time(client, auth_headers, monkeypatch):
    from routers import panels
    monkeypatch.setattr(panels.vault_io, "file_exists", lambda p: True)
    monkeypatch.setattr(regression, "status", lambda: {"cases": [], "scopes": {"system": 4}, "path": "p", "sessions": 4})
    monkeypatch.setattr(regression, "cases_for", lambda scope, cases=None: CASES if scope in ("system", "faber") else [])
    started = []
    monkeypatch.setattr(regression, "run", lambda scope, on_result=None, **k: started.append(scope))
    assert client.get("/v2/regression", headers=auth_headers).json()["scopes"] == {"system": 4}
    assert client.post("/v2/regression/run", headers=auth_headers, json={"scope": "vesper"}).status_code == 404
    assert client.post("/v2/regression/run", headers=auth_headers, json={"scope": "../x"}).status_code == 422
    r = client.post("/v2/regression/run", headers=auth_headers, json={"scope": "faber"})
    assert r.status_code == 200 and r.json() == {"started": "faber", "sessions": 4}
    import time
    for _ in range(50):
        if not client.get("/v2/regression/status", headers=auth_headers).json()["running"]:
            break
        time.sleep(0.02)
    assert started == ["faber"]
    assert client.post("/v2/regression/run").status_code == 401
