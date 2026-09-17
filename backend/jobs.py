"""Job lookup — which job is this session sitting in, and what does it need to know.

A mode session is launched with a working directory, not a job id. The job
is inferred from that directory: each job context carries a `project_path`
in its frontmatter, and the one matching the session's cwd is the job the
session is about to work on. No new field on the launch request, no picker
to keep in sync, and the mapping is the one the person already made when
they opened that directory.

**This module owns the mode-name → vault-directory mapping.** It had been
inline in `mcp/server.py`, and the moment a second caller needed it the
choice was extract or duplicate. Duplicating it is how the two drift: a
mode renamed in one place and not the other fails by returning "no jobs"
rather than by raising, which reads as an empty backlog instead of a bug.
`mcp/server.py` imports it from here now.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import vault_io

log = logging.getLogger(__name__)

# Mode names are the interface's; vault directories are the methodology's,
# and they predate the rename. `general` is absent deliberately — it has no
# jobs, and mapping it to something would invent a backlog it never has.
MODE_VAULT_DIR = {
    "faber": "dev",
    "noctua": "learn",
    "vesper": "research",
}

# Maintenance is not under `modes/`. Settings and Nightshift collapsed into
# root-level `maintenance/` on 2026-09-07 as infrastructure rather than a
# mode; only the methodology moved then, because v1's pipeline still read the
# old state paths. The state followed at the Stage 2 cutover (2026-09-12) and
# the two MOVED.md markers are gone with it.
#
# Every vault path for it is named here rather than written as a literal at
# each call site. There were eleven such literals across six files, and the
# mapping had already been restated three times and disagreed twice.
MAINTENANCE = "maintenance"
MAINTENANCE_STATE = f"{MAINTENANCE}/state.md"
MAINTENANCE_LESSONS = f"{MAINTENANCE}/lessons.md"


def lessons_path(mode: str) -> str:
    """Where a mode's lessons live, by vault folder name. Maintenance is
    outside `modes/`; the other three are under it."""
    return MAINTENANCE_LESSONS if mode == "maintenance" else f"modes/{mode}/lessons.md"
MAINTENANCE_INBOX = f"{MAINTENANCE}/inbox"
MAINTENANCE_ARCHIVE = f"{MAINTENANCE}/archive"
MAINTENANCE_JOBS = f"{MAINTENANCE}/jobs"

# Vault folder -> where that folder's jobs live. The folders, not the
# character names: this is what reads context files off disk. Maintenance is
# the reason it exists as a map at all, being the one that is not under
# `modes/`, and the reason it is shared: the staleness pass flagged
# maintenance jobs while the Inbox scanned only `modes/*/jobs`, so a flagged
# maintenance job was invisible and could not be cleared (2026-09-17).
JOB_FOLDERS = {
    "dev": "modes/dev/jobs",
    "learn": "modes/learn/jobs",
    "research": "modes/research/jobs",
    "maintenance": MAINTENANCE_JOBS,
}

# The prompt gets orientation, not the archive. A job context grows without
# bound — noctis-os's is already ~20KB of prose — and pasting all of it into
# every launch spends tokens on history the session can fetch when it wants
# it. The tail is what is current, so the tail is what is carried, and the
# `job_context` MCP tool remains there for the whole thing.
BRIEF_MAX_CHARS = 2600


# Where a mode's *methodology* lives, which is not always beside its state.
#
# Ordinarily `modes/<dir>/<dir>.md`. Maintenance is the exception, and after
# the 2026-09-12 cutover it is the exception in both directions: its
# methodology and its state both live at root-level `maintenance/`, outside
# `modes/` entirely, because it is infrastructure rather than a mode.
#
# Stated once, here, because it had been restated three times -- jobs.py,
# orchestrator/modes.py and mcp/server.py each carried a copy, and two of
# them disagreed about maintenance before anything called them.
METHODOLOGY_OVERRIDE = {"maintenance": f"{MAINTENANCE}/audit.md"}


def jobs_dir(mode: str) -> str | None:
    """Vault-relative jobs directory for a mode, or None if it has no jobs."""
    if mode == "maintenance":
        return MAINTENANCE_JOBS
    vault_dir = MODE_VAULT_DIR.get(mode)
    return f"modes/{vault_dir}/jobs" if vault_dir else None


def methodology_path(mode: str) -> str | None:
    """Vault-relative path to a mode's methodology, or None if it has none.

    `general` has none by design: it is the mode without a method.
    """
    if override := METHODOLOGY_OVERRIDE.get(mode):
        return override
    vault_dir = MODE_VAULT_DIR.get(mode)
    return f"modes/{vault_dir}/{vault_dir}.md" if vault_dir else None


def find_job_for_cwd(mode: str, cwd: str | Path) -> str | None:
    """The slug whose `project_path` is the session's working directory.

    Exact directory match after resolution, not a prefix test: a session
    opened in a subdirectory of a project is a deliberate scoping choice,
    and `~/Developer` — which is a parent of every project — would match
    all of them under a prefix rule. Wrong job context is worse than none,
    because none is visibly absent and wrong is quietly believed.
    """
    base = jobs_dir(mode)
    if not base or not cwd:
        return None
    try:
        target = Path(cwd).expanduser().resolve()
    except (OSError, RuntimeError):
        return None

    for slug in vault_io.list_subdirs(base):
        try:
            meta, _ = vault_io.read_frontmatter(f"{base}/{slug}/context.md")
        except (FileNotFoundError, ValueError):
            continue
        project_path = meta.get("project_path")
        if not project_path:
            continue
        try:
            if Path(str(project_path)).expanduser().resolve() == target:
                return slug
        except (OSError, RuntimeError):
            continue
    return None


def job_notes_paths(mode: str, slug: str) -> list[str]:
    """Where a job's planning record lives in the vault: its notes folder
    (`notes_path` in the context frontmatter, `wiki/<name>` by default) and
    its own job folder. The project repo holds what runs and what a
    contributor needs; the spec, briefs and migration records are the
    build's own record and live here -- which is why the Repo view shows
    this side's commits under the project too.
    """
    base = jobs_dir(mode)
    if not base:
        return []
    try:
        meta, _ = vault_io.read_frontmatter(f"{base}/{slug}/context.md")
    except (FileNotFoundError, ValueError):
        return [f"{base}/{slug}"]
    notes = str(meta.get("notes_path") or f"wiki/{meta.get('name') or slug}").strip("/")
    return [notes, f"{base}/{slug}"]


def _git(root: Path, *args: str) -> str | None:
    """One git read, or None. Never raises: a brief is orientation, and a
    session that fails to open because git was slow is worse than a session
    that opens without knowing its branch."""
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def repo_facts(project_path: str | Path) -> list[str]:
    """Branch, unpushed, uncommitted and last commit, read now.

    These four are the facts a resuming session most needs and the ones a
    closing session most often writes into its prose, where they rot: a job
    brief on 2026-09-17 said seventeen commits were unpushed when two were,
    and a session repeated it to the person who could see otherwise. Prose
    written at a session's close is a snapshot; the repository is the fact.
    `deterministic-where-possible` (CLAUDE.md) already covers exactly this
    and had never been pointed at the brief itself.

    Empty list when the path is missing or is not a git repository, so a
    job whose work is not in a repo simply gets no block.
    """
    # Explicitly, before Path touches it: `Path("").resolve()` is the process's
    # own working directory, so a job with no `project_path` would silently be
    # briefed on whatever repository the backend happens to be running from.
    # That is this function's own failure mode, one line from the inside.
    if not str(project_path).strip():
        return []
    try:
        root = Path(str(project_path)).expanduser().resolve()
    except (OSError, RuntimeError):
        return []
    if not root.is_dir() or _git(root, "rev-parse", "--git-dir") is None:
        return []

    facts: list[str] = []
    if branch := _git(root, "rev-parse", "--abbrev-ref", "HEAD"):
        facts.append(f"- branch: `{branch}`")

    # No upstream is a real state, not a failure: a branch that has never
    # been pushed has nothing to count against, and saying "0 unpushed"
    # there would be the same class of lie this function exists to stop.
    ahead = _git(root, "rev-list", "--count", "@{u}..HEAD")
    if ahead is None:
        facts.append("- unpushed: no upstream set for this branch")
    else:
        n = int(ahead) if ahead.isdigit() else 0
        facts.append(f"- unpushed: {n} commit{'' if n == 1 else 's'}"
                     + (" (Shayne pushes, Repo tab)" if n else ""))

    status = _git(root, "status", "--porcelain")
    if status is not None:
        n = len([ln for ln in status.splitlines() if ln.strip()])
        facts.append(f"- uncommitted: {'clean' if not n else f'{n} file' + ('' if n == 1 else 's')}")

    if last := _git(root, "log", "-1", "--format=%h %s (%cr)"):
        facts.append(f"- last commit: {last}")
    return facts


def job_brief(mode: str, cwd: str | Path) -> str | None:
    """Orientation for the job at `cwd`, or None if there isn't one.

    Frontmatter first — stage and status are the two things a session needs
    before it does anything — then the repository as it is right now, then
    the tail of the prose, cut at a paragraph boundary so the block never
    opens mid-sentence.

    The computed block sits above the prose and says so, because the two can
    disagree and the session has to know which wins. See `repo_facts`.
    """
    slug = find_job_for_cwd(mode, cwd)
    if not slug:
        return None
    base = jobs_dir(mode)
    try:
        meta, body = vault_io.read_frontmatter(f"{base}/{slug}/context.md")
    except (FileNotFoundError, ValueError) as exc:
        log.warning("job context unreadable for %s/%s: %s", mode, slug, exc)
        return None

    lines = [f"**{meta.get('name') or slug}** (`{slug}`)"]
    for field in ("stage", "status"):
        if meta.get(field):
            lines.append(f"- {field}: {meta[field]}")
    if meta.get("flagged"):
        lines.append("- flagged: this job was left stale and has not been cleared")

    if facts := repo_facts(meta.get("project_path") or ""):
        lines.append("\n**The repository, read just now.** Where these and the notes "
                     "below disagree, these are true and the notes are out of date.")
        lines += facts

    body = body.strip()
    if body:
        if len(body) > BRIEF_MAX_CHARS:
            body = body[-BRIEF_MAX_CHARS:]
            # Cut forward to a paragraph break so the excerpt starts at the
            # top of an entry rather than halfway through a sentence that
            # reads as though it were the beginning of one.
            split = body.find("\n\n")
            body = body[split + 2:] if split != -1 else body.lstrip()
            lines.append("\n*(most recent entries; call `job_context` for the full record)*")
        lines.append(f"\n{body}")

    return "\n".join(lines)
