"""The repository view: local truth always, GitHub when reachable, one group per repository."""
import subprocess
from pathlib import Path

from routers import panels


def _repo(tmp_path: Path, name: str = "proj") -> Path:
    root = tmp_path / name; root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "first"], cwd=root, check=True)
    (root / "a.txt").write_text("x")
    return root


def _one(client, auth_headers, root: Path) -> dict:
    body = client.get("/v2/repos", params={"cwd": [str(root)]}, headers=auth_headers).json()
    assert len(body["repos"]) == 1 and body["outside"] == []
    return body["repos"][0]


def test_a_repo_reads_its_local_state(tmp_path, monkeypatch, client, auth_headers):
    root = _repo(tmp_path)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    r = _one(client, auth_headers, root)
    assert r["name"] == "proj" and r["branch"] == "main"
    assert r["upstream"] is None and r["ahead"] is None, "no remote, no ahead/behind -- not zero"
    assert r["dirty"] == ["a.txt"]
    assert [c["subject"] for c in r["commits"]] == ["first"]
    assert r["commits"][0]["pushed"] is True, "with no upstream nothing is 'unpushed'"
    assert r["slug"] is None and r["github_reason"] == "no remote named origin"
    assert r["cwds"] == [str(root)]


def test_unpushed_commits_are_marked_and_github_failure_keeps_the_local_half(tmp_path, monkeypatch, client, auth_headers):
    root = _repo(tmp_path)
    bare = tmp_path / "origin.git"; subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:someone/proj.git"], cwd=root, check=True)
    # A real upstream to compare against, without the network: push to the bare repo under the github name.
    subprocess.run(["git", "remote", "set-url", "--push", "origin", str(bare)], cwd=root, check=True)
    subprocess.run(["git", "config", "remote.origin.url", str(bare)], cwd=root, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "local only"], cwd=root, check=True)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    r = _one(client, auth_headers, root)
    assert r["ahead"] == 1 and r["behind"] == 0
    assert [(c["subject"], c["pushed"]) for c in r["commits"]] == [("local only", False), ("first", True)]
    assert r["slug"] is None and "remote is not on GitHub" in r["github_reason"]


def test_not_a_repository_is_outside_not_an_error(tmp_path, monkeypatch, client, auth_headers):
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    body = client.get("/v2/repos", params={"cwd": [str(tmp_path)]}, headers=auth_headers).json()
    assert body == {"repos": [], "outside": [str(tmp_path)]}


def test_terminals_group_by_repository_and_keep_their_order(tmp_path, monkeypatch, client, auth_headers):
    # Two terminals in one project -- one at its root, one in a subdirectory --
    # a third in another project, and a fourth in no repository at all.
    a = _repo(tmp_path, "alpha"); (a / "backend").mkdir()
    b = _repo(tmp_path, "beta")
    notes = tmp_path / "notes"; notes.mkdir()
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    body = client.get("/v2/repos", params={"cwd": [str(b), str(a / "backend"), str(notes), str(a)]}, headers=auth_headers).json()
    assert [r["name"] for r in body["repos"]] == ["beta", "alpha"], "first-seen order, not alphabetical"
    assert body["repos"][0]["cwds"] == [str(b)]
    assert body["repos"][1]["cwds"] == [str(a / "backend"), str(a)], "the subdirectory and the root are one repository"
    assert body["outside"] == [str(notes)]


def test_a_modified_file_first_in_the_status_keeps_its_first_character(tmp_path, monkeypatch, client, auth_headers):
    """` M path` is the first porcelain line; the helper strips the output,
    and a column-based parse cut the path to `ath`."""
    root = _repo(tmp_path)
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "add a"], cwd=root, check=True)
    (root / "a.txt").write_text("changed")
    (root / "b.txt").write_text("new")
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    assert _one(client, auth_headers, root)["dirty"] == ["a.txt", "b.txt"]


