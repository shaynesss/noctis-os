"""The digest: what happened since you were last here, counted."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import digest

T0 = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------- sittings

def test_a_gap_of_thirty_minutes_ends_a_sitting(tmp_path):
    """Heartbeats close together are one sitting; the first one after a
    long silence starts the next, and "since" becomes the last beat of the
    previous one -- not the moment you came back, which would make every
    return read "nothing since a second ago"."""
    p = tmp_path / "s.json"
    assert digest.here(p, T0)["since"] is None                       # first look
    assert digest.here(p, T0 + timedelta(minutes=10))["since"] is None
    back = digest.here(p, T0 + timedelta(hours=9))
    assert back["since"] == (T0 + timedelta(minutes=10)).isoformat(timespec="seconds")
    # Still here: the figure holds while the sitting lasts.
    assert digest.here(p, T0 + timedelta(hours=9, minutes=5))["since"] == back["since"]
    assert digest.since(p) == back["since"]


def test_a_missing_or_broken_sittings_file_is_a_first_look(tmp_path):
    assert digest.since(tmp_path / "none.json") is None
    (tmp_path / "bad.json").write_text("{not json")
    assert digest.since(tmp_path / "bad.json") is None
    assert digest.here(tmp_path / "bad.json", T0)["since"] is None


# ---------------------------------------------------------------- facts

def _fake_git(answers: dict[str, str | None]):
    def git(root: Path, *args: str) -> str | None:
        return answers.get(" ".join(args[:2]) if args[0] in {"rev-parse", "rev-list"} else args[0])
    return git


def test_repos_report_movement_not_history(tmp_path):
    """Commits since, commits not on the upstream, files uncommitted -- the
    three numbers that say what moved. A directory that is not a repository
    is skipped, not reported as a quiet one."""
    git = _fake_git({
        "rev-parse --show-toplevel": "/x/noctis-os", "rev-parse --abbrev-ref": "main",
        "rev-list --count": "12", "log": "a1\nb2\nc3", "status": " M a.py\n?? b.py",
    })
    out = digest._repos(git, [Path("/x/noctis-os")], T0)
    assert out == [{"name": "noctis-os", "branch": "main", "commits": 3, "ahead": 12, "dirty": 2}]
    assert digest._repos(lambda *a: None, [Path("/not/a/repo")], T0) == []


def test_sessions_since_are_grouped_by_mode_and_need_you_to_have_spoken(tmp_path):
    """A session that only ran its opener is not one you were in."""
    from orchestrator.store import ConversationStore
    store = ConversationStore(tmp_path / "h.db")
    from interactive import OPENING_PROMPT
    old = store.open_session("faber", cwd="/x")
    a = store.open_session("faber", cwd="/x")
    b = store.open_session("noctua", cwd="/x")
    silent = store.open_session("faber", cwd="/x")
    opened = store.open_session("vesper", cwd="/x")
    for sid, started in ((old, "2026-09-01T00:00:00+00:00"), (a, "2026-09-15T08:00:00+00:00"),
                         (b, "2026-09-15T08:00:00+00:00"), (silent, "2026-09-15T08:00:00+00:00"),
                         (opened, "2026-09-15T08:00:00+00:00")):
        store.db.execute("UPDATE sessions SET started_at=?, title=? WHERE id=?", (started, f"session {sid}", sid))
    for sid in (old, a, b):                                    # `silent` never spoke
        store.db.execute("INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
                         (sid, "user", "hi", "2026-09-15T08:00:00+00:00"))
    # `opened` ran only Noctis's own opening prompt, which is stored as a
    # user message and is not you speaking.
    store.db.execute("INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
                     (opened, "user", OPENING_PROMPT, "2026-09-15T08:00:00+00:00"))
    store.db.commit()

    out = digest._sessions(store, T0 - timedelta(hours=2))
    assert [(e["mode"], e["count"], e["titles"]) for e in out] == \
        [("faber", 1, [f"session {a}"]), ("noctua", 1, [f"session {b}"])]
    store.close()


def test_gather_reads_jobs_and_defaults_the_window(monkeypatch, tmp_path):
    """Open jobs by character, the owed ones, the dev project directories as
    repositories beside the vault -- and with no sitting recorded, the last
    day rather than nothing."""
    from orchestrator.store import ConversationStore
    project = tmp_path / "proj"
    project.mkdir()
    jobs = {"modes": ["dev", "learn"], "modes/dev/jobs": ["live", "held"], "modes/learn/jobs": ["old"]}
    meta = {
        "modes/dev/jobs/live/context.md":
            {"name": "Live", "stage": "Build", "status": "going", "project_path": str(project),
             "last_touched": T0.isoformat()},
        "modes/dev/jobs/held/context.md":
            {"name": "Held", "stage": "Plan", "status": "On hold.", "last_touched": "2026-08-01"},
        "modes/learn/jobs/old/context.md":
            {"name": "Old topic", "stage": "Read", "status": "concluded", "last_touched": "2026-08-01"},
    }
    monkeypatch.setattr(digest.vault_io, "list_subdirs", lambda p: jobs.get(p, []))
    monkeypatch.setattr(digest.vault_io, "file_exists", lambda p: p in meta)
    monkeypatch.setattr(digest.vault_io, "read_frontmatter", lambda p: (meta[p], ""))
    monkeypatch.setattr(digest.vault_io, "get_vault_path", lambda: tmp_path / "vault")
    monkeypatch.setattr(digest, "SITTINGS", tmp_path / "none.json")
    seen: list[Path] = []

    def git(root: Path, *args: str) -> str | None:
        seen.append(root)
        return None                                  # nothing here is a repository

    store = ConversationStore(tmp_path / "h.db")
    facts = digest.gather(git, store=store)
    store.close()

    assert facts["since"] is None
    assert facts["open"] == 3 and facts["on_hold"] == 1
    assert [m["job"] for m in facts["modes"]] == ["Live", None, "Old topic"]
    assert facts["modes"][0]["days"] == 0
    assert [j["name"] for j in facts["owed"]] == ["Old topic"]        # held is not owed
    assert seen[:2] == [tmp_path / "vault", project.resolve()]         # vault first, then the project
    assert facts["repos"] == [] and facts["sessions"] == []


# ---------------------------------------------------------------- routes

def test_the_digest_route_adds_what_is_waiting(monkeypatch, client, auth_headers):
    from routers import panels
    monkeypatch.setattr(panels.digest, "gather", lambda git: {"since": "2026-09-14T23:00:00+00:00"})
    monkeypatch.setattr(panels, "_proposals", lambda: [
        {"kind": "proposal", "at": "2026-09-15T03:00:00+00:00"},
        {"kind": "proposal", "at": "2026-09-01T03:00:00+00:00"},
        {"kind": "unreadable", "at": ""},
    ])
    monkeypatch.setattr(panels, "_flagged_jobs", lambda: [{"kind": "flagged-job"}])
    body = client.get("/v2/digest", headers=auth_headers).json()
    assert body["inbox"] == {"waiting": 2, "flagged": 1, "arrived": 1}


def test_presence_is_a_post_and_needs_auth(monkeypatch, client, auth_headers, tmp_path):
    monkeypatch.setattr(digest, "SITTINGS", tmp_path / "s.json")
    assert client.post("/v2/digest/here").status_code == 401
    assert client.get("/v2/digest/here", headers=auth_headers).status_code == 405
    assert client.post("/v2/digest/here", headers=auth_headers).json() == {"since": None}
    assert (tmp_path / "s.json").exists()
