from auth import ALLOWED_ORIGIN, TAURI_ORIGIN


def test_missing_token_rejected(client):
    response = client.get("/v2/inbox")
    assert response.status_code == 401


def test_wrong_token_rejected(client):
    response = client.get("/v2/inbox", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_correct_token_accepted(client, auth_headers):
    response = client.get("/v2/inbox", headers=auth_headers)
    assert response.status_code == 200


def test_disallowed_origin_rejected(client, auth_headers):
    headers = {**auth_headers, "Origin": "http://evil.example"}
    response = client.get("/v2/inbox", headers=headers)
    assert response.status_code == 403


def test_allowed_origin_accepted(client, auth_headers):
    headers = {**auth_headers, "Origin": ALLOWED_ORIGIN}
    response = client.get("/v2/inbox", headers=headers)
    assert response.status_code == 200


def test_health_does_not_require_auth(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_cors_preflight_allows_frontend_origin(client):
    # Regression: the browser blocks every cross-origin fetch from the Vite
    # dev server without this — caught live when World.tsx's first fetch
    # against a running backend failed silently in the console.
    response = client.options(
        "/v2/config",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_cors_preflight_rejects_other_origins(client):
    response = client.options(
        "/v2/config",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_packaged_app_origin_is_accepted(auth_headers, client):
    """Tauri serves the bundled frontend from tauri://localhost, not from the
    dev server's port. Allowing only the dev origin ships an app that cannot
    reach its own backend -- and it passes every test in development."""
    r = client.get("/v2/inbox", headers={**auth_headers, "Origin": TAURI_ORIGIN})
    assert r.status_code != 403


def test_an_unrelated_origin_is_still_refused(auth_headers, client):
    r = client.get("/v2/inbox", headers={**auth_headers, "Origin": "http://evil.example"})
    assert r.status_code == 403


def test_every_routes_method_passes_the_browsers_preflight(client):
    """The test client never sends a preflight, so a method missing from the
    CORS list passes every other test and fails only in the browser. PUT and
    DELETE did exactly that: Settings could not save a prompt and a closed
    terminal was never released. Checked against the routes themselves, so a
    new route with a new method fails here rather than in the app."""
    from main import app

    # From the schema rather than app.routes: included routers sit behind a
    # wrapper there, and walking it found only /health's GET.
    methods = {m.upper() for ops in app.openapi()["paths"].values() for m in ops}
    assert {"PUT", "DELETE"} <= methods  # the two that were missing are still routed
    for method in sorted(methods):
        r = client.options("/v2/config", headers={
            "Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": method})
        assert r.status_code == 200, f"{method} preflight refused: {r.text}"


def test_no_route_but_health_answers_without_the_token(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code in (401, 404), path


def test_the_access_log_drops_successful_polls_and_keeps_everything_else():
    import logging
    from main import QuietPolls
    f = QuietPolls()
    rec = lambda method, path, status: logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:1", method, path, "1.1", status), None)
    assert not f.filter(rec("POST", "/v2/sessions/statusline?mode=faber&slot=t1", 200))
    assert not f.filter(rec("GET", "/health", 200))
    assert f.filter(rec("OPTIONS", "/v2/sessions/statusline/term-1", 400)), "a refusal is the line worth having"
    assert f.filter(rec("GET", "/v2/sessions/limits", 500))
    assert f.filter(rec("PUT", "/v2/prompts/system", 200)), "anything not polled is logged"
