"""Session route tests: the argv a terminal spawns with, the status-line
reports it sends back, history, stats, recap, panels."""
import pathlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from routers.sessions_v2 import MAX_CONCURRENT_CEILING


# ------------------------------------------------------------------ routes

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NOCTIS_API_TOKEN", "test-token")
    from main import app
    return TestClient(app)


AUTH = {"Authorization": "Bearer test-token"}


def _usage(store, sid, *, input=0, output=0, cached=0, cache_write=0):
    """One usage row, the shape the transcript indexer writes."""
    store.db.execute(
        "INSERT INTO usage (session_id, mode, model, input_tokens, output_tokens,"
        " cached_tokens, cache_write_tokens, duration_ms, created_at)"
        " VALUES (?,?,?,?,?,?,?,1,?)",
        (sid, "faber", "m", input, output, cached, cache_write,
         "2026-09-13T10:00:00+00:00"))
    store.db.commit()


def test_the_session_list_reports_the_terminals_that_are_reporting(client):
    """What is live is what the terminals say, not what a manager remembers.
    A terminal's status line re-runs every five seconds while it is up, so a
    report older than half a minute is a session that has gone."""
    import routers.sessions_v2 as sv2
    sv2._statusline.clear()
    client.post("/v2/sessions/statusline?slot=term-a", headers=AUTH,
                json={"session_id": "s-a", "model": {"id": "claude-opus-5"}})
    sv2._statusline["term-old"] = {"session_id": "s-old", "reported_at": 0}
    sv2._statusline["s-not-a-slot"] = {"session_id": "s-not-a-slot", "reported_at": 9e12}

    body = client.get("/v2/sessions", headers=AUTH).json()
    assert body["running"] == 1
    assert body["live"][0]["slot"] == "term-a"
    assert body["live"][0]["model"] == "claude-opus-5"
    sv2._statusline.clear()


def test_cwd_outside_home_is_refused(client):
    """cwd reaches the process as its working directory -- the same class of
    input as the job_slug traversal caught in the 2026-07-21 review."""
    r = client.get("/v2/sessions/interactive-args", headers=AUTH,
                   params={"mode": "faber", "cwd": "/etc"})
    assert r.status_code == 403


def test_nonexistent_cwd_is_refused(client):
    r = client.get("/v2/sessions/interactive-args", headers=AUTH,
                   params={"mode": "faber", "cwd": "~/definitely-not-here-xyz"})
    assert r.status_code == 400


def test_symlink_out_of_home_cannot_smuggle_a_path(client, tmp_path, monkeypatch):
    """Resolution happens before the containment check, so a link inside
    home that points outside it is still refused."""
    link = Path.home() / ".noctis-test-escape-link"
    try:
        link.symlink_to("/etc")
        r = client.get("/v2/sessions/interactive-args", headers=AUTH,
                       params={"mode": "faber", "cwd": str(link)})
        assert r.status_code == 403
    finally:
        link.unlink(missing_ok=True)


def test_routes_require_auth(client):
    assert client.get("/v2/sessions").status_code == 401
    assert client.get("/v2/sessions/limits").status_code == 401


def test_limits_distinguishes_unknown_from_zero(client):
    """Zero utilisation and 'not yet reported' must not render alike: the
    difference decides whether there is room to start a session."""
    body = client.get("/v2/sessions/limits", headers=AUTH).json()
    assert body["known"] is False
    assert body["five_hour"] is None


def test_session_list_reports_the_concurrency_budget(client):
    """The route must report the cap the manager actually has.

    Asserted against the live manager rather than against the default: the
    manager is a module singleton built at import, so it captures whatever
    NOCTIS_MAX_CONCURRENT was set to then -- and pinning the number here made
    the suite fail on a machine whose .env raised it, which tests the
    developer's environment rather than the code. What matters is that the
    UI is told the truth, whatever the truth is.
    """
    import routers.sessions_v2 as sv2
    sv2._statusline.clear()

    body = client.get("/v2/sessions", headers=AUTH).json()
    assert body["max_concurrent"] == sv2.max_concurrent()
    assert 1 <= body["max_concurrent"] <= MAX_CONCURRENT_CEILING
    assert body["running"] == 0


# ------------------------------------------------------------------- stats

def test_an_older_database_gains_the_new_columns(tmp_path):
    """CREATE TABLE IF NOT EXISTS is a no-op on a database that already has
    the table, so without the add-column pass the next INSERT fails on any
    machine that ran the older build."""
    import sqlite3
    from orchestrator.store import SCHEMA, ConversationStore

    old = SCHEMA.replace("    aux_input_tokens  INTEGER NOT NULL DEFAULT 0,\n", "")
    old = old.replace("    aux_output_tokens INTEGER NOT NULL DEFAULT 0,\n", "")
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript(old)
    con.commit()
    con.close()

    store = ConversationStore(path)
    cols = {r[1] for r in store.db.execute("PRAGMA table_info(usage)")}
    assert {"aux_input_tokens", "aux_output_tokens"} <= cols
    store.close()


