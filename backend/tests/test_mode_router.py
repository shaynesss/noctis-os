import vault_io


def test_unknown_mode_404(client, auth_headers):
    response = client.get("/mode/nonexistent", headers=auth_headers)
    assert response.status_code == 404


def test_known_mode_returns_state(client, auth_headers, vault):
    vault_io.write_frontmatter(
        "modes/learn/state.md",
        {"mode": "learn", "busy": False, "deep_due": 4},
        "notes",
    )
    response = client.get("/mode/learn", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["deep_due"] == 4


def test_create_job_writes_context_and_syncs_state(client, auth_headers, vault):
    response = client.post(
        "/mode/dev/jobs",
        json={"slug": "new-project", "name": "New Project", "project_path": "/tmp/new-project"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stage"] == "Plan"
    assert body["status"] == "just started"

    metadata, _ = vault_io.read_frontmatter("modes/dev/jobs/new-project/context.md")
    assert metadata["name"] == "New Project"
    assert metadata["project_path"] == "/tmp/new-project"

    state_meta, _ = vault_io.read_frontmatter("modes/dev/state.md")
    assert state_meta["jobs"][0]["slug"] == "new-project"
    assert state_meta["jobs"][0]["flagged"] is False


def test_create_job_notes_become_context_prose(client, auth_headers, vault):
    """notes is what POST /session/launch actually injects into the launch
    prompt -- a scoped launch (e.g. Custos "address this trigger") needs
    real task direction here, not just a job name."""
    response = client.post(
        "/mode/settings/jobs",
        json={"slug": "address-friction", "name": "Address friction", "notes": "Read modes/*/lessons.md for FRICTION: entries."},
        headers=auth_headers,
    )
    assert response.status_code == 200

    _, content = vault_io.read_frontmatter("modes/settings/jobs/address-friction/context.md")
    assert content.strip() == "Read modes/*/lessons.md for FRICTION: entries."


def test_create_job_conflicts_on_existing_slug(client, auth_headers, vault):
    client.post("/mode/dev/jobs", json={"slug": "dup", "name": "Dup"}, headers=auth_headers)
    response = client.post("/mode/dev/jobs", json={"slug": "dup", "name": "Dup again"}, headers=auth_headers)
    assert response.status_code == 409


def test_create_job_rejects_path_traversal_slug(client, auth_headers, vault):
    response = client.post(
        "/mode/dev/jobs",
        json={"slug": "../../../../tmp/pwned", "name": "evil"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert not (vault.parent.parent.parent.parent / "tmp" / "pwned").exists()


def test_update_job_rejects_invalid_slug(client, auth_headers, vault):
    # httpx normalizes ".." out of the URL before the request is even
    # sent, so it can't reach the handler this way -- is_safe_slug is
    # still the correct backstop regardless of a given client's URL
    # normalization behavior. Use an unambiguous single-segment value
    # that can't be normalized away but still fails validation.
    response = client.patch("/mode/dev/jobs/UPPERCASE", json={"stage": "Ship"}, headers=auth_headers)
    assert response.status_code == 400


def test_get_job_log_rejects_invalid_slug(client, auth_headers, vault):
    response = client.get("/mode/dev/jobs/UPPERCASE/log", headers=auth_headers)
    assert response.status_code == 400


def _seed_job(vault, mode="dev", slug="noctis-build"):
    job_dir = vault / "modes" / mode / "jobs" / slug
    job_dir.mkdir(parents=True)
    (job_dir / "context.md").write_text(
        "---\nname: Noctis build\nstage: Build\nstatus: in progress\n---\n\nnotes\n",
        encoding="utf-8",
    )
    vault_io.write_frontmatter(f"modes/{mode}/state.md", {"mode": mode, "busy": True, "jobs": []}, "")


def test_update_job_unknown_job_404(client, auth_headers, vault):
    response = client.patch(
        "/mode/dev/jobs/nonexistent", json={"stage": "Ship"}, headers=auth_headers
    )
    assert response.status_code == 404


def test_update_job_rewrites_context_and_syncs_state(client, auth_headers, vault):
    _seed_job(vault)

    response = client.patch("/mode/dev/jobs/noctis-build", json={"stage": "Ship"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["stage"] == "Ship"

    metadata, _ = vault_io.read_frontmatter("modes/dev/jobs/noctis-build/context.md")
    assert metadata["stage"] == "Ship"
    assert metadata["last_touched"]

    state_meta, _ = vault_io.read_frontmatter("modes/dev/state.md")
    assert state_meta["jobs"] == [
        {
            "slug": "noctis-build",
            "name": "Noctis build",
            "stage": "Ship",
            "status": "in progress",
            "last_touched": metadata["last_touched"],
            "flagged": False,
        }
    ]


def test_update_job_can_clear_flagged(client, auth_headers, vault):
    """staleness.py can set flagged, but nothing could clear it -- found
    2026-07-21 via a real flagged job. Resume is the natural place to clear
    it (World.tsx), which needs update_job to actually accept the field."""
    job_dir = vault / "modes" / "dev" / "jobs" / "flagged-job"
    job_dir.mkdir(parents=True)
    (job_dir / "context.md").write_text(
        "---\nname: Flagged\nstage: Build\nstatus: stalled\nflagged: true\n---\n\nnotes\n",
        encoding="utf-8",
    )
    vault_io.write_frontmatter(
        "modes/dev/state.md",
        {"mode": "dev", "busy": False, "jobs": [{"slug": "flagged-job", "flagged": True}]},
        "",
    )

    response = client.patch("/mode/dev/jobs/flagged-job", json={"flagged": False}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["flagged"] is False
    metadata, _ = vault_io.read_frontmatter("modes/dev/jobs/flagged-job/context.md")
    assert metadata["flagged"] is False
    state_meta, _ = vault_io.read_frontmatter("modes/dev/state.md")
    assert state_meta["jobs"][0]["flagged"] is False


def test_get_job_log_empty_when_no_session_run(client, auth_headers, vault):
    response = client.get("/mode/dev/jobs/noctis-build/log", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"lines": []}


def test_get_job_log_returns_tailed_lines(client, auth_headers, vault, monkeypatch):
    import routers.mode as mode_router

    monkeypatch.setattr(mode_router, "RUNTIME_DIR", vault / "runtime")
    (vault / "runtime").mkdir()
    (vault / "runtime" / "dev__noctis-build.log").write_text("line1\nline2\nline3\n", encoding="utf-8")

    response = client.get("/mode/dev/jobs/noctis-build/log?lines=2", headers=auth_headers)
    assert response.json() == {"lines": ["line2", "line3"]}


def test_get_job_log_falls_back_to_general_log(client, auth_headers, vault, monkeypatch):
    """A job created mid-session by a generically-launched terminal
    (NOCTIS_JOB_ID defaults to "general") has no log of its own -- its
    activity is all sitting in general.log. Found 2026-07-22 via a real
    research job (brunei-ai-smb-consulting) whose action-feed line was
    permanently empty despite an active session."""
    import routers.mode as mode_router

    monkeypatch.setattr(mode_router, "RUNTIME_DIR", vault / "runtime")
    (vault / "runtime").mkdir()
    (vault / "runtime" / "research__general.log").write_text("line1\nline2\n", encoding="utf-8")

    response = client.get("/mode/research/jobs/brunei-ai-smb-consulting/log", headers=auth_headers)

    assert response.json() == {"lines": ["line1", "line2"]}


def test_get_job_log_prefers_own_log_over_general_fallback(client, auth_headers, vault, monkeypatch):
    import routers.mode as mode_router

    monkeypatch.setattr(mode_router, "RUNTIME_DIR", vault / "runtime")
    (vault / "runtime").mkdir()
    (vault / "runtime" / "research__general.log").write_text("general line\n", encoding="utf-8")
    (vault / "runtime" / "research__brunei-ai-smb-consulting.log").write_text("own line\n", encoding="utf-8")

    response = client.get("/mode/research/jobs/brunei-ai-smb-consulting/log", headers=auth_headers)

    assert response.json() == {"lines": ["own line"]}
