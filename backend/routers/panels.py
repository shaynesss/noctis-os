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

import json
import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import vault_io
from prompts.render import render
from jobs import MAINTENANCE, MAINTENANCE_ARCHIVE, MAINTENANCE_INBOX
from nightshift import apply as proposals
from engine import (EFFORT_CYCLE, MODEL_CATALOG, MODE_MODELS, MODE_TOOLS, PERMISSION_CYCLE)

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


def _section(body: str, heading: str) -> str:
    """The text under a `## Heading`, not the heading itself.

    The inbox read `body.split()[0]` and so displayed "## Rationale" as every
    proposal's summary — the header, while the sentence explaining the
    proposal sat on the line below, unread. Three items all reading
    "## Rationale" is why the panel made no sense.
    """
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower() != f"## {heading}".lower():
            continue
        out = []
        for rest in lines[i + 1:]:
            if rest.startswith("## "):
                break
            out.append(rest)
        return " ".join(" ".join(out).split())
    return ""


MAINTENANCE_STATE = f"{MAINTENANCE}/state.md"


def _inbox_index() -> dict[str, dict]:
    """The index Custos keeps beside the files: `state.md`'s `inbox` array,
    keyed by slug. The proposal file is the content; the index is where the
    one-line description, the rationale and the confidence live, per
    `inbox/README.md` -- so a listing that read only the file's own
    frontmatter (which it does not have) showed slugs for titles."""
    if not vault_io.file_exists(MAINTENANCE_STATE):
        return {}
    meta = _safe_frontmatter(MAINTENANCE_STATE) or {}
    return {str(e.get("slug")): e for e in (meta.get("inbox") or []) if isinstance(e, dict)}


def _plain(text: str) -> str:
    """Markdown emphasis out of a one-line summary: `**probe**` reads as
    asterisks in a plain span."""
    return re.sub(r"[*_`]+", "", text).strip()


def _summary(text: str, limit: int = 320) -> str:
    """A cut at a word, with an ellipsis, rather than mid-word at a byte count
    ("This names that mo")."""
    text = _plain(" ".join(text.split()))
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def _target_of(diff: str) -> str | None:
    match = re.search(r"^--- (.+)$", diff, re.MULTILINE)
    return match.group(1).strip() if match else None


_FILE_NAMES = {
    "modes/dev/dev.md": ("Faber's methodology", "Faber"),
    "modes/learn/learn.md": ("Noctua's methodology", "Noctua"),
    "modes/research/research.md": ("Vesper's methodology", "Vesper"),
    "maintenance/audit.md": ("Custos's own method", "Custos"),
    "maintenance/schedule.md": ("the maintenance schedule", "maintenance"),
}


def _effect(target: str | None, hunks: int) -> str:
    """What accepting does to Noctis, in one sentence. Deterministic from the
    diff, because the person deciding needs the consequence before the
    argument -- and the consequence is a fact about the file, not a claim
    the proposal makes about itself."""
    if not target:
        return "Accepting archives this note. Nothing in Noctis changes."
    name, who = _FILE_NAMES.get(target, (f"`{target}`", None))
    where = f"in {hunks} place{'s' if hunks != 1 else ''}"
    if who:
        return (f"Accepting edits {name} {where} and commits the vault. "
                f"The next {who} session reads the new text; sessions already running do not.")
    if target.startswith("wiki/"):
        return f"Accepting edits the wiki page {name} {where} and commits the vault."
    return f"Accepting edits {name} {where} and commits the vault."