def test_stats_route_shape(client):
    body = client.get("/v2/sessions/stats", headers=AUTH).json()
    # `transcripts` and `diff` are the migration's gate: the same number read
    # from the CLI's own files beside the recorder's, and where they disagree.
    assert set(body) == {"lifetime", "activity", "transcripts", "diff"}
    assert set(body["transcripts"]) >= {"tokens", "turns", "sessions", "input", "output", "cached", "cache_write", "since"}
    assert set(body["diff"]) == {"compared", "agree", "rows"}
    assert set(body["lifetime"]) >= {"input", "output", "cached", "turns", "list_cost", "priced_turns"}


def test_stats_requires_auth(client):
    assert client.get("/v2/sessions/stats").status_code == 401


# ------------------------------------------------------------------ panels


def test_finished_jobs_are_not_inbox_items(monkeypatch):
    """Most of the vault's flagged jobs are settings work completed in July.
    Including them produced 22 entries, 20 long resolved -- which is how an
    inbox stops being read."""
    from routers import panels

    jobs = {
        "modes": ["dev"],
        "modes/dev/jobs": ["done-one", "open-one"],
    }
    meta = {
        "modes/dev/jobs/done-one/context.md": {"flagged": True, "stage": "Done", "name": "Done one"},
        "modes/dev/jobs/open-one/context.md": {"flagged": True, "stage": "Build", "name": "Open one"},
    }
    monkeypatch.setattr(panels.vault_io, "list_subdirs", lambda p: jobs.get(p, []))
    monkeypatch.setattr(panels.vault_io, "file_exists", lambda p: True)
    monkeypatch.setattr(panels, "_safe_frontmatter", lambda p: meta.get(p))

    titles = [j["title"] for j in panels._flagged_jobs()]
    assert titles == ["Open one"]


def test_one_unparseable_job_does_not_take_down_the_panel(monkeypatch):
    """A YAML scalar containing ': ' parses as a mapping and raises -- a real
    file in modes/dev/jobs was failing exactly that way."""
    from routers import panels

    monkeypatch.setattr(panels.vault_io, "list_subdirs",
                        lambda p: ["dev"] if p == "modes" else ["broken"])
    monkeypatch.setattr(panels.vault_io, "file_exists", lambda p: True)
    monkeypatch.setattr(panels, "_safe_frontmatter", lambda p: None)

    items = panels._flagged_jobs()
    assert len(items) == 1
    assert items[0]["kind"] == "unreadable"


def test_the_inbox_readme_is_not_a_proposal(monkeypatch):
    """The staging folder holds its own README; listing it put a docs file in
    a queue of things awaiting a decision."""
    from routers import panels

    monkeypatch.setattr(panels.vault_io, "file_exists", lambda p: True)
    monkeypatch.setattr(panels.vault_io, "list_dir", lambda p: ["README", "real-proposal"])
    monkeypatch.setattr(panels, "_safe_frontmatter", lambda p: {"description": "d"})
    monkeypatch.setattr(panels.vault_io, "read_frontmatter", lambda p: ({}, "body"))

    assert [p["id"] for p in panels._proposals()] == ["real-proposal"]


# ----------------------------------------------------------------- history

def _rows(msgs):
    """Message rows shaped like sqlite3.Row for the block renderer."""
    return [{"role": r, "content": c, "meta": m, "created_at": "2026-09-09T09:15:00+00:00"}
            for r, c, m in msgs]


def test_assistant_deltas_rejoin_into_one_block():
    """Deltas are stored one row each; a restored reply must not arrive
    shattered into a paragraph per fragment."""
    from transcript import blocks_from_messages
    blocks = blocks_from_messages(_rows([
        ("assistant", "Hel", None), ("assistant", "lo ", None), ("assistant", "there", None),
    ]))
    assert blocks == [{"kind": "text", "text": "Hello there"}]


def test_a_user_turn_separates_two_replies():
    """Without the user message between them, two turns' answers merge --
    which is exactly what old rows did before the prompt was recorded."""
    from transcript import blocks_from_messages
    blocks = blocks_from_messages(_rows([
        ("user", "one?", None), ("assistant", "ONE", None),
        ("user", "two?", None), ("assistant", "TWO", None),
    ]))
    assert [b["kind"] for b in blocks] == ["user", "text", "user", "text"]
    assert blocks[3]["text"] == "TWO"


def test_a_tool_result_pairs_with_its_call_by_id():
    """Pairing on adjacency breaks under the interleaving the live reducer
    already handles; the stored form must agree with it."""
    from transcript import blocks_from_messages
    blocks = blocks_from_messages(_rows([
        ("tool", "Read /a.py", '{"id": "a", "tool": "Read"}'),
        ("tool", "Bash ls", '{"id": "b", "tool": "Bash"}'),
        ("tool_result", "B OUT", '{"id": "b"}'),
        ("tool_result", "A OUT", '{"id": "a"}'),
    ]))
    assert [(b["id"], b["body"]) for b in blocks] == [("a", "A OUT"), ("b", "B OUT")]


def test_a_failed_tool_result_opens_itself():
    from transcript import blocks_from_messages
    blocks = blocks_from_messages(_rows([
        ("tool", "Bash boom", '{"id": "x", "tool": "Bash"}'),
        ("tool_result", "nope", '{"id": "x", "is_error": true}'),
    ]))
    assert blocks[0]["meta"] == "error" and blocks[0]["open"] is True


