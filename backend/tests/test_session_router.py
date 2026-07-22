import launch_surfaces
import vault_io


def test_unknown_mode_404(client, auth_headers):
    response = client.post("/session/launch", json={"mode": "nonexistent"}, headers=auth_headers)
    assert response.status_code == 404


def test_nondev_launch_opens_terminal(client, auth_headers, vault, monkeypatch):
    calls = []
    monkeypatch.setattr(
        launch_surfaces,
        "launch_terminal",
        lambda mode, job_label, prompt, job_slug=None, model=None: calls.append(
            (mode, job_label, job_slug, model)
        ),
    )

    response = client.post("/session/launch", json={"mode": "learn"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"launched": True, "mode": "learn", "surface": "terminal"}
    assert calls == [("learn", "no active job", None, None)]

    # Nothing in the system ever set this before -- found live when
    # launching Noctua's session didn't update its card at all.
    state, _ = vault_io.read_frontmatter("modes/learn/state.md")
    assert state["busy"] is True


def test_dev_launch_requires_project_path(client, auth_headers, vault):
    response = client.post("/session/launch", json={"mode": "dev"}, headers=auth_headers)
    assert response.status_code == 400


def test_launch_rejects_path_traversal_job_slug(client, auth_headers, vault):
    response = client.post(
        "/session/launch",
        json={"mode": "learn", "job_slug": "../../../../tmp/evil"},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_dev_launch_opens_vscode(client, auth_headers, vault, monkeypatch):
    job_dir = vault / "modes" / "dev" / "jobs" / "noctis-build"
    job_dir.mkdir(parents=True)
    (job_dir / "context.md").write_text(
        "---\nstage: Build\nproject_path: /tmp/noctis-os\n---\n\nnotes\n", encoding="utf-8"
    )

    calls = []
    monkeypatch.setattr(
        launch_surfaces,
        "launch_dev",
        lambda project_path, prompt, job_slug=None, model=None: calls.append(
            (project_path, job_slug, model)
        ),
    )

    response = client.post(
        "/session/launch",
        json={"mode": "dev", "job_slug": "noctis-build", "model": "claude-opus-4-8"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["surface"] == "vscode"
    assert calls == [("/tmp/noctis-os", "noctis-build", "claude-opus-4-8")]


def test_dev_launch_stamps_resumed_shipped_marker(client, auth_headers, vault, monkeypatch):
    job_dir = vault / "modes" / "dev" / "jobs" / "portfolio-platform"
    job_dir.mkdir(parents=True)
    job_dir.joinpath("context.md").write_text(
        "---\nstage: Ship\nstatus: v1 live, fully shippable\n"
        "project_path: /tmp/portfolio-platform\n---\n",
        encoding="utf-8",
    )

    calls = []
    monkeypatch.setattr(
        launch_surfaces,
        "launch_dev",
        lambda project_path, prompt, job_slug=None, model=None: calls.append(prompt),
    )

    response = client.post(
        "/session/launch",
        json={"mode": "dev", "job_slug": "portfolio-platform"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert calls[0].startswith("[RESUMED-SHIPPED-BUILD stage=Ship")


def test_dev_launch_no_marker_for_fresh_job(client, auth_headers, vault, monkeypatch):
    job_dir = vault / "modes" / "dev" / "jobs" / "new-build"
    job_dir.mkdir(parents=True)
    job_dir.joinpath("context.md").write_text(
        "---\nstage: Plan\nproject_path: /tmp/new-build\n---\n",
        encoding="utf-8",
    )

    calls = []
    monkeypatch.setattr(
        launch_surfaces,
        "launch_dev",
        lambda project_path, prompt, job_slug=None, model=None: calls.append(prompt),
    )

    response = client.post(
        "/session/launch",
        json={"mode": "dev", "job_slug": "new-build"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert not calls[0].startswith("[RESUMED-SHIPPED-BUILD")
