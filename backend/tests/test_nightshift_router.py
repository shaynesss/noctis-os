import vault_io

STATE_PATH = "modes/nightshift/state.md"


def _seed_inbox(vault, items):
    vault_io.write_frontmatter(STATE_PATH, {"mode": "nightshift", "busy": False, "inbox": items}, "notes")


def test_get_inbox_returns_staged_items(client, auth_headers, vault):
    _seed_inbox(
        vault,
        [{"slug": "a", "origin_mode": "learn", "description": "due reviews staged", "confidence": None}],
    )
    response = client.get("/nightshift/inbox", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()[0]["slug"] == "a"


def test_accept_removes_from_inbox_and_logs(client, auth_headers, vault):
    _seed_inbox(
        vault,
        [{"slug": "a", "origin_mode": "learn", "description": "due reviews staged", "confidence": None}],
    )
    response = client.post("/nightshift/inbox/a/accept", headers=auth_headers)
    assert response.status_code == 200

    metadata, _ = vault_io.read_frontmatter(STATE_PATH)
    assert metadata["inbox"] == []
    assert "accepted" in vault_io.read_file("log.md")


def test_reject_removes_from_inbox_and_logs(client, auth_headers, vault):
    _seed_inbox(
        vault,
        [{"slug": "b", "origin_mode": "research", "description": "parked trigger fired", "confidence": "low"}],
    )
    response = client.post("/nightshift/inbox/b/reject", headers=auth_headers)
    assert response.status_code == 200

    metadata, _ = vault_io.read_frontmatter(STATE_PATH)
    assert metadata["inbox"] == []
    assert "rejected" in vault_io.read_file("log.md")


def test_unknown_item_404(client, auth_headers, vault):
    _seed_inbox(vault, [])
    response = client.post("/nightshift/inbox/nonexistent/accept", headers=auth_headers)
    assert response.status_code == 404


def test_history_returns_past_decisions_most_recent_first(client, auth_headers, vault):
    _seed_inbox(
        vault,
        [
            {"slug": "a", "origin_mode": "learn", "description": "first one", "confidence": None},
            {"slug": "b", "origin_mode": "research", "description": "second one", "confidence": "low"},
        ],
    )
    client.post("/nightshift/inbox/a/accept", headers=auth_headers)
    client.post("/nightshift/inbox/b/reject", headers=auth_headers)

    response = client.get("/nightshift/history", headers=auth_headers)
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 2
    # most recent (b, rejected) first -- log.md is append-only, history reverses it
    assert entries[0]["slug"] == "b"
    assert entries[0]["decision"] == "rejected"
    assert entries[0]["origin_mode"] == "research"
    assert entries[1]["slug"] == "a"
    assert entries[1]["decision"] == "accepted"


def test_history_respects_limit(client, auth_headers, vault):
    _seed_inbox(
        vault,
        [{"slug": "a", "origin_mode": "learn", "description": "first one", "confidence": None}],
    )
    client.post("/nightshift/inbox/a/accept", headers=auth_headers)

    response = client.get("/nightshift/history?limit=0", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_history_ignores_unrelated_log_lines(client, auth_headers, vault):
    existing = vault_io.read_file("log.md")
    vault_io.write_file("log.md", existing + "- 2026-07-22 09:00 some unrelated log entry\n")

    response = client.get("/nightshift/history", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_get_archived_proposal_after_accept(client, auth_headers, vault):
    _seed_inbox(
        vault,
        [{"slug": "a", "origin_mode": "learn", "description": "first one", "confidence": None}],
    )
    vault_io.write_file(
        "modes/nightshift/inbox/a.md",
        "## Rationale\nwhy\n\n## Diff\n(none)\n\n## Evidence\n- x\n",
    )
    client.post("/nightshift/inbox/a/accept", headers=auth_headers)

    response = client.get("/nightshift/archive/a", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "a"
    assert "## Rationale" in body["proposal"]


def test_get_archived_proposal_missing_404(client, auth_headers, vault):
    response = client.get("/nightshift/archive/nonexistent", headers=auth_headers)
    assert response.status_code == 404


def _seed_proposal(vault, slug, text="the full diff + cited lessons"):
    proposal_dir = vault / "modes" / "nightshift" / "inbox"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    (proposal_dir / f"{slug}.md").write_text(text, encoding="utf-8")


def test_get_inbox_item_returns_full_proposal(client, auth_headers, vault):
    _seed_inbox(
        vault,
        [{"slug": "a", "origin_mode": "settings", "description": "diff", "rationale": "why", "confidence": None}],
    )
    _seed_proposal(vault, "a")

    response = client.get("/nightshift/inbox/a", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["proposal"] == "the full diff + cited lessons"


def test_accept_archives_proposal_file(client, auth_headers, vault):
    _seed_inbox(
        vault,
        [{"slug": "a", "origin_mode": "settings", "description": "diff", "rationale": "why", "confidence": None}],
    )
    _seed_proposal(vault, "a")

    response = client.post("/nightshift/inbox/a/accept", headers=auth_headers)
    assert response.status_code == 200

    assert not (vault / "modes/nightshift/inbox/a.md").exists()
    assert (vault / "modes/nightshift/archive/a.md").exists()


def test_reject_archives_proposal_file(client, auth_headers, vault):
    _seed_inbox(
        vault,
        [{"slug": "b", "origin_mode": "research", "description": "verdict", "rationale": "why", "confidence": "low"}],
    )
    _seed_proposal(vault, "b")

    response = client.post("/nightshift/inbox/b/reject", headers=auth_headers)
    assert response.status_code == 200

    assert not (vault / "modes/nightshift/inbox/b.md").exists()
    assert (vault / "modes/nightshift/archive/b.md").exists()


def test_accept_applies_a_real_diff(client, auth_headers, vault):
    vault_io.write_file("modes/settings/settings.md", "before\nold rule text\nafter\n")
    _seed_inbox(
        vault,
        [{"slug": "a", "origin_mode": "settings", "description": "diff", "rationale": "why", "confidence": None}],
    )
    _seed_proposal(
        vault,
        "a",
        text=(
            "## Rationale\nwhy\n\n## Diff\n"
            "--- modes/settings/settings.md\n+++ modes/settings/settings.md\n@@\n"
            "- old rule text\n+ new rule text\n\n## Evidence\n- x\n"
        ),
    )

    response = client.post("/nightshift/inbox/a/accept", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["applied_to"] == "modes/settings/settings.md"
    assert "new rule text" in vault_io.read_file("modes/settings/settings.md")


def test_accept_advances_lessons_cursor_to_live_line_count_not_marker_number(client, auth_headers, vault):
    """The marker's own number (dev=20 below) is deliberately ignored --
    advance_lessons_cursor reads modes/dev/lessons.md's actual line count
    at accept time instead, since a session-drafted number can go stale
    between proposal and accept (the bug this guards against)."""
    vault_io.write_frontmatter(
        "modes/settings/state.md",
        {"mode": "settings", "busy": False, "inbox": [], "lessons_distilled_through": {"dev": 12}},
        "",
    )
    vault_io.write_file("modes/dev/lessons.md", "\n".join(f"line {i}" for i in range(25)) + "\n")
    _seed_inbox(
        vault,
        [{"slug": "a", "origin_mode": "settings", "description": "distill", "rationale": "why", "confidence": None}],
    )
    _seed_proposal(
        vault,
        "a",
        text="## Rationale\nwhy\n\n## Diff\n(none)\n\n## Evidence\n- x\n\n<!-- cursor-advance: dev=20 -->\n",
    )

    response = client.post("/nightshift/inbox/a/accept", headers=auth_headers)

    assert response.status_code == 200
    state, _ = vault_io.read_frontmatter("modes/settings/state.md")
    assert state["lessons_distilled_through"]["dev"] == 25


def test_accept_leaves_item_pending_when_diff_apply_fails(client, auth_headers, vault):
    vault_io.write_file("modes/settings/settings.md", "content that doesn't match\n")
    _seed_inbox(
        vault,
        [{"slug": "a", "origin_mode": "settings", "description": "diff", "rationale": "why", "confidence": None}],
    )
    _seed_proposal(
        vault,
        "a",
        text=(
            "## Rationale\nwhy\n\n## Diff\n"
            "--- modes/settings/settings.md\n+++ modes/settings/settings.md\n@@\n"
            "- text nowhere in the file\n+ replacement\n\n## Evidence\n- x\n"
        ),
    )

    response = client.post("/nightshift/inbox/a/accept", headers=auth_headers)

    assert response.status_code == 422
    metadata, _ = vault_io.read_frontmatter(STATE_PATH)
    assert len(metadata["inbox"]) == 1
    assert (vault / "modes/nightshift/inbox/a.md").exists()