def test_transcript_404s_for_an_unknown_session(client):
    assert client.get("/v2/sessions/history/999999", headers=AUTH).status_code == 404


# ------------------------------------------------------------------ search

def test_search_returns_one_hit_per_conversation(monkeypatch, client):
    """Several matching messages in one session are one result to a person
    looking for that conversation -- and a long session would otherwise
    flood the list and bury everything else."""
    from routers import search as search_router

    rows = [
        {"session_id": 1, "mode": "faber", "role": "user", "content": "alpha one",
         "created_at": "2026-09-09"},
        {"session_id": 1, "mode": "faber", "role": "assistant", "content": "alpha two",
         "created_at": "2026-09-09"},
        {"session_id": 2, "mode": "vesper", "role": "user", "content": "alpha three",
         "created_at": "2026-09-09"},
    ]
    monkeypatch.setattr(search_router._store, "search", lambda q, limit: rows)
    monkeypatch.setattr(search_router, "_vault_index", lambda: type("I", (), {"search": lambda *a, **k: []})())

    body = client.get("/v2/search?q=alpha", headers=AUTH).json()
    assert [c["session_id"] for c in body["conversations"]] == [1, 2]


def test_excerpt_centres_on_the_match_not_the_opening():
    """A prefix of a long message is very often the least useful part of it;
    the match is why the row is there."""
    from routers.search import _excerpt

    text = "x" * 400 + " needle " + "y" * 400
    out = _excerpt(text, "needle")
    assert "needle" in out
    assert out.startswith("…")


def test_excerpt_falls_back_when_no_term_matches():
    from routers.search import _excerpt
    assert _excerpt("some content here", "zz").startswith("some content")


def test_search_requires_a_real_query(client):
    assert client.get("/v2/search?q=a", headers=AUTH).status_code == 422


def test_search_requires_auth(client):
    assert client.get("/v2/search?q=alpha").status_code == 401


# ------------------------------------------------------------ vault reader

def test_reader_refuses_the_project_root_prefix(client):
    """vault_io's ordinary resolver honours a project-root allowlist that
    also resolves noctis-os/.env -- the file holding this API's own token.
    Verified by reading it, not assumed. Anything taking a client-supplied
    path must not go through that resolver."""
    r = client.get("/v2/vault/doc?path=noctis-os/.env", headers=AUTH)
    assert r.status_code in (400, 403, 404)
    assert "NOCTIS_API_TOKEN" not in r.text


def test_reader_refuses_a_traversal(client):
    r = client.get("/v2/vault/doc?path=../../etc/passwd", headers=AUTH)
    assert r.status_code in (400, 403, 404)


def test_reader_refuses_non_markdown(client):
    """The vault holds binaries; a reader that serves any file is an
    exfiltration endpoint wearing a document viewer's clothes."""
    assert client.get("/v2/vault/doc?path=some/image.png", headers=AUTH).status_code == 400


def test_reader_404s_for_a_missing_document(client):
    r = client.get("/v2/vault/doc?path=definitely/not/here.md", headers=AUTH)
    assert r.status_code == 404


def test_reader_returns_a_real_document(client):
    r = client.get("/v2/vault/doc?path=README.md", headers=AUTH)
    if r.status_code == 200:
        assert isinstance(r.json()["markdown"], str)


def test_reader_requires_auth(client):
    assert client.get("/v2/vault/doc?path=README.md").status_code == 401


def test_vault_only_resolver_never_reaches_the_repo(tmp_path, monkeypatch):
    """It does not raise on this input, and should not: the path is treated
    as vault-relative (second-brain/noctis-os/.env), which is inside the
    vault and simply does not exist. The property that matters is that it
    cannot land on the repo's real .env, which the ordinary resolver does."""
    import vault_io

    resolved = vault_io.resolve_vault_only("noctis-os/.env")
    vault = vault_io.get_vault_path().resolve()
    assert vault in resolved.parents
    assert resolved != (pathlib.Path(vault_io.__file__).resolve().parent.parent / ".env")


def test_the_ordinary_resolver_still_reaches_the_repo(tmp_path):
    """Documents why the two exist. This capability is deliberate -- the
    apply pipeline writes noctis-os/SPEC.md -- and is exactly why a
    client-supplied path must not use it."""
    import vault_io

    repo = pathlib.Path(vault_io.__file__).resolve().parent.parent
    assert vault_io._resolve_within_vault("noctis-os/SPEC.md") == repo / "SPEC.md"


# ------------------------------------------------------------ deleting

def test_deleting_a_conversation_removes_its_usage_too(tmp_path):
    """Leaving usage rows behind would keep a deleted conversation's tokens
    in the lifetime totals, so Stats would disagree with History about what
    happened."""
    from orchestrator.store import ConversationStore

    store = ConversationStore(tmp_path / "h.db")
    sid = store.open_session("faber", cwd="/tmp")
    store.add_message(sid, "user", "hello")
    _usage(store, sid, input=1, output=9)
    assert store.lifetime_tokens()["output"] == 9

    store.db.execute("DELETE FROM messages WHERE session_id=?", (sid,))
    store.db.execute("DELETE FROM usage WHERE session_id=?", (sid,))
    store.db.execute("DELETE FROM sessions WHERE id=?", (sid,))
    store.db.commit()

    assert store.lifetime_tokens()["output"] == 0
    assert store.search("hello") == []      # the fts index kept in step
    store.close()