def _proposals() -> list[dict]:
    """Maintenance proposals staged for review.

    Maintenance can only propose — the tool policy enforces it at spawn —
    so everything here is waiting on a human decision by construction.
    Each item carries the decision's consequence (`effect`, `target`) and the
    full read (`full`: rationale, diff, evidence, confidence) so the panel can
    show a summary and open into the whole argument without a second call.
    """
    staged = MAINTENANCE_INBOX
    if not vault_io.file_exists(staged):
        return []
    index = _inbox_index()
    items: list[dict] = []
    # list_dir already returns stems of *.md, so there is no extension to
    # strip or filter on -- doing either silently matched nothing.
    for slug in vault_io.list_dir(staged):
        # The folder also holds its own README. Listing it as a proposal put
        # a documentation file in a queue of things awaiting a decision.
        if slug.upper() == "README":
            continue
        entry = index.get(slug, {})
        meta = _safe_frontmatter(f"{staged}/{slug}.md") or {}
        body = ""
        try:
            _, body = vault_io.read_frontmatter(f"{staged}/{slug}.md")
        except Exception:  # noqa: BLE001 - covered by _safe_frontmatter above
            pass
        rationale = (entry.get("rationale") or meta.get("rationale")
                     or _section(body, "Rationale"))
        # Raw, line-preserving reads for the diff and the full text --
        # `_section` above flattens to one line for a summary, which turns a
        # diff header into "modes/dev/dev.md +++ modes/dev/dev.md @@ …".
        raw = lambda h: (proposals._section(body, f"## {h}") or "").strip()  # noqa: E731
        diff = raw("diff")
        has_diff = bool(diff) and "none" not in diff.lower()[:20]
        if not rationale and not has_diff:
            # A file with neither an argument nor a change is not a proposal;
            # an empty template was sitting in the queue as "untitled".
            items.append({"id": slug, "kind": "unreadable", "mode": "maintenance",
                          "title": slug, "detail": "no rationale and no diff -- not a proposal",
                          "at": ""})
            continue
        target = _target_of(diff) if has_diff else None
        hunks = len(proposals._hunks(diff)) if has_diff else 0
        confidence = entry.get("confidence") or meta.get("confidence") or \
            (raw("confidence").split("--")[0].split("—")[0].strip().lower() or None)
        items.append({
            "id": slug,
            "kind": "proposal",
            "mode": entry.get("origin_mode") or "maintenance",
            "title": entry.get("description") or meta.get("description") or slug.replace("-", " "),
            "detail": _summary(rationale),
            # Whether accepting it would change a file, which is the first
            # thing you need to know before deciding. Several proposals are
            # status surfacing and change nothing at all.
            "changes_files": has_diff,
            "target": target,
            "effect": _effect(target, hunks),
            "at": str(entry.get("staged_at") or meta.get("staged_at") or ""),
            "confidence": confidence,
            "full": {
                "rationale": raw("rationale"),
                "diff": diff if has_diff else "",
                "evidence": raw("evidence"),
                "confidence": raw("confidence"),
            },
        })
    return items


@router.post("/brief/generate")
async def generate_brief() -> dict:
    """Write today's brief now.

    The scheduler calls this each morning; the Brief panel offers it so you
    can refresh after changing something rather than waiting until tomorrow
    to see the effect. It costs one cheap-tier call.
    """
    from brief.generate import build, write

    markdown = await build()
    return {"path": write(markdown), "bytes": len(markdown)}


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
            # How many of those turns the figure actually covers. Turns
            # recorded before the column existed carry a zero, so a cost
            # summed over them and token counts summed over all of them are
            # measurements of different populations -- and printing the two
            # side by side made the cost read ~20x low against its own
            # tokens. The UI needs this to say what it is quoting.
            "priced_turns": life["priced_turns"] or 0,
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
        # What the composer's chip cycles through now. It set the permission
        # mode until every mode came to spawn with the same tools and one
        # shared allowlist -- at which point that chip governed almost nothing
        # a person would notice, while this governs the answer. dev.md has
        # asked for the routing since it was written and nothing passed it.
        "effort_cycle": list(EFFORT_CYCLE),
        # Real and settable, deliberately not reachable by tapping a key --
        # the same treatment bypassPermissions gets below.
        "effort_excluded": ["max"],
        # True since the permission prompt tool landed: a request now reaches
        # a dialog in this window and waits for an answer, so "ask each time"
        # asks. It was False because --print has no interactive session, which
        # made every prompt an automatic refusal -- the UI said so rather than
        # implying a dialog that never arrived.
        "prompts_answerable": True,
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


def _git(root: Path, *args: str, timeout: float = 5) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _gh(root: Path, *args: str) -> list | dict | None:
    """One `gh` call, or None when gh is absent, unauthenticated, offline or
    the remote is not on GitHub. The panel says which; it never fails over
    the network half when the local half is fine."""
    try:
        out = subprocess.run(["gh", *args], cwd=str(root), capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout or "null")
    except json.JSONDecodeError:
        return None


def _github_slug(remote_url: str | None) -> str | None:
    if not remote_url:
        return None
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote_url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


