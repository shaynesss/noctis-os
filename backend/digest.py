"""What happened across Noctis since you were last here, and what is next.

Counted, not written. The morning brief this replaces (2026-09-10 → 09-15)
was a vault file a scheduler was meant to rewrite each morning, with a
paragraph a model wrote over the facts. The scheduler was never built, so the
file said "Thursday 10 September" for five days; and the paragraph was the
one sentence in the app nothing could check -- its prompt was twenty lines of
warnings about the mistakes it made anyway. Here every fact is a count, every
sentence is composed in the shell from the counts, and the whole thing is
computed when the Inbox opens. There is no file and nothing to schedule.

"Since you were last here" has to know when that was. A *sitting* is a run of
presence heartbeats the shell sends while you are at the app -- focused, with
recent input -- and a gap of thirty minutes ends one. The digest reads from
the end of the previous sitting, so it holds still while you are here and
moves on when you come back. Before any gap has ever been seen it reads the
last day.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import vault_io
from orchestrator.store import DATA_DIR, ConversationStore

SITTINGS = DATA_DIR / "sittings.json"
GAP = timedelta(minutes=30)
FIRST_LOOK = timedelta(hours=24)

# Untouched for this long, with a status implying something was concluded
# and not acted on. Two weeks because anything shorter catches work you
# simply have not got back to yet, which is not a decision owed.
STALE_DAYS = 14

# Vault mode folder → the character that runs it. Maintenance is absent on
# purpose: it is the overnight auditor, and its output is the inbox rather
# than a row telling you to go and work in it.
MODE_LABEL = {"dev": "Faber", "research": "Vesper", "learn": "Noctua"}
ROWS = ("Faber", "Vesper", "Noctua")

Git = Callable[..., "str | None"]


# ------------------------------------------------------------- sittings

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def here(path: Path | None = None, now: datetime | None = None) -> dict:
    """One presence heartbeat. A heartbeat more than `GAP` after the last
    one starts a new sitting, and the previous sitting's last heartbeat
    becomes what "since you were last here" means."""
    path = path or SITTINGS       # resolved now, so a test can point it elsewhere
    now = now or _now()
    state = _load(path)
    last = _parse(state.get("current"))
    if last and now - last > GAP:
        state["previous"] = state["current"]
    state["current"] = now.isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")
    return {"since": state.get("previous")}


def since(path: Path | None = None) -> str | None:
    return _load(path or SITTINGS).get("previous")


# ---------------------------------------------------------------- facts

def _age_days(stamp: str) -> int:
    dt = _parse(stamp)
    return (_now().date() - dt.date()).days if dt else 999


def _jobs() -> dict:
    """Open jobs by character, the ones owed a decision, and the project
    directories dev jobs point at -- read from each job's own frontmatter,
    which is the state."""
    per_mode: dict[str, list[dict]] = {label: [] for label in ROWS}
    owed: list[dict] = []
    projects: list[Path] = []
    open_count = on_hold = 0

    for folder in vault_io.list_subdirs("modes"):
        for slug in vault_io.list_subdirs(f"modes/{folder}/jobs"):
            path = f"modes/{folder}/jobs/{slug}/context.md"
            if not vault_io.file_exists(path):
                continue
            try:
                meta, _ = vault_io.read_frontmatter(path)
            except Exception:      # noqa: BLE001 - a bad file is not a crash
                continue
            if str(meta.get("stage", "")).lower() in {"done", "shipped", "resolved"}:
                continue
            status = str(meta.get("status", ""))
            open_count += 1
            if status.lower().startswith("on hold"):
                on_hold += 1
                continue
            job = {
                "name": meta.get("name") or slug,
                "stage": meta.get("stage"),
                "days": _age_days(str(meta.get("last_touched", ""))),
                "mode": MODE_LABEL.get(folder, folder),
            }
            if folder in MODE_LABEL:
                per_mode[MODE_LABEL[folder]].append(job)
            if job["days"] >= STALE_DAYS:
                owed.append(job)
            if folder == "dev" and meta.get("project_path"):
                try:
                    project = Path(str(meta["project_path"])).expanduser().resolve()
                except (OSError, RuntimeError):
                    continue
                if project.is_dir() and project not in projects:
                    projects.append(project)

    for jobs in per_mode.values():
        jobs.sort(key=lambda j: j["days"])          # freshest first: what you would resume
    return {
        "per_mode": per_mode,
        "owed": sorted(owed, key=lambda j: -j["days"])[:3],
        "open": open_count,
        "on_hold": on_hold,
        "projects": projects,
    }


def _sessions(store: ConversationStore, after: datetime) -> list[dict]:
    """Sessions that started after `after` and in which you said something.
    Grouped by mode, busiest first, with up to three titles each -- the
    titles are what "you were in Faber" means.

    The opening prompt Noctis hands a fresh session is stored as a user
    message, and it is not you speaking: a tab opened and closed again
    reported as "Faber ran 1 session -- Start new session" until it was
    left out."""
    from interactive import OPENING_PROMPT

    by_mode: dict[str, dict] = {}
    for row in store.recent_sessions(limit=120):
        started = _parse(row["started_at"])
        if not started or started <= after:
            continue
        said = store.db.execute(
            "SELECT COUNT(*) c FROM messages WHERE session_id=? AND role='user' AND TRIM(content) != ?",
            (row["id"], OPENING_PROMPT.strip())).fetchone()["c"]
        if not said:
            continue
        entry = by_mode.setdefault(row["mode"], {"mode": row["mode"], "count": 0, "titles": []})
        entry["count"] += 1
        if row["title"] and len(entry["titles"]) < 3:
            entry["titles"].append(row["title"])
    return sorted(by_mode.values(), key=lambda e: -e["count"])


def _repos(git: Git, roots: list[Path], after: datetime) -> list[dict]:
    """Each repository's movement: commits since, commits not on the
    upstream, files uncommitted. A directory that is not a repository is
    skipped rather than reported as an empty one."""
    out: list[dict] = []
    for root in roots:
        top = git(root, "rev-parse", "--show-toplevel")
        if not top:
            continue
        branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
        ahead = None
        if git(root, "rev-parse", "--abbrev-ref", "@{u}"):
            count = git(root, "rev-list", "--count", "@{u}..HEAD")
            ahead = int(count) if count and count.isdigit() else None
        log = git(root, "log", f"--since={after.isoformat()}", "--format=%h") or ""
        porcelain = git(root, "status", "--porcelain") or ""
        out.append({
            "name": Path(top).name,
            "branch": None if branch == "HEAD" else branch,
            "commits": len(log.split()),
            "ahead": ahead,
            "dirty": len([l for l in porcelain.splitlines() if l.strip()]),
        })
    return out


def gather(git: Git, since_at: str | None = None, store: ConversationStore | None = None) -> dict:
    """Everything the digest says, as counts. `since_at` defaults to the end
    of the previous sitting; with none recorded yet, the last day."""
    since_at = since() if since_at is None else since_at
    after = _parse(since_at) or (_now() - FIRST_LOOK)
    jobs = _jobs()

    own = store is None
    store = store or ConversationStore()
    try:
        sessions = _sessions(store, after)
    finally:
        if own:
            store.close()

    vault_root = Path(vault_io.get_vault_path())
    roots = [vault_root] + [p for p in jobs["projects"] if p != vault_root]

    # What nightshift did last night, and for how many nights it has been
    # doing the same: the one scheduled thing, whose six weeks of silent
    # failure are why this line exists.
    from nightshift import report

    return {
        "date": datetime.now().strftime("%A %-d %B"),
        "since": since_at,
        "sessions": sessions,
        "repos": _repos(git, roots, after),
        "nightshift": report.summary(),
        "modes": [
            {"label": label,
             "job": jobs["per_mode"][label][0]["name"] if jobs["per_mode"][label] else None,
             "days": jobs["per_mode"][label][0]["days"] if jobs["per_mode"][label] else None,
             "more": max(0, len(jobs["per_mode"][label]) - 1)}
            for label in ROWS
        ],
        "owed": jobs["owed"],
        "open": jobs["open"],
        "on_hold": jobs["on_hold"],
    }
