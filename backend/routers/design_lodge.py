import base64
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

import vault_io

_CODE_SECTION = re.compile(r"## Code\n\n```\n(.*?)\n```", re.DOTALL)
_REFERENCE_SECTION = re.compile(r"## Reference\n\n(.*?)(?=\n\n## |\Z)", re.DOTALL)

router = APIRouter(prefix="/design-lodge", tags=["design-lodge"])

# Vault-level, not per-mode -- Design Lodge is cross-project (every future
# Faber build reads the same shelf), unlike modes/<name>/state.md which is
# scoped to one mode. See noctis-os/SPEC.md's "Design Lodge" EDD section.
INDEX_PATH = "design-lodge/index.md"


def _entries_dir_path(slug: str) -> str:
    return f"design-lodge/entries/{slug}.md"


def _preview_path(slug: str) -> str:
    return f"design-lodge/entries/{slug}.png"


def _with_preview_flag(row: dict) -> dict:
    """Browse view shows a visual preview only by default (locked Design
    Brief decision) -- the frontend needs to know whether to bother
    fetching an image before rendering a thumbnail slot, rather than
    firing a request per entry and handling a 404 every time one has none.
    """
    return {**row, "has_preview": vault_io.file_exists(_preview_path(row["slug"]))}


def _find_entry(entries: list, slug: str) -> dict:
    for entry in entries:
        if entry.get("slug") == slug:
            return entry
    raise HTTPException(status_code=404, detail=f"No Design Lodge entry: {slug}")


def _body_for(code: str, reference: str) -> str:
    """Code and/or reference, whichever fits the entry -- both sections are
    written when both are given rather than forcing a single-field choice
    (locked decision: "whichever's smarter", not a schema toggle).
    """
    parts = []
    if code:
        parts.append(f"## Code\n\n```\n{code}\n```")
    if reference:
        parts.append(f"## Reference\n\n{reference}")
    return "\n\n".join(parts)


def _parse_body_sections(body: str) -> tuple[str, str]:
    """The inverse of _body_for -- needed so a partial PATCH (only `code` or
    only `reference` supplied) can preserve whichever section wasn't
    touched, instead of rebuilding the body from just the fields present on
    that one request and silently dropping the other section.
    """
    code_match = _CODE_SECTION.search(body)
    reference_match = _REFERENCE_SECTION.search(body)
    return (
        code_match.group(1) if code_match else "",
        reference_match.group(1).strip() if reference_match else "",
    )


class EntryCreate(BaseModel):
    slug: str
    name: str
    category: str
    tags: list[str] = []
    source: str = ""
    code: str = ""
    reference: str = ""
    projects_used: list[str] = []


class EntryUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    source: str | None = None
    code: str | None = None
    reference: str | None = None
    projects_used: list[str] | None = None
    superseded_by: str | None = None


class InboxAdd(BaseModel):
    link: str
    note: str = ""


@router.get("/entries")
def list_entries(category: str | None = None, tag: str | None = None):
    """Index rows only -- what the Lodge tab's browse grid renders (preview
    fields, not full code/reference bodies). Matches every mode's own
    state.md-is-the-lightweight-index contract.
    """
    metadata, _ = vault_io.read_frontmatter(INDEX_PATH)
    entries = metadata.get("entries", [])
    if category:
        entries = [e for e in entries if e.get("category") == category]
    if tag:
        entries = [e for e in entries if tag in (e.get("tags") or [])]
    return [_with_preview_flag(e) for e in entries]


@router.get("/entries/{slug}")
def get_entry(slug: str):
    """Full detail -- index row plus the entry file's code/reference body,
    for the browse grid's expand-to-reveal-detail interaction.
    """
    metadata, _ = vault_io.read_frontmatter(INDEX_PATH)
    entry = _find_entry(metadata.get("entries", []), slug)
    body = vault_io.read_file(_entries_dir_path(slug)) if vault_io.file_exists(_entries_dir_path(slug)) else ""
    return {**_with_preview_flag(entry), "body": body}


@router.post("/entries")
def create_entry(entry: EntryCreate):
    if not vault_io.is_safe_slug(entry.slug):
        raise HTTPException(status_code=400, detail=f"Invalid slug: {entry.slug!r}")
    metadata, content = vault_io.read_frontmatter(INDEX_PATH)
    entries = metadata.get("entries", [])
    if any(e.get("slug") == entry.slug for e in entries):
        raise HTTPException(status_code=409, detail=f"Entry already exists: {entry.slug}")

    row = {
        "slug": entry.slug,
        "name": entry.name,
        "category": entry.category,
        "tags": entry.tags,
        "source": entry.source,
        "projects_used": entry.projects_used,
        "superseded_by": None,
    }
    entries.append(row)
    metadata["entries"] = entries
    vault_io.write_frontmatter(INDEX_PATH, metadata, content)
    vault_io.write_frontmatter(_entries_dir_path(entry.slug), row, _body_for(entry.code, entry.reference))
    return row