@router.get("/repo")
def repo(cwd: str = Query(min_length=1)) -> dict:
    """What a working directory's repository looks like right now, local and
    on GitHub, in one read.

    The visualiser's data. Local first and always: root, branch, upstream,
    how far ahead and behind, what is dirty, the recent commits with the
    ones GitHub has not seen marked. Then GitHub through `gh`, when the
    remote is there and `gh` is signed in: open pull requests with their
    checks and the default branch, open issues. GitHub failing -- offline,
    no token, a remote elsewhere -- leaves `github` null with a reason and
    the local half intact, because the local half is what you are looking
    at and the network half is what you are being told about.

    Read-only by construction. Nothing here pushes, and the one thing this
    view asks a person to do -- push -- it asks in words, because the rule
    that a session never pushes is what keeps a crashed session from
    half-shipping, and a button here would be that power through another
    door.
    """
    try:
        resolved = _safe_home_dir(cwd)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    top = _git(resolved, "rev-parse", "--show-toplevel")
    if not top:
        return {"repo": None}
    root = Path(top)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        branch = None  # detached: git's name for "no branch" is not a branch name
    upstream = _git(root, "rev-parse", "--abbrev-ref", "@{u}")
    ahead = behind = None
    if upstream:
        counts = _git(root, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
        if counts:
            b, a = counts.split()
            ahead, behind = int(a), int(b)
    porcelain = _git(root, "status", "--porcelain") or ""
    dirty = [l[3:] for l in porcelain.splitlines() if l.strip()]
    remote_url = _git(root, "remote", "get-url", "origin")
    slug = _github_slug(remote_url)

    # The last twenty, newest first, each marked with whether the upstream
    # has it -- the honest version of "ahead by 201".
    unpushed: set[str] = set()
    if upstream:
        unpushed = set((_git(root, "rev-list", f"{upstream}..HEAD") or "").split())
    log = _git(root, "log", "-n", "20", "--format=%H%x1f%h%x1f%s%x1f%ct") or ""
    commits = []
    for line in log.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        full, short, subject, ts = parts
        commits.append({"sha": short, "subject": subject, "at": int(ts), "pushed": full not in unpushed})

    github: dict | None = None
    reason: str | None = None
    if not slug:
        reason = "the remote is not on GitHub" if remote_url else "no remote named origin"
    else:
        view = _gh(root, "repo", "view", slug, "--json", "defaultBranchRef,isPrivate,url")
        if not isinstance(view, dict):
            # Two different absences. `gh` answering for the account but not
            # for this slug means the repository is not there, or not this
            # account's to see -- a remote pointing at a repo that was never
            # created, renamed, or made private under another login. The
            # probe reported both as "could not reach GitHub", which sends
            # a person to check their network when they should check the
            # remote.
            who = _gh(root, "api", "user", "--jq", "{login: .login}")
            if isinstance(who, dict) and who.get("login"):
                reason = (f"GitHub has no repository at {slug} that {who['login']} can see -- "
                          f"check the remote (`git remote -v`) or create it (`gh repo create`)")
            else:
                reason = "gh could not reach GitHub (not signed in, offline, or gh is not installed)"
        else:
            prs = _gh(root, "pr", "list", "-R", slug, "--json",
                      "number,title,headRefName,isDraft,mergeable,statusCheckRollup,url,updatedAt", "--limit", "20")
            issues = _gh(root, "issue", "list", "-R", slug, "--json", "number,title,labels,url,updatedAt", "--limit", "20")
            github = {
                "slug": slug,
                "url": view.get("url"),
                "private": bool(view.get("isPrivate")),
                "default_branch": (view.get("defaultBranchRef") or {}).get("name"),
                "pull_requests": [
                    {"number": p["number"], "title": p["title"], "branch": p.get("headRefName"),
                     "draft": bool(p.get("isDraft")), "mergeable": p.get("mergeable"), "url": p.get("url"),
                     # One word from many checks: the panel shows a state, not a list.
                     "checks": _rollup(p.get("statusCheckRollup") or [])}
                    for p in (prs or []) if isinstance(p, dict)
                ],
                "issues": [
                    {"number": i["number"], "title": i["title"], "url": i.get("url"),
                     "labels": [l.get("name") for l in (i.get("labels") or []) if isinstance(l, dict)]}
                    for i in (issues or []) if isinstance(i, dict)
                ],
            }

    return {
        "repo": {
            "root": str(root), "name": root.name, "branch": branch, "upstream": upstream,
            "ahead": ahead, "behind": behind, "dirty": dirty, "commits": commits,
            "remote": remote_url, "github": github, "github_reason": reason,
        },
    }


def _rollup(checks: list) -> str | None:
    """pass / fail / pending / none from a PR's check list."""
    if not checks:
        return None
    states = {str(c.get("conclusion") or c.get("state") or "").upper() for c in checks if isinstance(c, dict)}
    if any(s in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"} for s in states):
        return "fail"
    if any(s in {"PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", ""} for s in states):
        return "pending"
    return "pass"


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


# The prompt files, and nothing else. A prompt editor that can open any vault
# path is a vault editor with a narrow label; naming the four files it may
# touch is what keeps it the thing it claims to be.
def _prompt_files() -> dict[str, str]:
    files = {"system": "prompts/system.md"}
    for mode in sorted(MODE_MODELS):
        files[mode] = f"prompts/overlays/{mode}.md"
    return files


@router.get("/prompts")
def list_prompts() -> dict:
    """The system prompt and each mode's overlay."""
    return {
        "prompts": [
            {"id": key, "path": path,
             "markdown": vault_io.read_file(path) if vault_io.file_exists(path) else None}
            for key, path in _prompt_files().items()
        ]
    }


class PromptUpdate(BaseModel):
    markdown: str = Field(min_length=1)


@router.put("/prompts/{prompt_id}")
def save_prompt(prompt_id: str, body: PromptUpdate) -> dict:
    """Write a prompt and re-render the config dirs that use it.

    Re-rendering here rather than at next launch is the point: an edit that
    only takes effect the next time a session starts is an edit you cannot
    check, and the whole reason to edit prompts in the app is a short loop
    between changing one and running the regression suite against it.

    `prompt_id` is matched against the known set rather than joined into a
    path, so it cannot address anything but these files.
    """
    files = _prompt_files()
    if prompt_id not in files:
        raise HTTPException(status_code=404, detail=f"No such prompt: {prompt_id}")

    vault_io.write_file(files[prompt_id], body.markdown)

    # The system prompt is composed into every mode; an overlay into one.
    affected = sorted(MODE_MODELS) if prompt_id == "system" else [prompt_id]
    rendered = []
    for mode in affected:
        changed, message = render(mode)
        rendered.append({"mode": mode, "changed": changed, "message": message})
    return {"saved": prompt_id, "rendered": rendered}


@router.get("/regression")
def regression_suite() -> dict:
    """The regression cases, without running any of them.

    Reading the suite is free; running it is thirteen real sessions on
    production models. Those are different enough that they are different
    routes — a page that fires the expensive one just by being opened would
    spend the 5h window every time you glanced at Settings.
    """
    import json

    path = "prompts/regression.jsonl"
    if not vault_io.file_exists(path):
        return {"cases": [], "path": path}

    cases = []
    for line in vault_io.read_file(path).splitlines():
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except ValueError:
            continue
        cases.append({
            "id": case.get("id"),
            "mode": case.get("mode"),
            "prompt": case.get("prompt"),
            "tests": case.get("tests"),
        })
    return {"cases": cases, "path": path,
            # What running it will actually cost, stated before you press it.
            "sessions": len(cases)}


@router.get("/mode-dirs")
def mode_dirs() -> dict:
    """Where each mode should start, when you have not said otherwise.

    Noctua, Vesper and Maintenance work across the vault, so they start at
    its root — not in their own `modes/<name>/` folder, which would be
    tidier and worse: the engine scopes reads to the working directory, so a
    Noctua session confined to `modes/learn/` could not read `wiki/`, which
    is most of what there is to learn from.

    Faber and General get the last directory actually used, because a build
    session belongs in a repo and which repo is a thing only history knows.
    """
    from orchestrator.store import ConversationStore

    vault = str(vault_io.get_vault_path())
    store = ConversationStore()
    try:
        recent = store.recent_cwds()
    finally:
        store.close()

    last = recent[0] if recent else str(Path.home())
    return {
        "dirs": {
            "general": last,
            "faber": next((d for d in recent if d != vault), last),
            "noctua": vault,
            "vesper": vault,
            "maintenance": vault,
        }
    }


def _drop_index_entry(slug: str) -> None:
    """The index entry goes with the file. `diffs_awaiting_review` and the
    rail badge both read the live `inbox` array, so a decided item left in it
    is an item that never leaves the count."""
    if not vault_io.file_exists(MAINTENANCE_STATE):
        return
    try:
        meta, body = vault_io.read_frontmatter(MAINTENANCE_STATE)
    except Exception:  # noqa: BLE001 - a malformed index must not block the decision
        return
    inbox = [e for e in (meta.get("inbox") or []) if not (isinstance(e, dict) and e.get("slug") == slug)]
    meta["inbox"] = inbox
    meta["diffs_awaiting_review"] = len(inbox)
    vault_io.write_frontmatter(MAINTENANCE_STATE, meta, body)


def _commit_vault(message: str, paths: list[str]) -> bool:
    """A decision is a commit. The vault is a git repo and applying a diff is
    deterministic backend work (`audit.md`, "Apply + verify"); leaving the
    result uncommitted would make the next session's `git status` the only
    record that anything was decided. Never pushes. Returns False rather than
    failing the decision when git itself cannot run."""
    root = vault_io.get_vault_path()
    try:
        subprocess.run(["git", "-C", str(root), "add", "-A", "--", *paths],
                       check=True, capture_output=True, timeout=20)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", message],
                       check=True, capture_output=True, timeout=20)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


@router.post("/inbox/{item_id}/{decision}")
def decide(item_id: str, decision: str) -> dict:
    """Accept or reject a staged proposal.

    An inbox you cannot dispatch is a report. This one showed three items
    and offered nothing to do about them, so the only way to clear it was to
    go and move files by hand — which is why it stopped being read.

    **Accepting applies the diff.** A previous version archived without
    applying, on the argument that maintenance proposes and never edits and
    a route that applied would be that power through another door. That
    inverted the design: the guarantee is that *maintenance* never edits;
    the person accepting is the edit, and `audit.md`'s Apply + verify stage
    names this route as where it happens — deterministic backend work, not
    session judgment. So: apply (all hunks or none, `apply.py`), honour the
    markers a proposal may carry (a lessons cursor to advance, a job to
    close), archive, drop the index entry, commit the vault. A diff that no
    longer applies -- the target moved on -- is a 409 with the reason, and
    nothing is moved: the proposal stays in the queue, visibly stale.

    Rejecting archives, drops the index entry and commits, so a rejection is
    on the record too.
    """
    if decision not in {"accept", "reject"}:
        raise HTTPException(status_code=400, detail="Decision is accept or reject")
    if not vault_io.is_safe_slug(item_id):
        raise HTTPException(status_code=400, detail=f"Invalid item: {item_id!r}")

    staged = f"{MAINTENANCE_INBOX}/{item_id}.md"
    if not vault_io.file_exists(staged):
        raise HTTPException(status_code=404, detail=f"No such proposal: {item_id}")

    archive = f"{MAINTENANCE_ARCHIVE}/{item_id}.md"
    if vault_io.file_exists(archive):
        raise HTTPException(status_code=409, detail=f"{item_id} was already decided")

    applied: str | None = None
    closed: str | None = None
    if decision == "accept":
        text = vault_io.read_file(staged)
        try:
            applied = proposals.apply_proposal(text)
        except proposals.DiffApplyError as exc:
            raise HTTPException(status_code=409, detail=f"Could not apply: {exc}")
        if mode := proposals.parse_cursor_advance(text):
            proposals.advance_lessons_cursor(mode)
        origin = proposals.parse_job_origin(text)
        if origin:
            job_mode, job_slug = origin
            proposals.close_job(job_mode, job_slug,
                                f"Resolved: {item_id} accepted and applied to {applied or 'nothing'}.")
            closed = f"{job_mode}/{job_slug}"

    vault_io.move_file(staged, archive)
    _drop_index_entry(item_id)
    touched = [staged, archive, MAINTENANCE_STATE] + ([applied] if applied else [])
    committed = _commit_vault(
        f"{'Accept' if decision == 'accept' else 'Reject'} {item_id}"
        + (f": applied to {applied}" if applied else ""), touched)
    return {"item": item_id, "decision": decision, "archived_to": archive,
            "applied_to": applied, "closed_job": closed, "committed": committed}


class WorklistUpdate(BaseModel):
    # Required, with no default. It defaulted to "", which meant a request
    # that simply omitted the field truncated the worklist and returned 200 --
    # silent data loss on the one file here that is hand-kept rather than
    # derived, and so the only one that cannot be regenerated. Clearing it on
    # purpose still works: `{"markdown": ""}` says so, and `{}` no longer
    # says anything at all.
    markdown: str


@router.put("/worklist")
def save_worklist(body: WorklistUpdate) -> dict:
    """Write the worklist.

    The one file here that is yours rather than derived — a hand-kept note of
    what to get done, not generated from mode state, because a generated one
    is the job list again under a second name and the two would disagree the
    moment either drifted.

    A fixed path, so nothing about it is caller-controlled: this writes into
    the vault, and the only safe version of that is a route that can write
    exactly one file.
    """
    vault_io.write_file(WORKLIST_PATH, body.markdown)
    return {"path": WORKLIST_PATH, "bytes": len(body.markdown)}
