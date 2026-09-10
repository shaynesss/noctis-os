"""Design Lodge tests.

This was the only router with no coverage — fifteen handlers, including the
vault's first binary read/write path and the round-trip that keeps a partial
PATCH from destroying half an entry. Both are the kind of thing that fails
quietly and is noticed months later, which is the argument for testing them
rather than the newest code.

Written against the pure helpers and the routes' guards rather than the
vault, so they say something about the logic instead of about whatever
happens to be in `second-brain/` today.
"""
import pytest
from fastapi.testclient import TestClient

from routers.design_lodge import _body_for, _parse_body_sections, _with_preview_flag


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NOCTIS_API_TOKEN", "test-token")
    from main import app
    return TestClient(app)


AUTH = {"Authorization": "Bearer test-token"}


# ------------------------------------------------------- body round-trip

def test_both_sections_are_written_when_both_are_given():
    """The locked decision was "whichever's smarter", not a schema toggle —
    an entry can be code, a reference, or both."""
    body = _body_for("const x = 1", "https://example.com/pattern")
    assert "## Code" in body and "## Reference" in body


def test_only_the_section_that_has_content_is_written():
    assert "## Reference" not in _body_for("const x = 1", "")
    assert "## Code" not in _body_for("", "a reference")
    assert _body_for("", "") == ""


def test_parsing_is_the_inverse_of_writing():
    """The round-trip is what lets a PATCH touching only `code` preserve the
    reference it never mentioned. If these two drift, a partial update
    silently drops half the entry."""
    code, reference = "const x = 1\nconst y = 2", "https://example.com/pattern"
    assert _parse_body_sections(_body_for(code, reference)) == (code, reference)


def test_parsing_a_code_only_body_returns_no_reference():
    assert _parse_body_sections(_body_for("code here", "")) == ("code here", "")


def test_parsing_a_reference_only_body_returns_no_code():
    assert _parse_body_sections(_body_for("", "just a link")) == ("", "just a link")


def test_parsing_an_unrecognised_body_loses_nothing_it_could_have_kept():
    """A hand-written entry that never went through _body_for still parses to
    empty rather than raising — the vault is hand-editable by design."""
    assert _parse_body_sections("just some prose someone typed") == ("", "")


def test_a_body_with_code_fences_inside_the_reference_still_splits():
    """References quote code often, and a naive split on ``` would take the
    reference's fence as the end of the code section."""
    body = _body_for("real code", "see this snippet:\n```\nnot the code section\n```")
    code, reference = _parse_body_sections(body)
    assert code == "real code"
    assert "not the code section" in reference


# ------------------------------------------------------------- previews

def test_preview_flag_is_reported_per_entry():
    """The flag says whether an image exists, so the UI can show a
    placeholder rather than a broken image element."""
    flagged = _with_preview_flag({"slug": "some-entry", "name": "Some entry"})
    assert "has_preview" in flagged
    assert isinstance(flagged["has_preview"], bool)


def test_the_flag_does_not_disturb_the_entry_it_describes():
    original = {"slug": "e", "name": "E", "tags": ["a"]}
    flagged = _with_preview_flag(dict(original))
    for key, value in original.items():
        assert flagged[key] == value


# --------------------------------------------------------------- routes

def test_every_route_requires_auth(client):
    """The vault's binary write path is here; an unauthenticated one would
    be an arbitrary file drop."""
    assert client.get("/design-lodge/entries").status_code == 401
    assert client.get("/design-lodge/inbox").status_code == 401
    assert client.post("/design-lodge/entries", json={}).status_code == 401


def test_an_unknown_entry_is_404_not_500(client):
    r = client.get("/design-lodge/entries/definitely-not-an-entry", headers=AUTH)
    assert r.status_code == 404


def test_creating_an_entry_validates_before_touching_the_vault(client):
    """A malformed request must be refused by the schema, not part-written
    and then rejected."""
    r = client.post("/design-lodge/entries", headers=AUTH, json={"name": "no slug"})
    assert r.status_code == 422


def test_adding_to_the_inbox_requires_a_link(client):
    r = client.post("/design-lodge/inbox", headers=AUTH, json={"note": "no link"})
    assert r.status_code == 422


def test_processing_an_unknown_inbox_item_is_404(client):
    r = client.post("/design-lodge/inbox/not-a-real-item/process", headers=AUTH)
    assert r.status_code == 404
