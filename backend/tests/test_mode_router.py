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
