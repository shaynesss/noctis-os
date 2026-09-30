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
    # No remote has it, so it is not on GitHub. This asserted the opposite
    # until 2026-09-29, which is how bello-website read "20, all on GitHub"
    # with no remote at all.
    assert r["commits"][0]["pushed"] is False, "with no remote, nothing is on GitHub"
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


# Every fixture commit carries a body, because the push refuses one without
# from 2026-09-17 and most of these tests are about something else. `at`
# pins the date: a test about the rule must say which side of it a commit
# falls on rather than trusting the clock, which is how three of these went
# red overnight when the cutoff passed.
FIXTURE_BODY = "Leaves the fixture where it was.\nNext: nothing."


def _commit(root: Path, msg: str, body: str | None = FIXTURE_BODY, at: str | None = None) -> None:
    import os
    env = {**os.environ}
    if at:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = at
    message = f"{msg}\n\n{body}" if body else msg
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                    "-m", message], cwd=root, check=True, env=env)


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
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "--amend", "-m", "clean now\n\n" + FIXTURE_BODY], cwd=root, check=True)
    r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["pushed"] is True and r.json()["force"] is False
    assert subprocess.run(["git", "rev-list", "--count", "origin/main..HEAD"], cwd=root, capture_output=True, text=True).stdout.strip() == "0"


def _git_out(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def _commit_on_origin(bare: Path, msg: str, name: str = "Shayne", email: str = "s@s", at: str | None = None) -> str:
    """A commit made on GitHub itself (the web editor, another machine):
    written straight into the bare origin, so this repository has not
    fetched it and its tracking ref still says 0 behind."""
    import os
    env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email}
    if at:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = at
    tree = _git_out(bare, "rev-parse", "main^{tree}")
    sha = subprocess.run(["git", "commit-tree", tree, "-p", "main", "-m", msg], cwd=bare, env=env,
                         capture_output=True, text=True, check=True).stdout.strip()
    _git_out(bare, "update-ref", "refs/heads/main", sha)
    return sha


