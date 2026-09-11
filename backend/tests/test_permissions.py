"""The permission gate — what makes the chip a control rather than a caption.

Before this existed, `--permission-prompts` had nobody to hand a question to,
so everything that would ask was refused: `manual` silently meant `never`, and
a chip reading acceptEdits sat above a session that could not write.
"""
import threading
import time

import pytest

from permissions import PermissionRegistry

AUTH = {"Authorization": "Bearer test-token-123", "Origin": "http://localhost:5180"}


def test_a_decision_releases_the_waiting_session():
    reg = PermissionRegistry(timeout=5)
    result = {}

    def asker():
        result["req"] = reg.ask("faber", "Write", {"file_path": "/tmp/x"})

    t = threading.Thread(target=asker)
    t.start()
    for _ in range(100):                 # let the request register
        if reg.pending():
            break
        time.sleep(0.01)

    (pending,) = reg.pending()
    assert pending["tool"] == "Write"
    assert pending["args"]["file_path"] == "/tmp/x"

    assert reg.decide(pending["id"], "allow") is True
    t.join(timeout=5)
    assert result["req"].decision == "allow"
    assert result["req"].expired is False


def test_an_unanswered_request_denies_rather_than_hanging():
    """A prompt nobody answers must not hold a session open forever, and the
    default for a question you were not present for is no."""
    reg = PermissionRegistry(timeout=0.1)
    req = reg.ask("faber", "Bash", {"command": "rm -rf /"})
    assert req.decision == "deny"
    assert req.expired is True


def test_a_settled_request_stops_being_pending():
    """Otherwise the dialog stays on screen after you answer it."""
    reg = PermissionRegistry(timeout=0.1)
    reg.ask("faber", "Write", {})
    assert reg.pending() == []


def test_deciding_something_unknown_reports_failure():
    """It expired while the dialog was still up. Reporting success would have
    the UI say 'allowed' about a session that already gave up."""
    reg = PermissionRegistry(timeout=0.1)
    assert reg.decide("nope", "allow") is False


def test_concurrent_requests_are_answered_independently():
    """Two modes can be waiting at once -- the cap is two -- and answering one
    must not release the other."""
    reg = PermissionRegistry(timeout=5)
    done = {}

    def asker(name):
        done[name] = reg.ask(name, "Write", {"n": name})

    threads = [threading.Thread(target=asker, args=(m,)) for m in ("faber", "vesper")]
    for t in threads:
        t.start()
    for _ in range(200):
        if len(reg.pending()) == 2:
            break
        time.sleep(0.01)

    by_mode = {p["mode"]: p["id"] for p in reg.pending()}
    reg.decide(by_mode["faber"], "allow")
    reg.decide(by_mode["vesper"], "deny")
    for t in threads:
        t.join(timeout=5)

    assert done["faber"].decision == "allow"
    assert done["vesper"].decision == "deny"


# ------------------------------------------------------------------ routes

def test_pending_and_decide_round_trip_over_http(client):
    from permissions import registry
    result = {}

    def asker():
        result["req"] = registry.ask("faber", "Write", {"file_path": "/tmp/a"})

    t = threading.Thread(target=asker)
    t.start()
    for _ in range(200):
        if registry.pending():
            break
        time.sleep(0.01)

    listed = client.get("/v2/sessions/permissions/pending", headers=AUTH).json()["pending"]
    assert len(listed) == 1 and listed[0]["tool"] == "Write"

    r = client.post(f"/v2/sessions/permissions/{listed[0]['id']}/decide",
                    json={"decision": "allow"}, headers=AUTH)
    assert r.status_code == 200
    t.join(timeout=5)
    assert result["req"].decision == "allow"


def test_deciding_an_unknown_request_404s(client):
    r = client.post("/v2/sessions/permissions/ghost/decide",
                    json={"decision": "allow"}, headers=AUTH)
    assert r.status_code == 404


def test_an_invalid_decision_is_refused(client):
    """Only allow and deny. A typo must not be read as one of them."""
    r = client.post("/v2/sessions/permissions/x/decide",
                    json={"decision": "maybe"}, headers=AUTH)
    assert r.status_code == 422


@pytest.mark.parametrize("path", ["/v2/sessions/permissions/pending"])
def test_permission_routes_require_auth(client, path):
    assert client.get(path).status_code in (401, 403)


def test_an_answer_reaches_the_session_that_asked(client):
    """AskUserQuestion is answered by the dialog, not merely permitted.

    Allowing the call without carrying the choice back hands the session its
    own question with no reply in it, which is indistinguishable from never
    having asked -- the bug this path exists to close.
    """
    from permissions import registry
    result = {}

    def asker():
        result["req"] = registry.ask("faber", "AskUserQuestion", {
            "questions": [{"question": "Which way?", "options": [{"label": "Left"}]}],
        })

    t = threading.Thread(target=asker)
    t.start()
    for _ in range(200):
        if registry.pending():
            break
        time.sleep(0.01)

    listed = client.get("/v2/sessions/permissions/pending", headers=AUTH).json()["pending"]
    assert len(listed) == 1 and listed[0]["tool"] == "AskUserQuestion"

    r = client.post(f"/v2/sessions/permissions/{listed[0]['id']}/decide",
                    json={"decision": "allow", "answers": {"Which way?": "Left"}},
                    headers=AUTH)
    assert r.status_code == 200
    t.join(timeout=5)
    assert result["req"].decision == "allow"
    assert result["req"].answers == {"Which way?": "Left"}


def test_an_ordinary_request_carries_no_answers(client):
    """The field is absent for every other tool, rather than an empty dict
    that the MCP layer would then have to distinguish from a real reply."""
    from permissions import registry
    result = {}

    def asker():
        result["req"] = registry.ask("faber", "Bash", {"command": "ls"})

    t = threading.Thread(target=asker)
    t.start()
    for _ in range(200):
        if registry.pending():
            break
        time.sleep(0.01)

    listed = client.get("/v2/sessions/permissions/pending", headers=AUTH).json()["pending"]
    client.post(f"/v2/sessions/permissions/{listed[0]['id']}/decide",
                json={"decision": "allow"}, headers=AUTH)
    t.join(timeout=5)
    assert result["req"].answers is None