def test_deleting_an_unknown_conversation_404s(client):
    assert client.delete("/v2/sessions/history/999999", headers=AUTH).status_code == 404


def test_delete_requires_auth(client):
    assert client.delete("/v2/sessions/history/1").status_code == 401


# ------------------------------------------------------------- recap

def test_no_route_is_defined_twice():
    """The recap route was defined twice, an exact copy body for body.
    FastAPI serves the first, so it was dead code rather than a break -- and
    dead code that would have rotted out of sync with the live one. Found by
    a session reading this repo, not by a test, which is why this exists.

    Checked against the source rather than the app: a duplicate decorator is
    the actual defect, and the router objects hide it behind wrappers.
    """
    import re

    routers = Path(__file__).resolve().parents[1] / "routers"
    for file in routers.glob("*.py"):
        decorators = re.findall(r'@router\.(get|post|patch|delete)\("([^"]*)"', file.read_text())
        seen: set[tuple[str, str]] = set()
        for method, path in decorators:
            assert (method, path) not in seen, f"{file.name} defines {method.upper()} {path!r} twice"
            seen.add((method, path))


# ------------------------------------------------------------- billing

def test_billing_says_plainly_that_nothing_is_charged(client):
    """The figure is API list price. Under a subscription the marginal cost
    of a turn is zero, and a UI that renders it as a bill would be lying with
    a real number."""
    body = client.get("/v2/billing", headers=AUTH).json()
    assert body["charged"] is False
    assert body["basis"] == "api-list-price"


def test_limits_report_overage_even_before_anything_is_known(client):
    """Overage is the one signal here that can mean money, so its absence
    must be explicit rather than a missing key the UI reads as undefined."""
    body = client.get("/v2/sessions/limits", headers=AUTH).json()
    assert body["using_overage"] is False


def test_billing_requires_auth(client):
    assert client.get("/v2/billing").status_code == 401


def test_recent_dirs_come_from_real_sessions(tmp_path):
    """The launcher's list was hardcoded, so it named the same directories
    whether or not you had opened them and never learned a new project."""
    from orchestrator.store import ConversationStore

    store = ConversationStore(tmp_path / "h.db")
    for cwd in ("/a", "/b", "/a"):
        store.close_session(store.open_session("faber", cwd=cwd))
    dirs = store.recent_cwds()
    assert set(dirs) == {"/a", "/b"}      # deduplicated
    assert dirs[0] == "/a"                # most recently used first
    store.close()


def test_recent_dirs_ignores_sessions_with_no_directory(tmp_path):
    from orchestrator.store import ConversationStore

    store = ConversationStore(tmp_path / "h.db")
    store.close_session(store.open_session("faber", cwd=None))
    assert store.recent_cwds() == []
    store.close()


