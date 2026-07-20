import launch_surfaces


def test_unknown_mode_404(client, auth_headers):
    response = client.post("/session/launch", json={"mode": "nonexistent"}, headers=auth_headers)
    assert response.status_code == 404


def test_nondev_launch_opens_terminal(client, auth_headers, vault, monkeypatch):
    calls = []
    monkeypatch.setattr(
        launch_surfaces,
        "launch_terminal",
        lambda mode, job_label, prompt, model=None: calls.append((mode, job_label, model)),
    )

    response = client.post("/session/launch", json={"mode": "learn"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"launched": True, "mode": "learn", "surface": "terminal"}
    assert calls == [("learn", "no active job", None)]


def test_dev_launch_requires_project_path(client, auth_headers, vault):
    response = client.post("/session/launch", json={"mode": "dev"}, headers=auth_headers)
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
        lambda project_path, prompt, model=None: calls.append((project_path, model)),
    )

    response = client.post(
        "/session/launch",
        json={"mode": "dev", "job_slug": "noctis-build", "model": "claude-opus-4-8"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["surface"] == "vscode"
    assert calls == [("/tmp/noctis-os", "claude-opus-4-8")]
