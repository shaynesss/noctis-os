import vault_io


def test_health_strip_requires_auth(client):
    response = client.get("/health/strip")
    assert response.status_code == 401


def test_health_strip_shape(client, auth_headers, vault):
    vault_io.write_file(
        "wiki/Lint History.md",
        "# Lint History\n\n## 2026-07-22 — run 1\n\nBaseline.\n",
    )

    response = client.get("/health/strip", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["lint"]["status"] == "ok"
    assert body["lint"]["last_run"] == "2026-07-22"
    assert body["istefox"]["status"] == "ok"