def test_billing_prices_the_same_turns_the_token_counts_span(tmp_path, monkeypatch, client):
    """The cost and the token counts are read from the same transcripts, so
    the figure covers every turn -- less only those whose model the price
    table does not know, and it says how many. Summed from the store it
    covered the 120 turns the `-p` engine had priced, under counts spanning
    eight thousand, and read 20x low against its own tokens."""
    import json
    from orchestrator import jsonl

    monkeypatch.setattr(jsonl, "PROJECTS", tmp_path)
    monkeypatch.setattr(jsonl, "_lifetime_cache", None)
    rows = [
        {"type": "assistant", "timestamp": "2026-09-14T00:00:00Z",
         "message": {"role": "assistant", "model": "claude-opus-5", "content": [],
                     "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}},
        {"type": "assistant", "timestamp": "2026-09-14T00:01:00Z",
         "message": {"role": "assistant", "model": "claude-mystery-9", "content": [],
                     "usage": {"input_tokens": 5, "output_tokens": 5}}},
    ]
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "s.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    body = client.get("/v2/billing", headers=AUTH).json()
    assert body["turns"] == 2
    assert body["priced_turns"] == 1            # the unknown model is the gap
    assert body["list_cost"] == 5.0             # a million Opus 5 input tokens
    assert body["charged"] is False
    assert body["since"] == "2026-09-14"

    # Stats quotes the same two numbers from the same pass.
    life = client.get("/v2/sessions/stats", headers=AUTH).json()["lifetime"]
    assert (life["list_cost"], life["priced_turns"], life["turns"]) == (5.0, 1, 2)


# ------------------------------------------------------------- prompts

def test_prompts_lists_the_system_prompt_and_every_overlay(client):
    body = client.get("/v2/prompts", headers=AUTH).json()
    ids = {p["id"] for p in body["prompts"]}
    from engine import MODE_MODELS
    assert ids == {"system", *MODE_MODELS}


def test_a_prompt_id_cannot_address_anything_else(client):
    """Matched against the known set rather than joined into a path: an
    editor that can open any vault file is a vault editor with a narrow
    label."""
    for attempt in ("../../../etc/passwd", "log", "system/../../secrets"):
        r = client.put(f"/v2/prompts/{attempt}", headers=AUTH, json={"markdown": "x"})
        assert r.status_code in (404, 405), attempt


def test_saving_a_prompt_writes_the_vault_file_and_nothing_else(client, monkeypatch):
    """The save is the write: `system.md` is what `~/.claude/CLAUDE.md`
    links to and an overlay is composed into the argv at the next spawn.
    Until 2026-09-15 the route also "re-rendered" per-mode config dirs
    that the 09-12 cutover had removed, reporting "config dir missing"
    five times per save -- which two tests here pinned as the behaviour."""
    from routers import panels

    written = {}
    monkeypatch.setattr(panels.vault_io, "write_file", lambda p, c: written.update({p: c}))

    body = client.put("/v2/prompts/faber", headers=AUTH, json={"markdown": "new overlay"}).json()
    assert written == {"prompts/overlays/faber.md": "new overlay"}
    assert body == {"saved": "faber", "path": "prompts/overlays/faber.md", "bytes": len("new overlay")}

    body = client.put("/v2/prompts/system", headers=AUTH, json={"markdown": "base"}).json()
    assert written["prompts/system.md"] == "base"
    assert body["path"] == "prompts/system.md"
    assert client.put("/v2/prompts/../etc", headers=AUTH, json={"markdown": "x"}).status_code == 404


def test_reading_the_regression_suite_runs_nothing(client):
    """Reading is free; running is thirteen real sessions on production
    models. A page that fired the expensive one just by being opened would
    spend the window every time you glanced at Settings."""
    body = client.get("/v2/regression", headers=AUTH).json()
    assert body["sessions"] == len(body["cases"])
    assert all("mode" in c and "tests" in c for c in body["cases"])


def test_prompt_routes_require_auth(client):
    assert client.get("/v2/prompts").status_code == 401
    assert client.get("/v2/regression").status_code == 401


# ----------------------------------------------------------- artifacts

def test_artifacts_are_derived_from_what_the_session_did(tmp_path, monkeypatch, client):
    """Not from anything the model announces: a turn that writes a file has
    already said so in its tool call, and asking it to also declare outputs
    would be a second source that can disagree with the first."""
    from orchestrator.store import ConversationStore
    from routers import sessions_v2

    store = ConversationStore(tmp_path / "h.db")
    sid = store.open_session("faber", cwd="/tmp")
    for i, (tool, path) in enumerate([("Write", "/tmp/a.py"), ("Edit", "/tmp/a.py"), ("Read", "/tmp/b.py")], 1):
        store.add_message(sid, "tool", f"{tool} {path}",
                          {"tool": tool, "args": {"file_path": path}, "id": str(i)})
    monkeypatch.setattr(sessions_v2, "_store", store)

    found = client.get(f"/v2/sessions/history/{sid}/artifacts", headers=AUTH).json()["artifacts"]
    assert [a["path"] for a in found] == ["/tmp/a.py"]      # Read produces nothing
    assert found[0]["writes"] == 2                          # one entry, not two
    assert sorted(found[0]["tools"]) == ["Edit", "Write"]
    store.close()


def test_a_conversation_that_changed_nothing_has_no_artifacts(tmp_path, monkeypatch, client):
    from orchestrator.store import ConversationStore
    from routers import sessions_v2

    store = ConversationStore(tmp_path / "h.db")
    sid = store.open_session("general", cwd="/tmp")
    store.add_message(sid, "user", "just talking")
    monkeypatch.setattr(sessions_v2, "_store", store)
    assert client.get(f"/v2/sessions/history/{sid}/artifacts", headers=AUTH).json()["artifacts"] == []
    store.close()


def test_artifacts_404_for_an_unknown_conversation(client):
    assert client.get("/v2/sessions/history/999999/artifacts", headers=AUTH).status_code == 404


# ---------------------------------------------------- live monitoring

# ------------------------------------------------------------- promote

def _promotable(store, tmp_path):
    sid = store.open_session("faber", cwd="/tmp")
    store.add_message(sid, "user", "should the store or the vault hold this?")
    store.add_message(sid, "assistant", "The vault, once it is a decision rather than a chat.")
    store.add_message(sid, "thinking", "")
    return sid


def test_promoting_writes_a_note_into_the_vault(tmp_path, monkeypatch, client):
    """The deliberate half of "SQLite with promotion" -- and the route that
    makes the project's second premise reachable at all. Without it the
    knowledge never compounds anywhere, it only accumulates in a database."""
    from orchestrator.store import ConversationStore
    from routers import sessions_v2

    vault = tmp_path / "vault"
    vault.mkdir()
    store = ConversationStore(tmp_path / "h.db")
    sid = _promotable(store, tmp_path)
    monkeypatch.setattr(sessions_v2, "_store", store)
    monkeypatch.setattr(sessions_v2.vault_io, "get_vault_path", lambda: vault)
    monkeypatch.setattr(sessions_v2.vault_io, "resolve_vault_only", lambda p: vault / p)

    r = client.post(f"/v2/sessions/history/{sid}/promote", headers=AUTH, json={
        "rel_path": "wiki/Store vs vault.md", "title": "Store vs vault", "note": "Decided.",
    })
    assert r.status_code == 200
    written = (vault / "wiki" / "Store vs vault.md").read_text()
    assert "# Store vs vault" in written
    assert "Decided." in written
    assert "should the store or the vault hold this?" in written
    assert "**Claude**" in written
    # Thinking is empty by design and noise when it is not.
    assert "`thinking`" not in written
    store.close()


def test_promotion_never_overwrites(tmp_path, monkeypatch, client):
    """A promoted note may have been edited by hand since, and replacing it
    would lose work the store never saw."""
    from orchestrator.store import ConversationStore
    from routers import sessions_v2

    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    (vault / "wiki" / "taken.md").write_text("edited by hand after promotion")
    store = ConversationStore(tmp_path / "h.db")
    sid = _promotable(store, tmp_path)
    monkeypatch.setattr(sessions_v2, "_store", store)
    monkeypatch.setattr(sessions_v2.vault_io, "get_vault_path", lambda: vault)
    monkeypatch.setattr(sessions_v2.vault_io, "resolve_vault_only", lambda p: vault / p)

    r = client.post(f"/v2/sessions/history/{sid}/promote", headers=AUTH, json={
        "rel_path": "wiki/taken.md", "title": "Taken",
    })
    assert r.status_code == 409
    assert (vault / "wiki" / "taken.md").read_text() == "edited by hand after promotion"
    store.close()


def test_promotion_refuses_a_path_outside_the_vault(client):
    """It writes a file from a client-supplied path -- the same class of
    input as the reader, which is why it uses the same guard."""
    r = client.post("/v2/sessions/history/1/promote", headers=AUTH, json={
        "rel_path": "../../../tmp/escaped.md", "title": "Escape",
    })
    assert r.status_code in (403, 404)


def test_promotion_refuses_non_markdown(client):
    r = client.post("/v2/sessions/history/1/promote", headers=AUTH, json={
        "rel_path": "wiki/note.txt", "title": "Note",
    })
    assert r.status_code in (400, 404)


def test_promoting_an_unknown_conversation_404s(client):
    r = client.post("/v2/sessions/history/999999/promote", headers=AUTH, json={
        "rel_path": "wiki/x.md", "title": "X",
    })
    assert r.status_code == 404


def test_promote_requires_auth(client):
    r = client.post("/v2/sessions/history/1/promote",
                    json={"rel_path": "wiki/x.md", "title": "X"})
    assert r.status_code == 401


def test_vault_modes_start_at_the_vault_root_not_their_own_folder(client, monkeypatch):
    """Tidier and worse: the engine scopes reads to the working directory,
    so a Noctua session confined to modes/learn/ could not read wiki/ --
    which is most of what there is to learn from."""
    dirs = client.get("/v2/mode-dirs", headers=AUTH).json()["dirs"]
    import vault_io

    vault = str(vault_io.get_vault_path())
    for mode in ("noctua", "vesper", "maintenance"):
        assert dirs[mode] == vault, f"{mode} should start at the vault root"
        assert not dirs[mode].endswith(("learn", "research", "maintenance"))


def test_faber_starts_in_the_projects_directory_and_general_at_the_vault(client, monkeypatch, tmp_path):
    """Which project a build session is for is the session's to establish --
    a continuation names one, a new build has none yet -- so Faber starts
    one level up, in the projects directory, not in whichever repo was used
    last. General is the front door and starts at the vault, not in the
    last repo Faber happened to be in."""
    from routers import panels

    monkeypatch.setattr(panels.vault_io, "get_vault_path", lambda: Path("/vault"))
    monkeypatch.setattr("orchestrator.store.ConversationStore.recent_cwds",
                        lambda self, limit=8: ["/vault", "/repo/project"])
    monkeypatch.setenv("PROJECTS_DIR", "/repo")
    dirs = client.get("/v2/mode-dirs", headers=AUTH).json()["dirs"]
    assert dirs["faber"] == "/repo"
    assert dirs["general"] == "/vault"

    # Without a declared projects directory, ~/Developer/projects wins over
    # ~/Developer when it exists -- the 2026-08-29 layout.
    monkeypatch.delenv("PROJECTS_DIR")
    home = tmp_path / "home"; (home / "Developer" / "projects").mkdir(parents=True)
    monkeypatch.setattr(panels.Path, "home", classmethod(lambda cls: home))
    assert client.get("/v2/mode-dirs", headers=AUTH).json()["dirs"]["faber"] == str(home / "Developer" / "projects")

    # And with neither (no ~/Developer at all), the parent of the last
    # project used is the best available answer.
    monkeypatch.setattr(panels.Path, "home", classmethod(lambda cls: Path("/nowhere")))
    dirs = client.get("/v2/mode-dirs", headers=AUTH).json()["dirs"]
    assert dirs["faber"] == "/repo"


def test_mode_dirs_requires_auth(client):
    assert client.get("/v2/mode-dirs").status_code == 401


# --------------------------------------------------------- inbox actions

def test_a_proposal_summary_is_its_rationale_not_its_heading():
    """The inbox read the body's first line, which is "## Rationale" — so
    every item displayed the header while the sentence explaining it sat
    unread on the line below. One section reader now, nightshift's, used by
    the listing and by the apply pipeline alike."""
    from nightshift.apply import _section

    body = "## Rationale\nThe actual reason.\n\n## Diff\n(none)\n"
    assert _section(body, "## rationale") == "The actual reason."
    assert _section(body, "## diff") == "(none)"
    assert _section(body, "## missing") is None


# `test_deciding_archives_rather_than_applies` stood here until 2026-09-14. It
# pinned the inversion the inbox rebuild removed: accepting now applies the
# diff (test_inbox.py). The guarantee that survives is that *maintenance*
# never edits; the person accepting is the edit.


def test_an_unsafe_item_id_is_refused(client):
    """It is joined into a vault path, so it is the same class of input as
    the job_slug traversal caught in the 2026-07-21 review."""
    r = client.post("/v2/inbox/..%2F..%2Fetc%2Fpasswd/accept", headers=AUTH)
    assert r.status_code in (400, 404)


def test_only_accept_or_reject_are_decisions(client):
    assert client.post("/v2/inbox/x/maybe", headers=AUTH).status_code == 400


def test_deciding_requires_auth(client):
    assert client.post("/v2/inbox/x/accept").status_code == 401




def test_the_status_line_feeds_the_rolling_windows(client):
    """An interactive session's only route for what the stream used to carry.

    It also survives a page reload, which the stream never did: the numbers
    live in the backend rather than in React state, so the bar is right the
    moment the window opens instead of after the first turn.
    """
    import routers.sessions_v2 as sv2
    sv2._statusline.clear()
    payload = {
        "session_id": "s-1",
        "rate_limits": {"five_hour": {"used_percentage": 3, "resets_at": 1789338000},
                        "seven_day": {"used_percentage": 9, "resets_at": 1789383600}},
        "context_window": {"used_percentage": 20},
        "model": {"id": "claude-opus-5"},
    }
    assert client.post("/v2/sessions/statusline?slot=term-1", json=payload, headers=AUTH).status_code == 200

    limits = client.get("/v2/sessions/limits", headers=AUTH).json()
    assert limits["known"] is True
    assert limits["five_hour"]["used"] == 0.03
    assert limits["seven_day"]["used"] == 0.09
    assert limits["five_hour"]["resets_at"] == 1789338000

    back = client.get("/v2/sessions/statusline/all", headers=AUTH).json()["slots"]
    assert back["term-1"]["context_window"]["used_percentage"] == 20


def test_a_status_line_post_never_rejects_a_shape(client):
    """A hot path on every render of every open terminal. A validation error
    would put a traceback in the middle of somebody's session, and a status
    line is not worth that."""
    for junk in ({}, {"rate_limits": None}, {"rate_limits": {"five_hour": {}}},
                 {"session_id": 12, "cost": "not an object"}):
        assert client.post("/v2/sessions/statusline", json=junk, headers=AUTH).status_code == 200


def test_interactive_args_are_served_per_mode(client):
    r = client.get("/v2/sessions/interactive-args",
                   params={"mode": "faber", "cwd": str(Path.home())}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["model"] and body["binary"]
    assert "-p" not in body["args"]


def test_interactive_args_refuse_an_unknown_mode(client):
    r = client.get("/v2/sessions/interactive-args",
                   params={"mode": "nonsense", "cwd": str(Path.home())}, headers=AUTH)
    assert r.status_code == 400


def test_a_status_line_report_is_filed_under_its_slot(client):
    """The shell's strip asks for its own terminal's reading by the name it
    gave the terminal, because the session id is not known to the shell until
    this very report arrives."""
    client.post("/v2/sessions/statusline?mode=faber&slot=term-a", headers=AUTH,
                json={"session_id": "s-a", "model": {"id": "claude-sonnet-5"}})
    got = client.get("/v2/sessions/statusline/all", headers=AUTH).json()["slots"]["term-a"]
    assert got["model"]["id"] == "claude-sonnet-5"
    assert "reported_at" in got, "the bar shows the reading's age"
    # A '-' slot means the shell gave none; the report is filed under its
    # session id, which is not a slot and so is not in the strip's listing.
    import routers.sessions_v2 as sv2
    client.post("/v2/sessions/statusline?slot=-", headers=AUTH, json={"session_id": "s-b"})
    assert "s-b" in sv2._statusline
    assert "s-b" not in client.get("/v2/sessions/statusline/all", headers=AUTH).json()["slots"]


def test_limits_carry_when_they_were_last_reported(client):
    """An idle terminal re-reports the same figure while other sessions move
    the account on. The age is what makes a stale reading look stale rather
    than wrong -- and it must not advance just because the bar polled."""
    payload = {"session_id": "s-1",
               "rate_limits": {"five_hour": {"used_percentage": 33, "resets_at": 1},
                               "seven_day": {"used_percentage": 12, "resets_at": 2}}}
    client.post("/v2/sessions/statusline", json=payload, headers=AUTH)
    first = client.get("/v2/sessions/limits", headers=AUTH).json()["reported_at"]
    again = client.get("/v2/sessions/limits", headers=AUTH).json()["reported_at"]
    assert first == again, "polling is not a new reading"
    client.post("/v2/sessions/statusline", json=payload, headers=AUTH)
    assert client.get("/v2/sessions/limits", headers=AUTH).json()["reported_at"] >= first


def test_a_report_says_whether_its_session_can_be_resumed(client, tmp_path):
    """The CLI assigns a session id at start and writes the transcript on
    the first message. A terminal opened and never spoken to has an id that
    `--resume` cannot find, and a shell that remembered it came back to "No
    conversation found" instead of a fresh session. The report says which."""
    import routers.sessions_v2 as sv2
    sv2._statusline.clear()
    written = tmp_path / "abc.jsonl"
    written.write_text("{}", encoding="utf-8")

    client.post("/v2/sessions/statusline?slot=term-yes", headers=AUTH,
                json={"session_id": "abc", "transcript_path": str(written)})
    client.post("/v2/sessions/statusline?slot=term-no", headers=AUTH,
                json={"session_id": "def", "transcript_path": str(tmp_path / "def.jsonl")})
    client.post("/v2/sessions/statusline?slot=term-none", headers=AUTH,
                json={"session_id": "ghi"})

    slots = client.get("/v2/sessions/statusline/all", headers=AUTH).json()["slots"]
    assert slots["term-yes"]["transcript_exists"] is True
    assert slots["term-no"]["transcript_exists"] is False
    assert slots["term-none"]["transcript_exists"] is False
    sv2._statusline.clear()


def test_an_empty_cwd_is_refused_not_defaulted(client):
    """`Path("")` is `Path(".")`, which resolves to wherever the backend runs
    -- inside home, so the confinement passed and a session opened in the
    backend's own directory. Found by the route sweep."""
    for cwd in ("", "   "):
        r = client.get("/v2/sessions/interactive-args", headers=AUTH,
                       params={"mode": "faber", "cwd": cwd})
        assert r.status_code == 400, cwd


def test_deleting_a_conversation_tombstones_its_engine_id(client):
    import routers.sessions_v2 as sv2
    sid = sv2._store.open_session("vesper", cwd="/tmp", title="to go")
    sv2._store.db.execute("UPDATE sessions SET engine_session_id='eng-gone' WHERE id=?", (sid,))
    sv2._store.db.commit()
    assert client.delete(f"/v2/sessions/history/{sid}", headers=AUTH).status_code == 200
    assert sv2._store.is_forgotten("eng-gone")
    assert sv2._store.find_by_engine_id("eng-gone") is None


def test_the_shell_can_close_a_slot_out_of_the_live_count(client):
    """Liveness is "reported within half a minute" for a terminal that died
    without saying so. One the shell watched exit says so, and leaves the
    count at once rather than thirty seconds later."""
    import routers.sessions_v2 as sv2
    sv2._statusline.clear()
    client.post("/v2/sessions/statusline?slot=term-bye", headers=AUTH, json={"session_id": "s"})
    assert client.get("/v2/sessions", headers=AUTH).json()["running"] == 1
    assert client.delete("/v2/sessions/statusline/term-bye", headers=AUTH).status_code == 200
    assert client.get("/v2/sessions", headers=AUTH).json()["running"] == 0
    # Closing a slot that is not there is not an error.
    assert client.delete("/v2/sessions/statusline/term-never", headers=AUTH).status_code == 200


def test_interactive_args_with_a_resume_id_lifts_its_tombstone(client, monkeypatch):
    """The shell asks for a resumed session's argv; that is the moment a
    conversation deleted from history is being asked for again."""
    from routers import sessions_v2
    lifted = []
    monkeypatch.setattr(sessions_v2._store, "unforget", lambda eid: lifted.append(eid))
    r = client.get("/v2/sessions/interactive-args", headers=AUTH,
                   params={"mode": "general", "cwd": "~", "resume_id": "abc-123"})
    assert r.status_code == 200
    assert lifted == ["abc-123"]
    r = client.get("/v2/sessions/interactive-args", headers=AUTH,
                   params={"mode": "general", "cwd": "~"})
    assert r.status_code == 200 and lifted == ["abc-123"], "no resume, nothing lifted"


def test_a_malformed_status_line_report_is_kept_and_its_numbers_ignored(client):
    """The route runs every five seconds per terminal on whatever shape this
    CLI version writes. A `rate_limits` that is a string answered 500 -- a
    traceback per terminal per five seconds. The slot stays live; the
    numbers are simply not a reading."""
    import routers.sessions_v2 as sv2
    before = sv2._limits
    for body in ({"rate_limits": "nope", "session_id": "x"},
                 {"rate_limits": {"five_hour": "3", "seven_day": {}}, "session_id": "x"},
                 {"rate_limits": {"five_hour": {"used_percentage": "lots", "resets_at": None},
                                  "seven_day": {"used_percentage": 1}}, "session_id": "x"}):
        r = client.post("/v2/sessions/statusline", json=body, headers=AUTH,
                        params={"mode": "general", "slot": "term-odd"})
        assert r.status_code == 200, body
    assert sv2._limits is before, "no reading was taken from garbage"
    assert "term-odd" in sv2._statusline, "the slot is still live"
    client.delete("/v2/sessions/statusline/term-odd", headers=AUTH)
