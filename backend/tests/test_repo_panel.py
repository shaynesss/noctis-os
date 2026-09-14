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
    assert r["github"] is None and r["github_reason"] == "no remote named origin"
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
    assert r["github"] is None and "remote is not on GitHub" in r["github_reason"]


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


def test_check_rollup_is_one_word():
    assert panels._rollup([]) is None
    assert panels._rollup([{"conclusion": "SUCCESS"}]) == "pass"
    assert panels._rollup([{"conclusion": "SUCCESS"}, {"state": "PENDING"}]) == "pending"
    assert panels._rollup([{"conclusion": "FAILURE"}, {"state": "PENDING"}]) == "fail"


def test_a_missing_repository_is_told_apart_from_an_unreachable_github(tmp_path, monkeypatch, client, auth_headers):
    root = _repo(tmp_path)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:someone/gone.git"], cwd=root, check=True)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    # gh answers for the account, not for the slug.
    monkeypatch.setattr(panels, "_gh", lambda root, *a: {"login": "someone"} if a[:2] == ("api", "user") else None)
    r = _one(client, auth_headers, root)
    assert "no repository at someone/gone that someone can see" in r["github_reason"]
    # gh answers for nothing: that is the network / sign-in case.
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    r = _one(client, auth_headers, root)
    assert "could not reach GitHub" in r["github_reason"]


def test_a_detached_head_is_not_a_branch_called_head(tmp_path, monkeypatch, client, auth_headers):
    root = _repo(tmp_path)
    subprocess.run(["git", "checkout", "-q", "--detach"], cwd=root, check=True)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    assert _one(client, auth_headers, root)["branch"] is None
