"""The inbox: what it lists, and what deciding does.

Found live 2026-09-14: titles were slugs (the description lives in
state.md's index, which the listing never read), summaries were cut
mid-word with markdown asterisks in them, an empty template sat in the
queue as "untitled", the rail badge was a hard-coded 3, and accept archived
the proposal without applying its diff.
"""
import vault_io

PROPOSAL = """## Rationale
Faber's stages have no track for a **mid-build** re-route; this names one.

## Diff
--- modes/dev/dev.md
+++ modes/dev/dev.md
@@
- Four phases, unchanged.
+ Four phases, unchanged, plus a Pivot.

## Evidence
- modes/dev/lessons.md, 2026-09-14: the sweep found nine defects.

## Confidence
high -- two records converge.
"""


def _stage(slug="faber-pivot-track-20260914", text=PROPOSAL, index=True):
    vault_io.write_file("modes/dev/dev.md", "# Dev\n\nFour phases, unchanged.\n\nMore.\n")
    vault_io.write_file(f"maintenance/inbox/{slug}.md", text)
    vault_io.write_file("maintenance/inbox/README.md", "# format\n")
    entries = [{"slug": slug, "origin_mode": "dev", "confidence": "high",
                "description": "Faber: a Pivot track for mid-build re-routes",
                "rationale": "Faber has no track for a better path found mid-Build.",
                "staged_at": "2026-09-14T12:00:00+00:00"}] if index else []
    vault_io.write_frontmatter("maintenance/state.md",
                               {"busy": False, "diffs_awaiting_review": len(entries), "inbox": entries, "jobs": []},
                               "\n")


def test_listing_reads_the_index_and_says_what_accepting_does(vault, client, auth_headers):
    _stage()
    vault_io.write_file("maintenance/inbox/untitled.md", "# untitled\n\n**Target:** ``\n")
    items = {i["id"]: i for i in client.get("/v2/inbox", headers=auth_headers).json()["items"]}
    p = items["faber-pivot-track-20260914"]
    assert p["title"] == "Faber: a Pivot track for mid-build re-routes", "the description, not the slug"
    assert p["mode"] == "dev" and p["confidence"] == "high"
    assert p["detail"] == "Faber has no track for a better path found mid-Build."
    assert p["target"] == "modes/dev/dev.md" and p["changes_files"] is True
    assert p["effect"].startswith("Accepting edits Faber's methodology in 1 place")
    assert "Pivot" in p["full"]["diff"] and "sweep" in p["full"]["evidence"]
    assert p["full"]["rationale"].startswith("Faber's stages")
    assert items["untitled"]["kind"] == "unreadable", "an empty template is not a proposal"
    assert "README" not in items


def test_summary_falls_back_to_the_file_and_cuts_at_a_word(vault, client, auth_headers):
    _stage(index=False)
    p = client.get("/v2/inbox", headers=auth_headers).json()["items"][0]
    assert p["title"] == "faber pivot track 20260914"
    assert p["detail"] == "Faber's stages have no track for a mid-build re-route; this names one.", \
        "markdown emphasis stripped from the one-line summary"
    assert p["confidence"] == "high"