def test_a_diverged_branch_needs_an_explicit_force(tmp_path, monkeypatch, client, auth_headers):
    root = _with_origin(tmp_path)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    # Rewrite the pushed commit as the trailer strip does: same subject and
    # content, a different body, a new hash -- what filter-repo leaves behind.
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "--amend", "-m", "first\n\n" + FIXTURE_BODY], cwd=root, check=True)
    r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
    assert r.status_code == 409 and "history rewritten here" in r.json()["detail"]
    # The view knows it is a rewrite: GitHub's one commit has a copy here.
    view = _one(client, auth_headers, root)
    assert view["behind"] == 1 and view["upstream_lost"] == 0 and view["upstream_only"][0]["copied"] is True
    r = client.post("/v2/repos/push", json={"cwd": str(root), "force": True}, headers=auth_headers)
    assert r.status_code == 400 and "names the GitHub commit" in r.json()["detail"]
    r = client.post("/v2/repos/push", json={"cwd": str(root), "force": True, "expect": view["upstream_sha"]}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["force"] is True
    assert _git_out(root, "rev-parse", "origin/main") == _git_out(root, "rev-parse", "HEAD")


def test_new_work_on_github_is_named_and_not_mistaken_for_a_rewrite(tmp_path, monkeypatch, client, auth_headers):
    """2026-09-29: two commits made on GitHub were never fetched here. The
    view said 0 behind, the push came back as git's bare "[rejected]", and a
    fresh view would have offered a force push, calling it a rewrite, which
    would have deleted them."""
    root = _with_origin(tmp_path)
    bare = tmp_path / "origin.git"
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    _commit(root, "local work")
    demo = _commit_on_origin(bare, "demo")
    assert _one(client, auth_headers, root)["behind"] == 0, "not fetched yet: the stale picture"

    r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
    detail = r.json()["detail"]
    assert r.status_code == 409 and "GitHub has 1 commit this branch does not" in detail
    assert '"demo" (Shayne, ' in detail and "Bring it in first" in detail
    assert _git_out(bare, "rev-parse", "main") == demo, "nothing was pushed"

    # The push's fetch leaves the view true, and it names the commit.
    view = _one(client, auth_headers, root)
    assert view["behind"] == 1 and view["ahead"] == 1 and view["upstream_lost"] == 1
    assert view["upstream_only"] == [{"sha": demo[:7], "subject": "demo", "author": "Shayne",
                                      "at": view["upstream_only"][0]["at"], "copied": False}]
    assert view["upstream_sha"] == demo


def test_a_force_push_replaces_only_what_it_was_shown(tmp_path, monkeypatch, client, auth_headers):
    """The person confirms against a list. If GitHub moves after that, the
    force would delete a commit nobody was shown, so it refuses."""
    root = _with_origin(tmp_path)
    bare = tmp_path / "origin.git"
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    _commit(root, "local work")
    _commit_on_origin(bare, "demo")
    client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)  # refused; fetches
    shown = _one(client, auth_headers, root)["upstream_sha"]
    later = _commit_on_origin(bare, "made after the view was read")

    r = client.post("/v2/repos/push", json={"cwd": str(root), "force": True, "expect": shown}, headers=auth_headers)
    assert r.status_code == 409 and "changed since this view was read" in r.json()["detail"]
    assert _git_out(bare, "rev-parse", "main") == later, "nothing was replaced"

    # Confirmed against what is there now, it goes: deleting GitHub's two is
    # the person's explicit choice, made against their names.
    r = client.post("/v2/repos/push", json={"cwd": str(root), "force": True, "expect": later}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["force"] is True
    assert _git_out(bare, "rev-parse", "main") == _git_out(root, "rev-parse", "HEAD")


def test_a_projects_notes_are_read_from_the_vault_under_the_project(tmp_path, monkeypatch, client, auth_headers):
    """A build has two commit paths: code in the project, the record in the
    vault. The vault side -- the job's notes folder and job folder -- rides
    under the project as `notes`, with only the commits and dirty files that
    touch those paths. A repository no job owns carries none."""
    project = _repo(tmp_path, "proj")
    vault = _repo(tmp_path, "vault")
    (vault / "wiki" / "Proj").mkdir(parents=True); (vault / "wiki" / "Proj" / "SPEC.md").write_text("spec")
    (vault / "modes" / "dev" / "jobs" / "proj").mkdir(parents=True); (vault / "modes" / "dev" / "jobs" / "proj" / "context.md").write_text("ctx")
    (vault / "log.md").write_text("elsewhere")
    subprocess.run(["git", "add", "-A"], cwd=vault, check=True)
    _commit(vault, "spec and context and log")
    (vault / "log.md").write_text("changed elsewhere")
    subprocess.run(["git", "add", "-A"], cwd=vault, check=True); _commit(vault, "only the log")
    (vault / "wiki" / "Proj" / "SPEC.md").write_text("spec, edited and not committed")
    (vault / "log.md").write_text("dirty elsewhere")
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    monkeypatch.setattr(panels.vault_io, "get_vault_path", lambda: vault)
    monkeypatch.setattr("jobs.find_job_for_cwd", lambda mode, cwd: "proj" if Path(cwd).resolve() == project.resolve() else None)
    monkeypatch.setattr("jobs.job_notes_paths", lambda mode, slug: ["wiki/Proj", "modes/dev/jobs/proj"])
    r = _one(client, auth_headers, project)
    n = r["notes"]
    assert n["name"] == "vault" and n["paths"] == ["wiki/Proj", "modes/dev/jobs/proj"]
    assert [c["subject"] for c in n["commits"]] == ["spec and context and log"], "the log-only commit does not touch the notes"
    assert n["dirty"] == ["wiki/Proj/SPEC.md"], "the dirty log is not the project's business"
    assert n["cwds"] == []
    # The vault itself, read as a repository, carries no notes of its own.
    assert _one(client, auth_headers, vault)["notes"] is None


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


# ------------------------------------------------- attribution by evidence

def _session_with_commit(store, mode: str, cwd: str, subject: str) -> int:
    """A session whose transcript ran `git commit -m <subject>`: what the
    indexer files for a tool call, meta carrying the arguments."""
    sid = store.open_session(mode, cwd=cwd)
    store.db.execute("INSERT INTO messages (session_id, role, content, meta, created_at) VALUES (?,?,?,?,?)",
                     (sid, "tool", "Bash", '{"id": "t1", "args": {"command": "git commit -q -m \\"' + subject + '\\""}}',
                      "2026-09-15T10:00:00+00:00"))
    store.db.commit()
    return sid


def test_a_commit_is_credited_to_the_session_whose_transcript_made_it(tmp_path, monkeypatch, client, auth_headers):
    """Evidence beats proximity. A Noctua tab was live in the vault all
    afternoon while a VS Code session in the project made thirty commits
    to it; every one was marked Noctua. The transcript that ran the commit
    is its author -- and a General-filed session in a dev job's project is
    Faber's."""
    from datetime import datetime, timedelta, timezone
    from orchestrator.store import ConversationStore
    root = _repo(tmp_path)
    project = tmp_path / "noctis-os"; project.mkdir()
    _commit(root, "Log: something long enough to look up")
    store = ConversationStore(tmp_path / "h.db")
    _session_with_commit(store, "general", str(project / "backend"), "Log: something long enough to look up")
    store.close()
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    original_init = ConversationStore.__init__
    monkeypatch.setattr(ConversationStore, "__init__", lambda self, path=None: original_init(self, tmp_path / "h.db"))
    monkeypatch.setattr("jobs.find_job_for_cwd", lambda mode, cwd: "noctis-os" if Path(str(cwd)).resolve() == project.resolve() else None)
    now = datetime.now(timezone.utc)
    iso = lambda d: d.isoformat().replace("+00:00", "Z")  # noqa: E731
    # A Noctua tab live in this very directory the whole time -- the old
    # rule's answer. It must lose to the transcript.
    monkeypatch.setattr(ConversationStore, "sessions_in", lambda self, r: [
        {"mode": "noctua", "cwd": str(root), "started_at": iso(now - timedelta(hours=2)), "ended_at": None}])
    monkeypatch.setattr(ConversationStore, "sessions_all", lambda self: [])
    commits = _one(client, auth_headers, root)["commits"]
    by = {c["subject"]: c for c in commits}
    assert by["Log: something long enough to look up"]["mode"] == "faber", "the VS Code session, in the project, is Faber's"
    assert by["Log: something long enough to look up"]["by"]["cwd"] == str(project / "backend")
    assert by["first"]["mode"] == "noctua", "'first' is too short to look up; the clock still decides that one"


def test_the_record_claims_vault_commits_made_from_inside_the_project(tmp_path, monkeypatch, client, auth_headers):
    """The path rule alone hid the log entry and the lesson a build session
    writes as it goes -- shared files, not under the notes paths. A vault
    commit whose author session was inside the project is the project's
    record too."""
    from orchestrator.store import ConversationStore
    project = _repo(tmp_path, "proj")
    vault = _repo(tmp_path, "vault")
    (vault / "wiki" / "Proj").mkdir(parents=True); (vault / "wiki" / "Proj" / "SPEC.md").write_text("spec")
    (vault / "log.md").write_text("log")
    subprocess.run(["git", "add", "-A"], cwd=vault, check=True); _commit(vault, "spec written for the project")
    (vault / "log.md").write_text("log 2"); subprocess.run(["git", "add", "-A"], cwd=vault, check=True)
    _commit(vault, "Log: the build session's own entry")
    (vault / "log.md").write_text("log 3"); subprocess.run(["git", "add", "-A"], cwd=vault, check=True)
    _commit(vault, "Log: written by Noctua elsewhere")
    store = ConversationStore(tmp_path / "h.db")
    _session_with_commit(store, "general", str(project / "backend"), "Log: the build session's own entry")
    _session_with_commit(store, "noctua", str(vault), "Log: written by Noctua elsewhere")
    store.close()
    original_init = ConversationStore.__init__
    monkeypatch.setattr(ConversationStore, "__init__", lambda self, path=None: original_init(self, tmp_path / "h.db"))
    monkeypatch.setattr(ConversationStore, "sessions_in", lambda self, r: [])
    monkeypatch.setattr(ConversationStore, "sessions_all", lambda self: [])
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    monkeypatch.setattr(panels.vault_io, "get_vault_path", lambda: vault)
    monkeypatch.setattr("jobs.find_job_for_cwd", lambda mode, cwd: "proj" if Path(str(cwd)).resolve() == project.resolve() else None)
    monkeypatch.setattr("jobs.job_notes_paths", lambda mode, slug: ["wiki/Proj"])
    n = _one(client, auth_headers, project)["notes"]
    got = [(c["subject"], c["via"], c["mode"]) for c in n["commits"]]
    assert got == [
        ("Log: the build session's own entry", "session", "faber"),   # from inside the project: the record
        ("spec written for the project", "path", None),               # touches the notes: the record, by hand
    ], got
    assert all(c["subject"] != "Log: written by Noctua elsewhere" for c in n["commits"]), "Noctua's vault work is not this project's"


def test_the_push_refuses_a_bodiless_commit_made_after_the_rule(tmp_path, monkeypatch, client, auth_headers):
    """A commit is the record. One with no body, dated after the rule, stops
    the push; one from before the rule does not -- the rule cannot reach
    back."""
    import os
    root = _with_origin(tmp_path)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    # Explicitly before the rule, not "now": this test read the clock and
    # passed for two days, then failed at midnight on the 17th.
    _commit(root, "old style, no body", body=None, at="2026-09-16T10:00:00+00:00")
    r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
    assert r.status_code == 200, r.json()
    env = {**os.environ, "GIT_AUTHOR_DATE": "2026-09-20T10:00:00+00:00", "GIT_COMMITTER_DATE": "2026-09-20T10:00:00+00:00"}
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "new, and bare"], cwd=root, check=True, env=env)
    r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
    assert r.status_code == 409 and "no body" in r.json()["detail"] and "nothing was pushed" in r.json()["detail"]
    assert subprocess.run(["git", "rev-list", "--count", "origin/main..HEAD"], cwd=root, capture_output=True, text=True).stdout.strip() == "1"
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "--amend",
                    "-m", "new, with its record\n\nLeaves the widget half wired.\nNext: wire the other half."], cwd=root, check=True, env=env)
    assert client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers).status_code == 200
    body = _one(client, auth_headers, root)["commits"][0]
    assert body["body"].startswith("Leaves the widget") and body["body"].endswith("Next: wire the other half.")


