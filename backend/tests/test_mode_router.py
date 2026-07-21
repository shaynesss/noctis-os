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
        }
    ]


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
