"""The repository view: local truth always, GitHub when reachable."""
import subprocess
from pathlib import Path

from routers import panels


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "proj"; root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "first"], cwd=root, check=True)
    (root / "a.txt").write_text("x")
    return root


def test_a_repo_reads_its_local_state(tmp_path, monkeypatch, client, auth_headers):
    root = _repo(tmp_path)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    r = client.get("/v2/repo", params={"cwd": str(root)}, headers=auth_headers).json()["repo"]
    assert r["name"] == "proj" and r["branch"] == "main"
    assert r["upstream"] is None and r["ahead"] is None, "no remote, no ahead/behind -- not zero"
    assert r["dirty"] == ["a.txt"]
    assert [c["subject"] for c in r["commits"]] == ["first"]
    assert r["commits"][0]["pushed"] is True, "with no upstream nothing is 'unpushed'"
    assert r["github"] is None and r["github_reason"] == "no remote named origin"


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
    r = client.get("/v2/repo", params={"cwd": str(root)}, headers=auth_headers).json()["repo"]
    assert r["ahead"] == 1 and r["behind"] == 0
    assert [(c["subject"], c["pushed"]) for c in r["commits"]] == [("local only", False), ("first", True)]
    assert r["github"] is None and "remote is not on GitHub" in r["github_reason"]


def test_not_a_repository_is_null_not_an_error(tmp_path, monkeypatch, client, auth_headers):
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    assert client.get("/v2/repo", params={"cwd": str(tmp_path)}, headers=auth_headers).json() == {"repo": None}


def test_check_rollup_is_one_word():
    assert panels._rollup([]) is None
    assert panels._rollup([{"conclusion": "SUCCESS"}]) == "pass"
    assert panels._rollup([{"conclusion": "SUCCESS"}, {"state": "PENDING"}]) == "pending"
    assert panels._rollup([{"conclusion": "FAILURE"}, {"state": "PENDING"}]) == "fail"