def test_a_transcripts_mode_comes_from_its_directory_when_noctis_did_not_launch_it(tmp_path, monkeypatch):
    from orchestrator import jsonl
    project = tmp_path / "noctis-os"; (project / "backend").mkdir(parents=True)
    monkeypatch.setattr("jobs.find_job_for_cwd", lambda mode, cwd: "noctis-os" if Path(str(cwd)).resolve() == project.resolve() else None)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
    assert jsonl.mode_for_cwd(str(project / "backend")) == "faber", "a subdirectory of the project is the project"
    assert jsonl.mode_for_cwd(str(tmp_path / "elsewhere")) == "general"
    assert jsonl.mode_for_cwd(None) == "general"


def test_the_record_lists_its_commits_and_says_how_far_it_trails_the_code(tmp_path, monkeypatch, client, auth_headers):
    """The record's commits are the two sets united -- commits touching the
    notes paths, and commits made from inside the project -- and `trails`
    is the gap between the newest project commit and the newest record
    commit. The by-file view this replaced (2026-09-15 to 09-16) put twelve
    unpushed commits beside three rows."""
    import time
    from orchestrator.store import ConversationStore
    project = _repo(tmp_path, "proj")
    vault = _repo(tmp_path, "vault")
    (vault / "wiki" / "Proj").mkdir(parents=True)
    (vault / "wiki" / "Proj" / "SPEC.md").write_text("spec"); (vault / "wiki" / "Proj" / "Overview.md").write_text("overview")
    (vault / "log.md").write_text("log")
    subprocess.run(["git", "add", "-A"], cwd=vault, check=True); _commit(vault, "spec and overview written")
    (vault / "log.md").write_text("log 2"); subprocess.run(["git", "add", "-A"], cwd=vault, check=True)
    _commit(vault, "Log: the build session's own entry")
    (vault / "wiki" / "Proj" / "BRIEF.md").write_text("not committed yet")
    # The project's newest commit comes after every record commit.
    time.sleep(1.1)
    _commit(project, "code moved on after the record")
    store = ConversationStore(tmp_path / "h.db")
    _session_with_commit(store, "general", str(project / "backend"), "Log: the build session's own entry")
    store.close()
    original_init = ConversationStore.__init__
    monkeypatch.setattr(ConversationStore, "__init__", lambda self, path=None: original_init(self, tmp_path / "h.db"))
    monkeypatch.setattr(ConversationStore, "sessions_in", lambda self, r: [])
    monkeypatch.setattr(ConversationStore, "sessions_all", lambda self: [])
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    monkeypatch.setattr(panels.vault_io, "get_vault_path", lambda: vault)
    monkeypatch.setattr("jobs.find_job_for_cwd", lambda mode, cwd: "proj" if Path(str(cwd)).resolve() == project.resolve() else None)
    monkeypatch.setattr("jobs.job_notes_paths", lambda mode, slug: ["wiki/Proj"])
    r = _one(client, auth_headers, project)
    n = r["notes"]
    assert "files" not in n
    by_subject = {c["subject"]: c for c in n["commits"]}
    assert by_subject["Log: the build session's own entry"]["via"] == "session" and by_subject["Log: the build session's own entry"]["mode"] == "faber", \
        "a commit the build session made is the record even outside the notes paths"
    assert by_subject["spec and overview written"]["via"] == "path"
    assert n["dirty"] == ["wiki/Proj/BRIEF.md"], "uncommitted under the notes paths, and only there"
    t = n["trails"]
    assert t["behind"] >= 1 and t["project_at"] == r["commits"][0]["at"] and t["record_at"] == n["commits"][0]["at"], t
    # The vault as its own repository carries no record of its own.
    assert _one(client, auth_headers, vault)["notes"] is None