def test_accept_applies_the_diff_archives_and_drops_the_index_entry(vault, client, auth_headers):
    _stage()
    r = client.post("/v2/inbox/faber-pivot-track-20260914/accept", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied_to"] == "modes/dev/dev.md"
    assert "plus a Pivot" in vault_io.read_file("modes/dev/dev.md"), "the methodology changed"
    assert vault_io.file_exists("maintenance/archive/faber-pivot-track-20260914.md")
    assert not vault_io.file_exists("maintenance/inbox/faber-pivot-track-20260914.md")
    meta, _ = vault_io.read_frontmatter("maintenance/state.md")
    assert meta["inbox"] == [] and meta["diffs_awaiting_review"] == 0
    assert body["committed"] is False, "the test vault is not a git repo; the decision still stands"
    assert client.get("/v2/inbox", headers=auth_headers).json()["counts"]["proposals"] == 0


def test_a_stale_diff_is_refused_and_the_proposal_stays(vault, client, auth_headers):
    _stage()
    vault_io.write_file("modes/dev/dev.md", "# Dev\n\nThe text moved on.\n")
    r = client.post("/v2/inbox/faber-pivot-track-20260914/accept", headers=auth_headers)
    assert r.status_code == 409 and "old text not found" in r.json()["detail"]
    assert vault_io.file_exists("maintenance/inbox/faber-pivot-track-20260914.md"), "nothing moved"
    meta, _ = vault_io.read_frontmatter("maintenance/state.md")
    assert len(meta["inbox"]) == 1


def test_reject_archives_and_changes_nothing(vault, client, auth_headers):
    _stage()
    r = client.post("/v2/inbox/faber-pivot-track-20260914/reject", headers=auth_headers)
    assert r.status_code == 200 and r.json()["applied_to"] is None
    assert "plus a Pivot" not in vault_io.read_file("modes/dev/dev.md")
    assert vault_io.file_exists("maintenance/archive/faber-pivot-track-20260914.md")
    meta, _ = vault_io.read_frontmatter("maintenance/state.md")
    assert meta["inbox"] == []


def _body_of(text: str, decision="accept", applied="modes/dev/dev.md", closed=None) -> str:
    from routers.panels import _decision_body
    return _decision_body("faber-pivot-track-20260914", decision, text, applied, closed)


def test_a_decision_commit_has_a_body_because_the_push_refuses_one_without(vault):
    """The app is not exempt from its own rule. `_recordless` refuses to push a
    commit dated after 2026-09-17 with no body, and until that day this route
    wrote a subject alone: the rule began at 00:00, two proposals were accepted
    that afternoon, and the push then refused the app's own two commits."""
    body = _body_of(PROPOSAL)
    assert body.strip(), "a decision commit with no body cannot be pushed"
    # The argument survives verbatim; paraphrasing it at the moment of deciding
    # is how the reason gets lost.
    assert "no track for a **mid-build** re-route" in body
    assert "Applied 1 hunk to modes/dev/dev.md." in body
    assert "Leaves" in body and "Next:" in body


def test_a_rejection_keeps_the_argument_it_turned_down(vault):
    body = _body_of(PROPOSAL, decision="reject", applied=None)
    assert "no track for a **mid-build** re-route" in body
    assert "nothing was applied" in body


def test_a_proposal_with_no_diff_says_so_rather_than_claiming_a_change(vault):
    body = _body_of("## Rationale\nA cursor advance, no methodology change.\n",
                    applied=None)
    assert "no diff" in body
    assert "Applied" not in body


def test_the_closed_job_is_named_in_the_body(vault):
    assert "Closed maintenance/address-accumulation-20260917" in _body_of(
        PROPOSAL, closed="maintenance/address-accumulation-20260917")


def test_the_real_commit_passes_the_real_push_check(vault, client, auth_headers):
    """End to end against `_recordless` itself, not a re-implementation of it:
    accept a proposal, then read the commit the route made and run the push's
    own body check over it."""
    import subprocess

    from routers.panels import _recordless
    root = vault_io.get_vault_path()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t.t"],
                 ["config", "user.name", "t"], ["add", "-A"],
                 ["commit", "-q", "-m", "base", "-m", "a body, so the base is clean too"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    # Staged but never committed, which is how nightshift and the MCP
    # `propose` tool leave a proposal: neither commits what it stages.
    _stage()
    assert client.post("/v2/inbox/faber-pivot-track-20260914/accept",
                       headers=auth_headers).json()["committed"] is True

    subject = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%s"],
                             capture_output=True, text=True).stdout.strip()
    assert subject.startswith("Accept faber-pivot-track-20260914")
    assert _recordless(root, "HEAD~1..HEAD") == [], "the push would refuse the app's own commit"


# --- an item can be decided twice in one day, because restaging says so -------

def test_the_same_slug_can_be_decided_again_after_being_restaged(vault, client, auth_headers):
    """A slug carries the date its item was staged, so a proposal rejected
    for a bad diff and redrafted the same day comes back under the name its
    own rejection already holds in the archive. That was a 409, "was already
    decided", which read as a safety check and in practice meant no item
    could be decided twice in one calendar day -- while the rejection's own
    commit body was telling the reader that reopening one means staging it
    again. Found live 2026-09-18, on the first restage the system ever did.
    """
    _stage()
    first = client.post("/v2/inbox/faber-pivot-track-20260914/reject", headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["archived_to"] == "maintenance/archive/faber-pivot-track-20260914.md"

    _stage()   # redrafted, same slug, same day
    second = client.post("/v2/inbox/faber-pivot-track-20260914/accept", headers=auth_headers)

    assert second.status_code == 200
    # The earlier decision is the record and is never written over.
    assert second.json()["archived_to"] == "maintenance/archive/faber-pivot-track-20260914-2.md"
    assert vault_io.file_exists("maintenance/archive/faber-pivot-track-20260914.md")
    assert vault_io.file_exists("maintenance/archive/faber-pivot-track-20260914-2.md")
    assert second.json()["applied_to"] == "modes/dev/dev.md"


def test_deciding_a_proposal_that_is_not_staged_is_a_404(vault, client, auth_headers):
    """What actually catches a double click: the first decision moves the
    staged file to the archive, so the second request finds nothing to
    decide. This is the guard the archive-filename check was mistaken for.
    """
    _stage()
    assert client.post("/v2/inbox/faber-pivot-track-20260914/reject",
                       headers=auth_headers).status_code == 200
    again = client.post("/v2/inbox/faber-pivot-track-20260914/reject", headers=auth_headers)
    assert again.status_code == 404


def test_the_body_names_the_archive_file_the_decision_actually_wrote(vault):
    """The commit body says where the proposal went; on a second decision
    that is the suffixed name, not the one the first decision took."""
    from routers.panels import _decision_body
    body = _decision_body("faber-pivot-track-20260914", "reject", PROPOSAL, None, None,
                          "maintenance/archive/faber-pivot-track-20260914-2.md")
    assert "maintenance/archive/faber-pivot-track-20260914-2.md" in body
    assert "maintenance/archive/faber-pivot-track-20260914.md and" not in body


def test_archive_path_walks_past_every_decision_already_on_record(vault):
    from routers.panels import _archive_path
    assert _archive_path("x-20260918") == "maintenance/archive/x-20260918.md"
    vault_io.write_file("maintenance/archive/x-20260918.md", "first\n")
    assert _archive_path("x-20260918") == "maintenance/archive/x-20260918-2.md"
    vault_io.write_file("maintenance/archive/x-20260918-2.md", "second\n")
    assert _archive_path("x-20260918") == "maintenance/archive/x-20260918-3.md"