@router.patch("/entries/{slug}")
def update_entry(slug: str, update: EntryUpdate):
    """Manual full edit -- the free-time path (no dev session required),
    same as the plain add/edit form the Lodge tab itself exposes.
    """
    metadata, content = vault_io.read_frontmatter(INDEX_PATH)
    entries = metadata.get("entries", [])
    entry = _find_entry(entries, slug)

    for field in ("name", "category", "tags", "source", "projects_used", "superseded_by"):
        value = getattr(update, field)
        if value is not None:
            entry[field] = value
    metadata["entries"] = entries
    vault_io.write_frontmatter(INDEX_PATH, metadata, content)

    if update.code is not None or update.reference is not None:
        file_metadata, file_body = vault_io.read_frontmatter(_entries_dir_path(slug))
        file_metadata.update({k: entry[k] for k in ("name", "category", "tags", "source", "projects_used", "superseded_by")})
        existing_code, existing_reference = _parse_body_sections(file_body)
        new_body = _body_for(
            update.code if update.code is not None else existing_code,
            update.reference if update.reference is not None else existing_reference,
        )
        vault_io.write_frontmatter(_entries_dir_path(slug), file_metadata, new_body)
    return entry


@router.get("/inbox")
def list_inbox():
    """Pending quick-capture items -- what the Lodge tab's inbox section
    renders, and what session-bootstrap's opportunistic pass reads.
    """
    metadata, _ = vault_io.read_frontmatter(INDEX_PATH)
    return metadata.get("inbox", [])


@router.post("/inbox")
def add_inbox_item(item: InboxAdd):
    """The whole point of quick-capture is minimal friction -- link + note
    only, no slug/category/tags asked for here. Slug is generated, not
    caller-supplied, since there's nothing meaningful to derive one from at
    capture time.
    """
    metadata, content = vault_io.read_frontmatter(INDEX_PATH)
    inbox = metadata.get("inbox", [])
    slug = f"capture-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    entry = {
        "slug": slug,
        "link": item.link,
        "note": item.note,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    inbox.append(entry)
    metadata["inbox"] = inbox
    vault_io.write_frontmatter(INDEX_PATH, metadata, content)
    return entry


@router.post("/inbox/{slug}/process")
def mark_inbox_processed(slug: str):
    """Removes the item from the pending queue. Deciding code-vs-reference,
    category, and filing the real entry is session-side judgment (visiting
    the link, reading the resource) -- not something this deterministic
    endpoint does; the session calls POST /entries separately, then this.
    """
    metadata, content = vault_io.read_frontmatter(INDEX_PATH)
    inbox = metadata.get("inbox", [])
    if not any(i.get("slug") == slug for i in inbox):
        raise HTTPException(status_code=404, detail=f"No pending inbox item: {slug}")
    metadata["inbox"] = [i for i in inbox if i.get("slug") != slug]
    vault_io.write_frontmatter(INDEX_PATH, metadata, content)
    return {"processed": slug}


class PreviewUpload(BaseModel):
    image_base64: str


@router.post("/entries/{slug}/preview")
def upload_preview(slug: str, upload: PreviewUpload):
    """Browse view is preview-first (locked Design Brief decision) -- an
    entry with code/reference but no image reads as an incomplete catalog
    row, not just a plainer one. Raw base64, no data-URI prefix; the
    frontend strips that before sending.
    """
    metadata, _ = vault_io.read_frontmatter(INDEX_PATH)
    _find_entry(metadata.get("entries", []), slug)
    try:
        image_bytes = base64.b64decode(upload.image_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image data: {exc}") from exc
    vault_io.write_binary(_preview_path(slug), image_bytes)
    return {"slug": slug, "has_preview": True}


@router.get("/entries/{slug}/preview")
def get_preview(slug: str):
    # Unlike every other slug route here, this one had no is_safe_slug check
    # and no _find_entry index lookup -- vault_io's containment check still
    # stops escaping the vault root entirely, but a crafted slug like
    # "../../assets/characters/faber" would still resolve to a real .png
    # elsewhere in the vault and get served back. Caught in ship-gate
    # security review (2026-07-25); fixed the same way create_entry already
    # guards its own slug.
    if not vault_io.is_safe_slug(slug):
        raise HTTPException(status_code=400, detail=f"Invalid slug: {slug!r}")
    path = _preview_path(slug)
    if not vault_io.file_exists(path):
        raise HTTPException(status_code=404, detail=f"No preview image for: {slug}")
    return Response(content=vault_io.read_binary(path), media_type="image/png")