def test_the_records_figures_are_the_records_not_the_vaults(tmp_path, monkeypatch, client, auth_headers):
    """The vault may be five commits ahead while only two of them touch the
    project's record. The record block says two; the vault's five ride
    along as `vault_ahead`, because a push is the repository's."""
    project = _repo(tmp_path, "proj")
    vault = _repo(tmp_path, "vault")
    (vault / "wiki" / "Proj").mkdir(parents=True); (vault / "other.md").write_text("x")
    (vault / "wiki" / "Proj" / "SPEC.md").write_text("spec")
    subprocess.run(["git", "add", "-A"], cwd=vault, check=True); _commit(vault, "spec and other")
    # A bare "origin" the vault is ahead of, so ahead/behind are real numbers.
    origin = tmp_path / "origin.git"; subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=vault, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "HEAD"], cwd=vault, check=True, capture_output=True)
    for i in range(3):
        (vault / "other.md").write_text(f"x{i}"); subprocess.run(["git", "add", "-A"], cwd=vault, check=True); _commit(vault, f"other {i}")
    for i in range(2):
        (vault / "wiki" / "Proj" / "SPEC.md").write_text(f"spec {i}"); subprocess.run(["git", "add", "-A"], cwd=vault, check=True); _commit(vault, f"spec {i}")
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    monkeypatch.setattr(panels, "_gh", lambda *a, **k: None)
    monkeypatch.setattr(panels.vault_io, "get_vault_path", lambda: vault)
    monkeypatch.setattr("jobs.find_job_for_cwd", lambda mode, cwd: "proj" if Path(str(cwd)).resolve() == project.resolve() else None)
    monkeypatch.setattr("jobs.job_notes_paths", lambda mode, slug: ["wiki/Proj"])
    n = _one(client, auth_headers, project)["notes"]
    assert n["vault_ahead"] == 5, "the whole vault is five ahead"
    assert n["ahead"] == 2, "the record is two ahead -- the two commits that touch it"
    assert sum(1 for c in n["commits"] if not c["pushed"]) == 2


