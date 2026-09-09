"""Brief, Inbox and Settings — the three rail panels that are not Chat.

These read; they do not launch. Anything that starts a session goes through
`sessions_v2.py`, so a panel cannot become a second, quieter way to spend the
5h window.

The brief and worklist are *generated* by the scheduler (spec build order,
item 6), which does not exist yet. This serves them as absent rather than
faking content: a panel that invents a morning brief is worse than one that
says the generator has not run, because the invented one gets believed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

import vault_io
from orchestrator.driver import MODEL_CATALOG, MODE_MODELS, MODE_TOOLS, PERMISSION_CYCLE

router = APIRouter(prefix="/v2", tags=["panels"])

def _safe_frontmatter(path: str) -> dict | None:
    """Frontmatter, or None if the file will not parse.

    Vault files are hand-edited and a YAML scalar containing ": " parses as a
    mapping and raises -- a real file in modes/dev/jobs was failing exactly
    this way. One malformed file must not take down a panel that reads many.
    """
    try:
        meta, _ = vault_io.read_frontmatter(path)
        return meta
    except Exception:  # noqa: BLE001 - any parse failure is the same answer
        return None


BRIEF_PATH = "brief/today.md"
WORKLIST_PATH = "worklist.md"


@router.get("/brief")
def brief() -> dict:
    """Today's brief and the durable worklist, as written in the vault.

    `generated` is false when the file is simply not there. The distinction
    matters: an empty brief and an unwritten one mean different things, and
    only one of them is a problem worth chasing.
    """
    def read(path: str) -> str | None:
        return vault_io.read_file(path) if vault_io.file_exists(path) else None

    brief_md = read(BRIEF_PATH)
    worklist_md = read(WORKLIST_PATH)
    return {
        "brief": {"generated": brief_md is not None, "markdown": brief_md, "path": BRIEF_PATH},
        "worklist": {"generated": worklist_md is not None, "markdown": worklist_md,
                     "path": WORKLIST_PATH},
    }


def _flagged_jobs() -> list[dict]:
    """Jobs whose context marks them flagged or stale.

    Read straight from each job's frontmatter rather than a separate index:
    the job file is the state, and an index would be a second thing that can
    disagree with it.
    """
    out: list[dict] = []
    for mode in vault_io.list_subdirs("modes"):
        jobs_dir = f"modes/{mode}/jobs"
        if not vault_io.file_exists(jobs_dir):
            continue
        for slug in vault_io.list_subdirs(jobs_dir):
            context = f"{jobs_dir}/{slug}/context.md"
            if not vault_io.file_exists(context):
                continue
            meta = _safe_frontmatter(context)
            if meta is None:
                # Malformed frontmatter is itself worth surfacing: a job
                # whose state cannot be read is exactly the stale-and-flagged
                # case the inbox exists for, and raising here would take the
                # whole panel down over one bad file.
                out.append({
                    "id": f"{mode}/{slug}", "kind": "unreadable", "mode": mode,
                    "title": slug, "detail": "context.md frontmatter is not valid YAML",
                    "at": "",
                })
                continue
            # A finished job is not an inbox item however it is flagged.
            # Most of the vault's `flagged: true` jobs are settings work
            # completed in July: including them produced 22 entries, 20 of
            # them long resolved, which is how an inbox stops being read.
            if str(meta.get("stage", "")).lower() in {"done", "shipped", "resolved"}:
                continue
            if not (meta.get("flagged") or str(meta.get("status", "")).lower() == "stale"):
                continue
            out.append({
                "id": f"{mode}/{slug}",
                "kind": "flagged-job",
                "mode": mode,
                "title": meta.get("name") or slug,
                "detail": f"{meta.get('stage', '?')} · {meta.get('status', '?')}",
                "at": str(meta.get("last_touched") or ""),
            })
    return out


def _proposals() -> list[dict]:
    """Maintenance proposals staged for review.

    Maintenance can only propose — the tool policy enforces it at spawn —
    so everything here is waiting on a human decision by construction.
    """
    staged = "modes/nightshift/inbox"
    if not vault_io.file_exists(staged):
        return []
    items: list[dict] = []
    # list_dir already returns stems of *.md, so there is no extension to
    # strip or filter on -- doing either silently matched nothing.
    for slug in vault_io.list_dir(staged):
        # The folder also holds its own README. Listing it as a proposal put
        # a documentation file in a queue of things awaiting a decision.
        if slug.upper() == "README":
            continue
        meta = _safe_frontmatter(f"{staged}/{slug}.md") or {}
        body = ""
        try:
            _, body = vault_io.read_frontmatter(f"{staged}/{slug}.md")
        except Exception:  # noqa: BLE001 - covered by _safe_frontmatter above
            pass
        items.append({
            "id": slug,
            "kind": "proposal",
            "mode": "maintenance",
            "title": meta.get("description") or slug.replace("-", " "),
            "detail": meta.get("rationale") or body.strip().split("\n")[0][:160],
            "at": str(meta.get("staged_at") or ""),
            "confidence": meta.get("confidence"),
        })
    return items


@router.get("/inbox")
def inbox() -> dict:
    """One list across modes: proposals first, then flagged jobs.

    Proposals lead because they are blocked on a decision only the person can
    make, whereas a flagged job is information. Sorting the two together by
    date would bury the actionable half.
    """
    proposals, flagged = _proposals(), _flagged_jobs()
    return {"items": proposals + flagged,
            "counts": {"proposals": len(proposals), "flagged": len(flagged)}}


@router.get("/billing")
def billing() -> dict:
    """What the plan is doing, in the only terms that are true.

    Two different things, deliberately kept apart:

    `list_cost` is what every turn so far would have cost at API list price.
    It is not a charge and never was — the engine reports costBasis "list",
    and a subscription's marginal cost per turn is zero. It answers "what is
    this subscription worth", which is a real question.

    `using_overage` is the one that can mean money. It comes from the
    engine's own rate-limit reporting, and it is the only signal here that
    should ever raise an alarm.
    """
    from orchestrator.store import ConversationStore

    store = ConversationStore()
    try:
        life = store.lifetime_tokens()
        return {
            "list_cost": round(life["list_cost"], 2),
            "turns": life["turns"],
            "since": life["since"],
            # Stated rather than implied, so the UI has no excuse to render
            # the figure above as a bill.
            "charged": False,
            "basis": "api-list-price",
        }
    finally:
        store.close()


@router.get("/recent-dirs")
def recent_dirs() -> dict:
    """Working directories from real session history.

    The launcher used a hardcoded list, which never learned a directory you
    started using and kept offering ones you had abandoned.
    """
    from orchestrator.store import ConversationStore

    store = ConversationStore()
    try:
        return {"dirs": store.recent_cwds()}
    finally:
        store.close()


@router.get("/config")
def config() -> dict:
    """What each mode actually runs — read from the driver, not restated.

    The Settings page shows the values the orchestrator will really use. A
    hand-maintained copy would drift from `driver.py` and quietly start
    describing a system that no longer exists.
    """
    return {
        "modes": [
            {
                "mode": mode,
                "model": model,
                # Empty means the full tool surface. Named explicitly so the
                # page can say "full access" rather than leave a blank that
                # reads as unknown.
                "disallowed": MODE_TOOLS.get(mode, {}).get("disallowed", "").split() or [],
                # Pre-approved at spawn, because a hosted session has nobody
                # to ask. Surfaced so Settings can show what each mode may do
                # without prompting, rather than leaving it implicit.
                "allowed": MODE_TOOLS.get(mode, {}).get("allowed", "").split() or [],
            }
            for mode, model in MODE_MODELS.items()
        ],
        # What a session can be switched to, so the picker and Settings
        # both read the same list the orchestrator validates against.
        "models": MODEL_CATALOG,
        "permission_cycle": list(PERMISSION_CYCLE),
        # The CLI denies anything that would prompt when run with --print,
        # because there is no interactive session to answer. Reported so the
        # UI can say what "ask each time" actually means here instead of
        # implying a prompt that never arrives.
        "prompts_answerable": False,
        # bypassPermissions is a real flag that stays settable, but is
        # deliberately unreachable by tapping a key. Reported so Settings can
        # state that rather than leave its absence looking like an oversight.
        "excluded_from_cycle": ["bypassPermissions"],
    }


@router.get("/vault/doc")
def vault_doc(path: str = Query(min_length=1)) -> dict:
    """One vault markdown document, for the reader.

    Two guards, because `path` comes from a client and lands on a filesystem.

    `resolve_vault_only` rather than vault_io's ordinary resolver: that one
    honours a project-root allowlist which also resolves `noctis-os/.env`,
    the file holding this API's own token. Confirmed by reading it, not
    assumed.

    And markdown only. The vault holds binaries (Design Lodge previews) and a
    reader that will serve any file is a file-exfiltration endpoint wearing a
    document viewer's clothes.
    """
    if not path.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only markdown documents can be read")
    try:
        resolved = vault_io.resolve_vault_only(path)
    except ValueError:
        raise HTTPException(status_code=403, detail="Path escapes the vault")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"No such document: {path}")
    return {"path": path, "markdown": resolved.read_text(encoding="utf-8")}


@router.get("/git")
def git_branch(cwd: str = Query(min_length=1)) -> dict:
    """The current branch for a working directory.

    Its own route rather than a field on something else: it changes when you
    switch branches in a terminal, not when a session does anything, so it
    cannot ride along on session state without going stale.

    Returns branch: null rather than erroring when the directory is not a
    repository — plenty of useful working directories are not, and the status
    bar should simply omit the segment instead of showing a failure.
    """
    try:
        resolved = _safe_home_dir(cwd)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    try:
        out = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return {"branch": None}
    branch = out.stdout.strip()
    return {"branch": branch if out.returncode == 0 and branch else None}


def _safe_home_dir(raw: str) -> Path:
    """A client-supplied directory, confined to home.

    Same rule as the session launcher's `_safe_cwd`, for the same reason:
    this path reaches a subprocess. Resolved before the containment check so
    a symlink cannot smuggle one past it.
    """
    resolved = Path(raw).expanduser().resolve()
    home = Path.home().resolve()
    if resolved != home and home not in resolved.parents:
        raise ValueError("Directory must be inside the home directory")
    return resolved
