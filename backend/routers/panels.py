"""Inbox, Repo and Settings — the rail panels that are not a terminal.

These read; they do not launch. Anything that starts a session goes through
`sessions_v2.py`, so a panel cannot become a second, quieter way to spend the
5h window.

Nothing here is generated ahead of time: every panel is computed when it
opens. The Repo view is the memory -- the commit log, bodies and all, is
where a piece of work was left -- and Settings carries what arrives
(nightshift's last run, the proposals). A morning brief and then an Inbox
digest preceded that on 2026-09-15; both were summaries of what the
commits already said.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import vault_io
import jobs
from jobs import MAINTENANCE, MAINTENANCE_ARCHIVE, MAINTENANCE_INBOX
from nightshift import apply as proposals
import interactive
from engine import MODE_MODELS

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


@router.get("/nightshift")
def nightshift_last() -> dict:
    """Nightshift's newest recorded run and how many nights in a row have
    ended the same way -- Settings' Maintenance section reads it. Null
    until a run has been recorded."""
    from nightshift import report

    return {"nightshift": report.summary()}


def _flagged_jobs() -> list[dict]:
    """Jobs whose context marks them flagged or stale.

    Read straight from each job's frontmatter rather than a separate index:
    the job file is the state, and an index would be a second thing that can
    disagree with it.
    """
    out: list[dict] = []
    # The same map the staleness pass flags from. Scanning `modes/*` instead
    # missed `maintenance/jobs`, which that pass does flag: a flagged
    # maintenance job was invisible here and unclearable (2026-09-17).
    for mode, jobs_dir in jobs.JOB_FOLDERS.items():
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
                     or proposals._section(body, "## rationale") or "")
        # One section reader, nightshift's, for the listing and the apply
        # pipeline alike; `_summary` flattens for the one-line view.
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
    from orchestrator import jsonl

    # The same transcripts Stats' token counts are summed from, so the two
    # are measurements of one population. Read from the store, the cost
    # covered only the 120 turns the `-p` engine had priced, and printed
    # under counts spanning every turn it read ~20x low against its own
    # tokens.
    life = jsonl.lifetime_tokens_cached()
    return {
        "list_cost": life["list_cost"],
        "turns": life["turns"],
        # How many of those turns the figure covers: all of them, less any
        # whose model the price table does not know. The UI says so when
        # the two differ rather than quietly implying a total.
        "priced_turns": life["priced_turns"],
        "since": life["since"][:10] if life["since"] else None,
        # Stated rather than implied, so the UI has no excuse to render
        # the figure above as a bill.
        "charged": False,
        "basis": "api-list-price",
    }


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


@router.get("/repos")
def repos(cwd: list[str] = Query(min_length=1)) -> dict:
    """What the repositories under the open terminals look like right now,
    local and on GitHub, in one read.

    One `cwd` per open terminal. Terminals are grouped by the repository
    they are in -- two Faber sessions on one project are one repository
    with two terminals, and a third session on another project is a second
    repository -- so the view follows the arrangement rather than the one
    terminal that happens to be showing. A directory in no repository is
    returned under `outside`, in words, not as an error: plenty of useful
    working directories are not repositories.

    Per repository, local first and always: root, branch, upstream, how far
    ahead and behind, what is dirty, the recent commits with the ones GitHub
    has not seen marked. Then GitHub through `gh`, when the remote is there
    and `gh` is signed in: open pull requests with their checks and the
    default branch, open issues. GitHub failing -- offline, no token, a
    remote elsewhere -- leaves `github` null with a reason and the local
    half intact, because the local half is what you are looking at and the
    network half is what you are being told about.

    Read-only by construction. Nothing here pushes, and the one thing this
    view asks a person to do -- push -- it asks in words, because the rule
    that a session never pushes is what keeps a crashed session from
    half-shipping, and a button here would be that power through another
    door.
    """
    groups: dict[Path, list[str]] = {}
    outside: list[str] = []
    for raw in cwd:
        try:
            resolved = _safe_home_dir(raw)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        top = _git(resolved, "rev-parse", "--show-toplevel")
        if not top:
            outside.append(raw)
            continue
        groups.setdefault(Path(top), []).append(raw)
    # Each repository is a dozen git calls; two projects open cost the sum.
    # Read them at once -- subprocesses wait outside the GIL -- so the view
    # costs the slowest repository, not all of them (2026-09-16).
    from concurrent.futures import ThreadPoolExecutor
    roots = list(groups)
    with ThreadPoolExecutor(max_workers=max(1, min(4, len(roots)))) as pool:
        read = list(pool.map(_repo_at, roots))
    return {
        "repos": [{**r, "cwds": groups[root]} for root, r in zip(roots, read)],
        "outside": outside,
    }


def _commits(root: Path, n: int, paths: list[str] | None, unpushed: set[str], rev: str | None = None) -> list[dict]:
    """The last `n` commits, newest first, each with its body: the body is
    the record -- where a piece of work left things -- and the view shows
    it, so a subject-only log would be a list of titles with the memory
    cut off. Records are split on a separator git will not print in a
    message, since a body has newlines of its own. `rev` starts the walk
    at a given commit instead of HEAD."""
    log = _git(root, "log", "-n", str(n), "--format=%H%x1f%h%x1f%s%x1f%ct%x1f%b%x1e",
               *([rev] if rev else []), *(["--", *paths] if paths else [])) or ""
    commits = []
    for record in log.split("\x1e"):
        # Python's strip() counts \x1f as whitespace, so `_git` has already
        # eaten a trailing empty body from the last record: pad rather than
        # demand five fields, or the newest bodiless commit vanishes.
        parts = record.strip("\n").split("\x1f")
        if len(parts) < 4 or not parts[0].strip():
            continue
        parts += [""] * (5 - len(parts))
        full, short, subject, ts, body = parts[:5]
        commits.append({"sha": short, "full": full, "subject": subject, "body": body.strip(),
                        "at": int(ts), "pushed": full not in unpushed})
    return commits


def _repo_at(root: Path, paths: list[str] | None = None) -> dict:
    """A repository's local state. With `paths`, the commits and dirty files
    are those touching them -- how the vault is read as one project's notes
    rather than as the whole vault."""
    # The record is the vault's git, the project is its own; neither waits
    # on the other, so the record's read starts now and is joined at the end
    # (2026-09-16). It needs the project's newest commit only for `trails`.
    notes_read = None
    if paths is None:
        from concurrent.futures import ThreadPoolExecutor
        notes_read = ThreadPoolExecutor(max_workers=1).submit(_project_notes, root)
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
    # By status code, not by column: `_git` strips its output, and a first
    # line of " M path" loses its leading space, so a fixed `l[3:]` cut the
    # first character off the first path -- the view read "rontend/…".
    dirty = [m.group(1) for l in porcelain.splitlines()
             if (m := re.match(r"^\s*[A-Z?!]{1,2}\s+(.+)$", l))]
    if paths:
        dirty = [d for d in dirty if any(d == p or d.startswith(p.rstrip("/") + "/") for p in paths)]
    remote_url = _git(root, "remote", "get-url", "origin")
    slug = _github_slug(remote_url)

    # The last twenty, newest first, each marked with whether the upstream
    # has it -- the honest version of "ahead by 201".
    unpushed: set[str] = set()
    if upstream:
        unpushed = set((_git(root, "rev-list", f"{upstream}..HEAD") or "").split())
    commits = _commits(root, 20, paths, unpushed)
    _mark_commit_modes(root, commits)

    # The GitHub half is not read here. It is three network calls per
    # repository, and with two repositories open the view sat on "Loading…"
    # for three seconds while `git` had answered in a tenth of one. The
    # local half returns at once; the shell asks /repos/github per slug and
    # fills that card in when it arrives.
    reason = None if slug else ("the remote is not on GitHub" if remote_url else "no remote named origin")
    out = {
        "root": str(root), "name": root.name, "branch": branch, "upstream": upstream,
        "ahead": ahead, "behind": behind, "dirty": dirty, "commits": commits,
        "remote": remote_url, "slug": slug, "github_reason": reason,
    }
    if notes_read is not None:
        notes = notes_read.result()
        if notes:
            notes["trails"] = _record_trails(commits[0]["at"] if commits else None, notes["commits"])
        out["notes"] = notes
    return out


def _project_notes(root: Path) -> dict | None:
    """The vault side of a project: commits and uncommitted files under the
    job's notes folder and job folder, read from the vault's repository.

    A build has two commit paths on purpose -- code in the project, the
    record in the vault -- and the second was invisible from the project's
    group. Shown under it, with its own push, so both halves of one piece
    of work are one view. None for a repository no dev job owns, and for
    the vault itself.

    Listed by commit, like the project (2026-09-16). A by-file view was
    tried for a day and put twelve unpushed commits beside three rows,
    because twelve commits had touched one file. `trails` -- how far the
    record's newest commit sits behind the project's -- is set by the
    caller, which has both.
    """
    import jobs
    slug = jobs.find_job_for_cwd("faber", root)
    if not slug:
        return None
    try:
        vault = Path(str(vault_io.get_vault_path())).resolve()
    except Exception:  # noqa: BLE001 -- no vault configured is "no notes", not an error
        return None
    if vault == root.resolve() or not _git(vault, "rev-parse", "--show-toplevel"):
        return None
    paths = jobs.job_notes_paths("faber", slug)
    notes = _repo_at(vault, paths=paths)
    # The record is two sets, united (2026-09-15). Commits touching the
    # job's notes paths, whoever made them; and commits to the vault made
    # from inside this project -- the log entry, the lesson, the job context
    # a build session writes as it goes, which touch shared files and were
    # invisible here under the path rule alone. The second set comes from
    # attribution: each vault commit knows where its author session was.
    root_str = str(root.resolve()).rstrip("/")
    inside = lambda cwd: bool(cwd) and (cwd == root_str or cwd.startswith(root_str + "/"))  # noqa: E731
    unpushed: set[str] = set()
    if notes["upstream"]:
        unpushed = set((_git(vault, "rev-list", f"{notes['upstream']}..HEAD") or "").split())
    recent = _commits(vault, 60, None, unpushed)
    _mark_commit_modes(vault, recent)
    by_path = {c["full"]: c for c in notes["commits"]}
    # Git's own order, newest first -- not a sort by timestamp, which two
    # commits in one second would shuffle. Walk the recent vault log and
    # keep what the record claims; path commits older than that log go on
    # the end, in their own order.
    merged = []
    for c in recent:
        if c["full"] in by_path:
            c["via"] = "path"
        elif inside((c.get("by") or {}).get("cwd")):
            c["via"] = "session"
        else:
            continue
        merged.append(c)
    in_recent = {c["full"] for c in recent}
    for c in notes["commits"]:
        if c["full"] not in in_recent:
            c["via"] = "path"
            merged.append(c)
    notes["commits"] = merged[:20]
    notes["paths"] = paths
    notes["cwds"] = []
    notes["trails"] = None
    # The record's figures are the record's, not the vault's (2026-09-16):
    # "not on GitHub" counts the record's own unpushed commits, the way
    # `dirty` already counts only files under the notes paths. The vault's
    # whole count sat beside a Record fold listing three and read as a
    # contradiction. A push is still the repository's -- git pushes history,
    # not paths -- so the vault's count rides along as `vault_ahead` for the
    # button to say so. Bounded by the sixty-commit window the union reads.
    notes["vault_ahead"] = notes["ahead"]
    if notes["upstream"]:
        notes["ahead"] = sum(1 for c in merged if not c["pushed"])
    return notes


def _record_trails(project_newest_at: int | None, commits: list[dict]) -> dict | None:
    """How far the record trails the code, in seconds: the newest project
    commit against the newest record commit. Positive means the code moved
    after the record last did -- the one fact no commit list shows, and the
    gap the 2026-09-11 lesson found when the record fell a hundred commits
    behind with nothing flagging it. None when either side has no commit.
    """
    if project_newest_at is None or not commits:
        return None
    record_at = commits[0]["at"]
    return {"project_at": project_newest_at, "record_at": record_at, "behind": project_newest_at - record_at}


# full sha -> (looked up at, session row or None). See _mark_commit_modes.
_AUTHOR_CACHE: dict[str, tuple[float, dict | None]] = {}


import threading as _threading

_STORE_LOCK = _threading.Lock()


def _mark_commit_modes(root: Path, commits: list[dict]) -> None:
    """Whose work a commit is.

    A commit carries no session id -- and must not: the no-attribution
    rule keeps trailers out of commit messages. Two things stand in.

    First, ownership. A repository that is a dev job's `project_path` is
    Faber's project, and every commit to it is Faber's work -- whichever
    session or terminal typed the command. That is the vault's own model
    of who does what, and it answers the question the view is asked
    ("whose is this") without guessing from the clock. It also covers the
    case the clock gets wrong: a build session launched into VS Code
    rather than hosted here carries no mode signal, is indexed as General,
    and had its commits to the project marked General.

    Second, for a repository no job owns (the vault), time. History holds
    which sessions ran and when: a commit made while a session was live in
    that directory is marked with that session's mode; failing that, with
    any session live at the moment, since the vault is written from every
    mode's working directory. Two live at once is a guess -- the most
    recently started wins, said here rather than hidden. A commit outside
    every span, made by hand, gets no mark. A session's end is its last
    message and a commit lands moments after the message that made it, so
    a span is stretched ten minutes.
    """
    from datetime import datetime
    import jobs
    from orchestrator.jsonl import mode_for_cwd
    from orchestrator.store import ConversationStore

    # Evidence first (2026-09-15): the session whose transcript ran the
    # commit is its author, whatever was live at the time. A session filed
    # as General from a directory that is a dev job's project is Faber's --
    # the VS Code session that built most of today was one. Each commit
    # also remembers where its author was, which is what lets a project's
    # Record claim the vault commits made from inside it.
    # Built under a lock: repositories are read in parallel now, and two
    # constructors on one fresh database raced the schema script against
    # the WAL pragma ("database is locked").
    with _STORE_LOCK:
        store = ConversationStore()
    try:
        unresolved = []
        now = time.time()
        for c in commits:
            # A commit's author never changes once a transcript claims it,
            # and the lookup is a LIKE over every tool call ever indexed --
            # 25ms a commit, a hundred commits a view, on the landing page,
            # every poll. Hits are kept for the process's life; a miss is
            # retried after a minute, since the transcript that made the
            # commit may simply not be indexed yet.
            hit = _AUTHOR_CACHE.get(c["full"])
            if hit is not None and (hit[1] is not None or now - hit[0] < 60):
                row = hit[1]
            else:
                found = store.session_for_commit(c["subject"])
                row = dict(found) if found is not None else None
                _AUTHOR_CACHE[c["full"]] = (now, row)
            if row is None:
                unresolved.append(c)
                continue
            mode = row["mode"]
            if mode == "general":
                mode = mode_for_cwd(row["cwd"], "general")
            c["mode"] = mode
            c["by"] = {"session": row["id"], "cwd": row["cwd"]}
        if not unresolved:
            return
        # No transcript claims the rest. Ownership next: a dev job's project
        # is Faber's, whichever terminal typed the command.
        if jobs.find_job_for_cwd("faber", root):
            for c in unresolved:
                c["mode"] = "faber"
            return
        commits = unresolved
        rows = store.sessions_in(str(root))
        everywhere = store.sessions_all()
    finally:
        store.close()

    def when(s: str | None) -> float | None:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None

    def spans(source) -> list[tuple[float, float, str]]:
        out = []
        for r in source:
            start = when(r["started_at"])
            if start is None:
                continue
            end = when(r["ended_at"])
            out.append((start, (end + 600) if end is not None else float("inf"), r["mode"]))
        return out

    here, anywhere = spans(rows), spans(everywhere)
    for c in commits:
        for candidates in (here, anywhere):
            hits = [(start, mode) for start, end, mode in candidates if start - 60 <= c["at"] <= end]
            if hits:
                c["mode"] = max(hits)[1]
                break
        else:
            c["mode"] = None


class PushRequest(BaseModel):
    cwd: str = Field(min_length=1)
    force: bool = False


_ATTRIBUTION = re.compile(r"^\s*(Co-Authored-By:|Claude-Session:|.*Generated with \[Claude Code\])", re.I | re.M)

# A commit is the record (2026-09-15): the Repo view is where you read
# where a piece of work left things, so a commit with a subject and no
# body is a title with the memory cut off. The push refuses one -- for
# commits made after the rule was written; the rule cannot reach back and
# demand a body of commits that predate it.
RECORD_RULE_SINCE = 1789603200   # 2026-09-17 00:00 UTC (datetime(2026, 9, 17, tzinfo=utc).timestamp())


def _recordless(root: Path, outgoing: str) -> list[str]:
    """Short shas of outgoing commits, dated after the rule, that have no body."""
    log = _git(root, "log", outgoing, "--format=%h%x1f%ct%x1f%b%x1e", timeout=20) or ""
    bare = []
    for record in log.split("\x1e"):
        parts = record.strip("\n").split("\x1f")
        if len(parts) < 2 or not parts[0].strip():
            continue
        parts += [""] * (3 - len(parts))       # a stripped trailing empty body, as in _commits
        short, ts, body = parts[:3]
        if int(ts) >= RECORD_RULE_SINCE and not body.strip():
            bare.append(short)
    return bare


@router.post("/repos/push")
def repos_push(req: PushRequest) -> dict:
    """Push a repository's branch -- the one action the Repo view performs.

    A session never pushes; the deny rule in permissions.json makes that a
    fact for hosted sessions, and the prompt tells every other session to
    send the person here. This button is that person's hand: it runs `git
    push` as the machine's git identity, which is theirs, through the same
    credential helper a terminal would use.

    Two refusals before anything leaves the machine. **Attribution:** every
    message in the range about to go is read, and one `Co-Authored-By`,
    `Claude-Session` or "Generated with Claude Code" line stops the push
    -- the 2026-09-15 incident was four such lines that had never been
    read before they went. **Divergence:** a rewritten history needs
    `force`, and the view asks for that explicitly; a plain push is never
    turned into a force here. Force is `--force-with-lease`, so a remote
    that moved since the last fetch still refuses.
    """
    try:
        resolved = _safe_home_dir(req.cwd)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    top = _git(resolved, "rev-parse", "--show-toplevel")
    if not top:
        raise HTTPException(status_code=400, detail="not inside a git repository")
    root = Path(top)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch or branch == "HEAD":
        raise HTTPException(status_code=409, detail="detached HEAD: check out a branch first")
    if not _git(root, "remote", "get-url", "origin"):
        raise HTTPException(status_code=409, detail="no remote named origin")
    upstream = _git(root, "rev-parse", "--abbrev-ref", "@{u}")

    outgoing = f"{upstream}..HEAD" if upstream else "HEAD"
    messages = _git(root, "log", outgoing, "--format=%B", timeout=20) or ""
    tainted = len(_ATTRIBUTION.findall(messages))
    if tainted:
        raise HTTPException(status_code=409, detail=(
            f"{tainted} attribution line{'s' if tainted != 1 else ''} (Co-Authored-By / Claude-Session) in the "
            f"commits about to go -- strip them first (scripts/strip_claude_trailers.py); nothing was pushed"))
    bare = _recordless(root, outgoing)
    if bare:
        raise HTTPException(status_code=409, detail=(
            f"{len(bare)} commit{'s' if len(bare) != 1 else ''} with no body ({', '.join(bare[:5])}) -- a commit is the "
            f"record; amend {'it' if len(bare) == 1 else 'them'} with where the work leaves things; nothing was pushed"))

    behind = 0
    if upstream:
        counts = _git(root, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
        if counts:
            behind = int(counts.split()[0])
    if behind and not req.force:
        raise HTTPException(status_code=409, detail=(
            f"origin has {behind} commit{'s' if behind != 1 else ''} this branch does not -- a rewritten history "
            f"needs a force push, which is a separate confirmation; nothing was pushed"))

    args = ["push"]
    if req.force:
        args.append("--force-with-lease")
    if not upstream:
        args.append("-u")
    args += ["origin", branch]
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="git push did not finish in two minutes")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if out.returncode != 0:
        raise HTTPException(status_code=502, detail=(out.stderr or out.stdout or "git push failed").strip()[-600:])
    _GITHUB_CACHE.pop(_github_slug(_git(root, "remote", "get-url", "origin")) or "", None)
    return {"pushed": True, "branch": branch, "force": req.force,
            "as": _git(root, "config", "user.name") or "", "output": (out.stderr or out.stdout).strip()[-600:]}


# What GitHub said about a slug, for a minute. The Repo view re-reads on
# every tab change and every visit; open PRs do not change at that rate,
# and `gh` costs a third of a second per call.
_GITHUB_CACHE: dict[str, tuple[float, dict]] = {}
_GITHUB_TTL = 60.0


@router.get("/repos/github")
def repos_github(slug: str = Query(min_length=3, pattern=r"^[\w.-]+/[\w.-]+$")) -> dict:
    """Open pull requests with a one-word check state, open issues, and the
    repository's visibility and default branch -- through `gh`, when signed
    in. Failing leaves `github` null with a reason that tells "no such
    repository for this account" apart from "could not reach GitHub".

    The three `gh` calls run at once rather than in turn: the answer is the
    slowest of them, not the sum.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    hit = _GITHUB_CACHE.get(slug)
    if hit and time.monotonic() - hit[0] < _GITHUB_TTL:
        return hit[1]

    root = Path.home()
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_view = pool.submit(_gh, root, "repo", "view", slug, "--json", "defaultBranchRef,isPrivate,url")
        f_prs = pool.submit(_gh, root, "pr", "list", "-R", slug, "--json",
                            "number,title,headRefName,isDraft,mergeable,statusCheckRollup,url,updatedAt", "--limit", "20")
        f_issues = pool.submit(_gh, root, "issue", "list", "-R", slug, "--json", "number,title,labels,url,updatedAt", "--limit", "20")
        view, prs, issues = f_view.result(), f_prs.result(), f_issues.result()

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
        # A failure is not cached: the next look should be a fresh one.
        return {"github": None, "reason": reason}

    out = {"github": {
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
    }, "reason": None}
    _GITHUB_CACHE[slug] = (time.monotonic(), out)
    return out


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
    """Write a prompt to the vault. That is the whole save: `system.md` is
    what `~/.claude/CLAUDE.md` links to, and an overlay is composed into the
    argv at the next spawn, so the file on disk is what the next session
    reads. Nothing is rendered -- this used to re-render per-mode config
    dirs that the 2026-09-12 cutover removed, and reported "config dir
    missing" five times per save until 2026-09-15.

    `prompt_id` is matched against the known set rather than joined into a
    path, so it cannot address anything but these files. The vault is not
    committed here: the Repo tab shows the file as uncommitted, which is
    where the commit belongs.
    """
    files = _prompt_files()
    if prompt_id not in files:
        raise HTTPException(status_code=404, detail=f"No such prompt: {prompt_id}")

    vault_io.write_file(files[prompt_id], body.markdown)
    return {"saved": prompt_id, "path": files[prompt_id], "bytes": len(body.markdown.encode("utf-8"))}


@router.get("/regression")
def regression_suite() -> dict:
    """The regression cases with their last results, without running any.

    Reading the suite is free; running it is real sessions on production
    models. Those are different enough that they are different routes -- a
    page that fired the expensive one just by being opened would spend the
    5h window every time you glanced at Settings. `scopes` says how many
    sessions each scope costs, so the button can say it before the click.
    """
    from prompts import regression

    if not vault_io.file_exists("prompts/regression.jsonl"):
        return {"cases": [], "scopes": {}, "path": "prompts/regression.jsonl", "sessions": 0}
    return regression.status()


class RegressionRun(BaseModel):
    # `system`/`all`, a mode, or `rule:<name>` -- what an edit can affect.
    scope: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9:_-]*$")


# One run at a time, in a thread the request returns from at once: the
# cases take twenty to forty seconds each and a request held open for a
# four-minute run would time out in the shell. The shell polls `/status`.
_regression_run: dict = {"running": False, "scope": None, "done": 0, "total": 0, "results": [], "started_at": None}
_regression_lock = threading.Lock()


@router.post("/regression/run")
def regression_run(body: RegressionRun) -> dict:
    """Start running the cases `scope` covers. 409 while a run is going: two
    runs at once would double the sessions and interleave the records."""
    from prompts import regression

    cases = regression.cases_for(body.scope)
    if not cases:
        raise HTTPException(status_code=404, detail=f"No cases in scope {body.scope!r}")
    with _regression_lock:
        if _regression_run["running"]:
            raise HTTPException(status_code=409, detail=f"A run is already going ({_regression_run['scope']})")
        _regression_run.update(running=True, scope=body.scope, done=0, total=len(cases), results=[],
                               started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def landed(r: dict) -> None:
        with _regression_lock:
            _regression_run["done"] += 1
            _regression_run["results"].append({k: r[k] for k in ("id", "mode", "rule", "passed", "why", "attempts")})

    def go() -> None:
        try:
            regression.run(body.scope, on_result=landed)
        finally:
            with _regression_lock:
                _regression_run["running"] = False

    threading.Thread(target=go, name="regression", daemon=True).start()
    return {"started": body.scope, "sessions": len(cases)}


@router.get("/regression/status")
def regression_status() -> dict:
    """Where the current (or last) run is: cases done of total, and each
    result as it landed. Cheap enough to poll every couple of seconds."""
    with _regression_lock:
        return dict(_regression_run)


def _configured_effort(model: str) -> str | None:
    """What the CLI would run this model at if Noctis passed no `--effort`.

    Read from the same `settings.json` a session would, so the launcher's
    chooser opens on the truth: picking the level already shown sends an
    override identical to the default, and changes nothing. A chooser that
    opened on a guess would silently outrank the machine's own setting the
    first time anyone pressed Start.
    """
    import capabilities
    try:
        settings = json.loads((capabilities.config_root() / "settings.json").read_text())
    except (OSError, ValueError):
        return None
    per_model = (settings.get("modelSettings") or {}).get(model) or {}
    level = per_model.get("effortLevel") or settings.get("effortLevel")
    return level if level in interactive.EFFORTS else None


@router.get("/mode-defaults")
def mode_defaults() -> dict:
    """What the launcher fills in for each mode: where it starts, and how
    hard it thinks.

    Noctua, Vesper and Maintenance work across the vault, so they start at
    its root — not in their own `modes/<name>/` folder, which would be
    tidier and worse: the engine scopes reads to the working directory, so a
    Noctua session confined to `modes/learn/` could not read `wiki/`, which
    is most of what there is to learn from.

    General is the front door and starts at the vault too: it used to get
    the last directory used, which was whichever repo Faber had just been
    in, so a question about nothing in particular opened inside noctis-os.

    Faber starts in the projects directory, not in a project. Which project
    is the session's to establish -- a continuation names one, a new build
    has none yet and Setup renames its scratch directory -- so defaulting
    to the last repo used pre-decided that for it. The projects directory
    is `PROJECTS_DIR` when set, `~/Developer/projects` when that exists
    (the 2026-08-29 layout: projects in `projects/`, archived ones under
    `projects/archive/`, Noctis itself at the root as the system), else
    `~/Developer`, else the parent of the last project used, else home.
    """
    from orchestrator.store import ConversationStore

    vault = str(vault_io.get_vault_path())
    store = ConversationStore()
    try:
        recent = store.recent_cwds()
    finally:
        store.close()

    home = Path.home()
    projects = os.environ.get("PROJECTS_DIR")
    if not projects and (home / "Developer" / "projects").is_dir():
        projects = str(home / "Developer" / "projects")
    if not projects and (home / "Developer").is_dir():
        projects = str(home / "Developer")
    if not projects:
        last_project = next((d for d in recent if d != vault), None)
        projects = str(Path(last_project).parent) if last_project else str(home)
    from engine import MODEL_CATALOG
    return {
        # Every model a session may start on, with the level each is already
        # configured to run at: the launcher's effort control follows the
        # model, because that is where the CLI's own setting is keyed.
        "models": [{**m, "effort": _configured_effort(m["id"])} for m in MODEL_CATALOG],
        "mode_model": dict(MODE_MODELS),
        "effort": {mode: _configured_effort(model) for mode, model in MODE_MODELS.items()},
        "dirs": {
            "general": vault,
            "faber": projects,
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


@router.post("/flagged/{mode}/{slug}/acknowledge")
def acknowledge_flag(mode: str, slug: str) -> dict:
    """Clear a job's flag, and record that you cleared it.

    A flag says a session died mid-build. Until 2026-09-17 there was no way
    to say "I know", so a job stayed flagged forever and nightshift wrote a
    note about it every night. Accepting that note archived the note and
    left the flag exactly where it was.

    Two writes, both durable: `flagged` goes false, and
    `flag_acknowledged_at` records when. The staleness pass reads the second
    one, so a job is flagged again only by work that happens *after* the
    acknowledgement, never by the same old timestamp coming round again.
    """
    if not vault_io.is_safe_slug(mode) or not vault_io.is_safe_slug(slug):
        raise HTTPException(status_code=400, detail=f"Invalid job: {mode}/{slug}")
    base = jobs.JOB_FOLDERS.get(mode)
    if not base:
        raise HTTPException(status_code=404, detail=f"No such mode: {mode}")
    context = f"{base}/{slug}/context.md"
    if not vault_io.file_exists(context):
        raise HTTPException(status_code=404, detail=f"No such job: {mode}/{slug}")
    try:
        meta, body = vault_io.read_frontmatter(context)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Cannot read {context}: {exc}")
    if not meta.get("flagged"):
        raise HTTPException(status_code=409, detail=f"{mode}/{slug} is not flagged")
    meta["flagged"] = False
    meta["flag_acknowledged_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    vault_io.write_frontmatter(context, meta, body)
    committed = _commit_vault(f"Acknowledge {mode}/{slug}'s flag", [context])
    return {"acknowledged": f"{mode}/{slug}", "committed": committed}


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