def test_the_same_author_in_the_same_second_is_not_a_copy_on_its_own(tmp_path, monkeypatch, client, auth_headers):
    """The worst case for telling a rewrite from new work: both commits empty
    (so their changes compare equal), same author, same second. Only the
    subject tells them apart, and it must, because calling GitHub's commit a
    copy would tell the person a force push loses nothing."""
    root = _with_origin(tmp_path)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    same = "2026-09-18T13:41:00+00:00"
    _commit(root, "local, empty", at=same)
    _commit_on_origin(tmp_path / "origin.git", "on GitHub, empty", name="t", email="t@t", at=same)
    client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)  # refused; fetches
    view = _one(client, auth_headers, root)
    assert view["upstream_lost"] == 1 and view["upstream_only"][0]["copied"] is False


def test_every_wording_of_the_attribution_rule_is_refused(tmp_path, monkeypatch, client, auth_headers):
    """The rule names a "Generated with Claude Code" line; only the bracketed
    Markdown form was caught, and "Co-Authored-By :" slipped by its space."""
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    for i, line in enumerate(("Generated with Claude Code", "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
                 "Co-Authored-By : Claude <noreply@anthropic.com>", "claude-session: https://x")):
        (tmp_path / str(i)).mkdir()
        root = _with_origin(tmp_path / str(i))
        _commit(root, "work", body=FIXTURE_BODY + "\n\n" + line)
        r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
        assert r.status_code == 409 and "attribution line" in r.json()["detail"], line