def test_a_commit_is_marked_with_the_session_that_was_live_when_it_was_made(tmp_path, monkeypatch, client, auth_headers):
    """No trailer in the message; the mark comes from which session ran in
    this repository at the time. Two live at once: the most recently started
    wins. None live: no mark."""
    from datetime import datetime, timedelta, timezone
    root = _repo(tmp_path)
    now = datetime.now(timezone.utc)
    iso = lambda d: d.isoformat().replace("+00:00", "Z")  # noqa: E731
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    monkeypatch.setattr("jobs.find_job_for_cwd", lambda mode, cwd: None)  # nobody's project
    monkeypatch.setattr("orchestrator.store.ConversationStore.sessions_all", lambda self: [])
    monkeypatch.setattr("orchestrator.store.ConversationStore.sessions_in", lambda self, r: [
        {"mode": "general", "cwd": str(root), "started_at": iso(now - timedelta(hours=2)), "ended_at": iso(now + timedelta(minutes=5))},
        {"mode": "faber", "cwd": str(root / "backend"), "started_at": iso(now - timedelta(hours=1)), "ended_at": None},
    ])
    assert _one(client, auth_headers, root)["commits"][0]["mode"] == "faber", "the later-started of two live sessions"
    monkeypatch.setattr("orchestrator.store.ConversationStore.sessions_in", lambda self, r: [
        {"mode": "faber", "cwd": str(root), "started_at": iso(now - timedelta(days=2)), "ended_at": iso(now - timedelta(days=1))},
    ])
    assert _one(client, auth_headers, root)["commits"][0]["mode"] is None, "no session was live; made by hand"
    # Nothing ran here, but a Vesper session elsewhere was live: the vault
    # is written from every mode's directory, so that is whose it was.
    monkeypatch.setattr("orchestrator.store.ConversationStore.sessions_all", lambda self: [
        {"mode": "vesper", "cwd": "/elsewhere", "started_at": iso(now - timedelta(minutes=30)), "ended_at": None},
    ])
    assert _one(client, auth_headers, root)["commits"][0]["mode"] == "vesper"


def test_every_commit_to_a_dev_jobs_project_is_fabers(tmp_path, monkeypatch, client, auth_headers):
    """The repository is the job's project_path, so the work is Faber's --
    whichever terminal typed the command, and even when the only session
    the store knows of was filed as General."""
    root = _repo(tmp_path)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    monkeypatch.setattr("jobs.find_job_for_cwd", lambda mode, cwd: "noctis-os" if mode == "faber" else None)
    monkeypatch.setattr("orchestrator.store.ConversationStore.sessions_in", lambda self, r: (_ for _ in ()).throw(AssertionError("ownership decides; the clock is not consulted")))
    assert _one(client, auth_headers, root)["commits"][0]["mode"] == "faber"


def _with_origin(tmp_path: Path) -> Path:
    """A repo with a bare origin it has pushed to once."""
    root = _repo(tmp_path)
    bare = tmp_path / "origin.git"; subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=root, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=root, check=True)
    return root


def _commit(root: Path, msg: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", msg], cwd=root, check=True)


def test_the_push_button_pushes_and_refuses_attribution_lines(tmp_path, monkeypatch, client, auth_headers):
    """The one action the view performs, and the check that would have
    stopped four commits reaching GitHub with a Claude co-author line."""
    root = _with_origin(tmp_path)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    _commit(root, "fine on its own")
    _commit(root, "tainted\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>\nClaude-Session: https://x")
    r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
    assert r.status_code == 409 and "2 attribution lines" in r.json()["detail"]
    assert subprocess.run(["git", "rev-list", "--count", "origin/main..HEAD"], cwd=root, capture_output=True, text=True).stdout.strip() == "2", "nothing was pushed"
    # Strip it and go.
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "--amend", "-m", "clean now"], cwd=root, check=True)
    r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["pushed"] is True and r.json()["force"] is False
    assert subprocess.run(["git", "rev-list", "--count", "origin/main..HEAD"], cwd=root, capture_output=True, text=True).stdout.strip() == "0"


