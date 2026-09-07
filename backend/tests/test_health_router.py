from datetime import date

import vault_io


def test_health_strip_requires_auth(client):
    response = client.get("/health/strip")
    assert response.status_code == 401


def test_health_strip_shape(client, auth_headers, vault):
    # Relative, not hardcoded: lint goes stale after 7 days, so a fixed
    # date turns this into a time bomb that passes the week it is written
    # and fails forever after (it had been failing since 2026-07-29).
    today = date.today().isoformat()
    vault_io.write_file(
        "wiki/Lint History.md",
        f"# Lint History\n\n## {today} — run 1\n\nBaseline.\n",
    )

    response = client.get("/health/strip", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["lint"]["status"] == "ok"
    assert body["lint"]["last_run"] == today
    assert "istefox" not in body