def test_a_check_that_cannot_read_the_commits_refuses_the_push(tmp_path, monkeypatch, client, auth_headers):
    """`_git` answers None on an error or a timeout, and `or ""` read that as
    nothing to refuse: the push went out unchecked."""
    root = _with_origin(tmp_path)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    _commit(root, "tainted", body=FIXTURE_BODY + "\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    real = panels._git
    monkeypatch.setattr(panels, "_git", lambda root, *a, **k: None if a[:1] == ("log",) else real(root, *a, **k))
    r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
    assert r.status_code == 503 and "not checked" in r.json()["detail"]
    assert subprocess.run(["git", "rev-list", "--count", "origin/main..HEAD"], cwd=root,
                          capture_output=True, text=True).stdout.strip() == "1", "nothing was pushed"


def test_a_new_branch_is_checked_only_for_what_no_remote_has(tmp_path, monkeypatch, client, auth_headers):
    """A branch with no upstream was checked against all of HEAD's history,
    so in noctis-os two bodiless commits made on GitHub's editor, already
    on origin, refused every new branch."""
    root = _with_origin(tmp_path)
    monkeypatch.setattr(panels, "_safe_home_dir", lambda raw: Path(raw))
    _commit(root, "made on github, no body", body=None, at="2026-09-18T10:00:00Z")
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=root, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=root, check=True)
    _commit(root, "the new work")
    listing = _one(client, auth_headers, root)
    assert [c["pushed"] for c in listing["commits"][:2]] == [False, True], "only the new commit is off GitHub"
    r = client.post("/v2/repos/push", json={"cwd": str(root)}, headers=auth_headers)
    assert r.status_code == 200 and r.json()["branch"] == "feature", r.text


def test_a_sentence_about_the_rule_is_not_an_attribution_line():
    """50a8b84's body quotes the phrase while describing the check, and the
    push refused it: the pattern matched any line containing it."""
    refused = ["Generated with Claude Code", "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
               "  Generated with [Claude Code]", "Co-Authored-By: Claude <noreply@anthropic.com>",
               "Co-Authored-By : x", "Claude-Session: https://x"]
    allowed = ['The attribution pattern caught only "Generated with [Claude Code]" in its',
               'missed the plain "Generated with Claude Code" line, and drew a repo',
               "It refuses any `Co-Authored-By`, `Claude-Session` or the rest."]
    for line in refused:
        assert panels._ATTRIBUTION.search(line), line
    for line in allowed:
        assert not panels._ATTRIBUTION.search(line), line


def test_the_spaced_link_form_is_refused_too():
    assert panels._ATTRIBUTION.search("Generated with Claude Code (https://claude.com/claude-code)")
    assert panels._outgoing(None) == ["HEAD", "--not", "--remotes=origin"]