def test_a_diverged_branch_needs_an_explicit_force(tmp_path, monkeypatch, client, auth_headers):
    root = _with_origin(tmp_path)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    # Rewrite the pushed commit: same content, new hash -- what filter-repo leaves behind.
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "--amend", "-m", "first, reworded"], cwd=root, check=True)
    r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
    assert r.status_code == 409 and "force" in r.json()["detail"]
    r = client.post("/v2/repos/push", json={"cwd": str(root), "force": True}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["force"] is True
    assert subprocess.run(["git", "log", "-1", "--format=%s", "origin/main"], cwd=root, capture_output=True, text=True).stdout.strip() == "first, reworded"


def test_check_rollup_is_one_word():
    assert panels._rollup([]) is None
    assert panels._rollup([{"conclusion": "SUCCESS"}]) == "pass"
    assert panels._rollup([{"conclusion": "SUCCESS"}, {"state": "PENDING"}]) == "pending"
    assert panels._rollup([{"conclusion": "FAILURE"}, {"state": "PENDING"}]) == "fail"


def test_the_local_half_names_the_slug_and_leaves_github_to_its_own_route(tmp_path, monkeypatch, client, auth_headers):
    """Three network calls per repository made the whole view wait; the
    local read answers at once and carries the slug for the second read."""
    root = _repo(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:someone/proj.git"], cwd=root, check=True)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    calls = []
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: calls.append(a) or None)
    r = _one(client, auth_headers, root)
    assert r["slug"] == "someone/proj" and r["github_reason"] is None
    assert calls == [], "the local read must not touch gh"


def test_a_missing_repository_is_told_apart_from_an_unreachable_github(monkeypatch, client, auth_headers):
    panels._GITHUB_CACHE.clear()
    # gh answers for the account, not for the slug.
    monkeypatch.setattr(panels, "_gh", lambda root, *a: {"login": "someone"} if a[:2] == ("api", "user") else None)
    r = client.get("/v2/repos/github", params={"slug": "someone/gone"}, headers=auth_headers).json()
    assert r["github"] is None and "no repository at someone/gone that someone can see" in r["reason"]
    # gh answers for nothing: that is the network / sign-in case.
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    r = client.get("/v2/repos/github", params={"slug": "someone/gone"}, headers=auth_headers).json()
    assert "could not reach GitHub" in r["reason"]


def test_github_answers_are_cached_for_a_minute_and_failures_are_not(monkeypatch, client, auth_headers):
    panels._GITHUB_CACHE.clear()
    calls = []
    def gh(root, *a):
        calls.append(a[:2])
        if a[:2] == ("repo", "view"):
            return {"url": "https://github.com/me/x", "isPrivate": True, "defaultBranchRef": {"name": "main"}}
        return [{"number": 1, "title": "t", "headRefName": "b", "isDraft": False, "mergeable": "MERGEABLE",
                 "url": "u", "statusCheckRollup": [{"conclusion": "SUCCESS"}], "labels": []}]
    monkeypatch.setattr(panels, "_gh", gh)
    first = client.get("/v2/repos/github", params={"slug": "me/x"}, headers=auth_headers).json()
    assert first["github"]["private"] is True and first["github"]["pull_requests"][0]["checks"] == "pass"
    assert len(calls) == 3, "view, prs and issues -- once each"
    client.get("/v2/repos/github", params={"slug": "me/x"}, headers=auth_headers)
    assert len(calls) == 3, "the second read within a minute is the cache"
    assert client.get("/v2/repos/github", params={"slug": "not a slug"}, headers=auth_headers).status_code == 422


def test_a_detached_head_is_not_a_branch_called_head(tmp_path, monkeypatch, client, auth_headers):
    root = _repo(tmp_path)
    subprocess.run(["git", "checkout", "-q", "--detach"], cwd=root, check=True)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    assert _one(client, auth_headers, root)["branch"] is None
