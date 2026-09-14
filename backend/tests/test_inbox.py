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
