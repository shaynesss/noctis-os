def test_missing_token_rejected(client):
    response = client.get("/mode/dev")
    assert response.status_code == 401


def test_wrong_token_rejected(client):
    response = client.get("/mode/dev", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_correct_token_accepted(client, auth_headers):
    response = client.get("/mode/dev", headers=auth_headers)
    assert response.status_code == 200


def test_disallowed_origin_rejected(client, auth_headers):
    headers = {**auth_headers, "Origin": "http://evil.example"}
    response = client.get("/mode/dev", headers=headers)
    assert response.status_code == 403


def test_allowed_origin_accepted(client, auth_headers):
    headers = {**auth_headers, "Origin": "http://localhost:5173"}
    response = client.get("/mode/dev", headers=headers)
    assert response.status_code == 200


def test_health_does_not_require_auth(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_cors_preflight_allows_frontend_origin(client):
    # Regression: the browser blocks every cross-origin fetch from the Vite
    # dev server without this — caught live when World.tsx's first fetch
    # against a running backend failed silently in the console.
    response = client.options(
        "/mode/dev",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_preflight_rejects_other_origins(client):
    response = client.options(
        "/mode/dev",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers
