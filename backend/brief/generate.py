"""The morning brief — gathered deterministically, written by a session.

Two halves, deliberately separated.

**The facts are computed here.** Which jobs are open, how old they are, what
is waiting in the inbox, where the last session got to. Python reads those;
they are counted, not estimated, and nothing about them is left to a model
that might round 45 days to "about a month" or invent a job that closed in
July.

**The prose is written by a session**, from those facts and nothing else.
That is what makes it read like someone telling you where things stand
rather than like assembled fields — and it is why the awkward parts come out
readable: a job whose status begins "Correction: this job had been marked
Done at 14:11 claiming..." becomes a sentence, instead of being quoted raw
into your morning.

The brief is not a session you enter. It is a file, replaced each morning by
the scheduler, and the Brief panel reads it.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import vault_io
from orchestrator.driver import one_shot
from orchestrator.store import ConversationStore

BRIEF_PATH = "brief/today.md"

# Vault mode folder → the character that runs it. Maintenance is absent on
# purpose: it is the overnight auditor, and its output is the inbox rather
# than a row telling you to go and work in it.
MODE_LABEL = {"dev": "Faber", "research": "Vesper", "learn": "Noctua"}
ROWS = ("Faber", "Vesper", "Noctua")

# Untouched for this long, with a status implying something was concluded
# and not acted on. Two weeks because anything shorter catches work you
# simply have not got back to yet, which is not a decision owed.
STALE_DAYS = 14


def _age(timestamp: str) -> int:
    try:
        started = datetime.fromisoformat(str(timestamp)[:10]).date()
    except ValueError:
        return 999
    return (datetime.now(timezone.utc).date() - started).days


def gather() -> dict:
    """Everything the brief is about, as facts rather than prose."""
    per_mode: dict[str, list[dict]] = {label: [] for label in ROWS}
    owed: list[dict] = []
    on_hold = 0
    open_count = 0

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
                "status": status,
                "days": _age(meta.get("last_touched", "")),
                "mode": MODE_LABEL.get(folder, folder),
            }
            label = MODE_LABEL.get(folder)
            if label:
                per_mode[label].append(job)
            if job["days"] >= STALE_DAYS:
                owed.append(job)

    for jobs in per_mode.values():
        jobs.sort(key=lambda j: j["days"])          # freshest first: what you would resume

    store = ConversationStore()
    try:
        # The last session that was actually in a mode. General is the front
        # door, and "you were last in General" tells you nothing.
        last = next(
            (s for s in store.recent_sessions(limit=25) if s["mode"] != "general"), None,
        )
        last_session = {
            "mode": last["mode"], "title": last["title"],
            # The recap is far closer to what you want at 9am than a job's
            # status field, which is written for a spec.
            "recap": last["recap"], "days": _age(last["started_at"]),
        } if last else None
    finally:
        store.close()

    inbox = _inbox_counts()
    return {
        "date": datetime.now().strftime("%A %-d %B"),
        "per_mode": per_mode,
        "owed": sorted(owed, key=lambda j: -j["days"])[:3],
        "open": open_count,
        "on_hold": on_hold,
        "inbox": inbox,
        "last_session": last_session,
    }


def _inbox_counts() -> dict:
    staged = "modes/nightshift/inbox"
    if not vault_io.file_exists(staged):
        return {"waiting": 0, "empty": 0}
    waiting = empty = 0
    for slug in vault_io.list_dir(staged):
        if slug.upper() == "README":
            continue
        waiting += 1
        body = vault_io.read_file(f"{staged}/{slug}.md")
        # A proposal with no rationale is one nobody can act on, and saying
        # how many there are is the nudge to clear them.
        if "## Rationale" not in body or len(body.strip()) < 60:
            empty += 1
    return {"waiting": waiting, "empty": empty}


PROMPT = """You are writing one person's morning brief. They will read it at 9am and
decide what to do. Below are the facts, already gathered — use only these, invent nothing,
and do not soften a number.

Write exactly two short paragraphs of prose, nothing else. No headings, no bullet points,
no sign-off.

Paragraph one: where they left off. Name the mode and what was in progress, in plain past
tense. If the last session was days ago, say so.

Paragraph two: what is owed a decision, if anything. Rewrite each into one clear clause —
several of these statuses are notes the vault wrote to itself and read badly as-is. If
nothing is owed, say the work is all moving and stop.

Be direct and unhurried. No exclamation marks, no "Good morning", no encouragement.

Dates and times: use only the ages given below, in days. The statuses are notes the vault
wrote to itself and often contain bare clock times like "14:11" with no date — those are
not today and not recent, and saying "this morning" because you saw a clock time is the
one mistake that makes this brief untrustworthy. If you cannot date something from the
days-untouched figure, do not date it at all.

FACTS:
"""


def _facts_for_prompt(facts: dict) -> str:
    lines = [f"Date: {facts['date']}"]
    last = facts["last_session"]
    if last:
        lines.append(
            f"Last mode session: {last['mode']}, {last['days']} days ago, "
            f"titled {last['title']!r}. Recap: {last['recap'] or 'none recorded'}"
        )
    else:
        lines.append("Last mode session: none recorded")

    for label in ROWS:
        jobs = facts["per_mode"][label]
        if not jobs:
            lines.append(f"{label}: nothing open")
        else:
            head = jobs[0]
            extra = f", plus {len(jobs) - 1} other open" if len(jobs) > 1 else ""
            lines.append(
                f"{label}: {head['name']} ({head['stage']}, {head['days']} days since "
                f"touched){extra}. Status: {head['status'][:200]}"
            )

    if facts["owed"]:
        for job in facts["owed"]:
            lines.append(
                f"Owed a decision: {job['name']}, {job['days']} days untouched. "
                f"Status: {job['status'][:280]}"
            )
    else:
        lines.append("Owed a decision: nothing")

    lines.append(
        f"Counts: {facts['open']} jobs open, {facts['on_hold']} on hold, "
        f"{facts['inbox']['waiting']} in the inbox ({facts['inbox']['empty']} empty)"
    )
    return "\n".join(lines)


def render(facts: dict, prose: str) -> str:
    """The file. Prose first, then the rows — the shape that was chosen."""
    out = [f"# {facts['date']}", "", prose.strip(), ""]

    for label in ROWS:
        jobs = facts["per_mode"][label]
        if not jobs:
            out.append(f"- **{label}** — —")
            continue
        head = jobs[0]
        extra = f" · +{len(jobs) - 1}" if len(jobs) > 1 else ""
        out.append(f"- **{label}** — {head['name']}{extra}")

    inbox = facts["inbox"]
    empty = f" · {inbox['empty']} empty" if inbox["empty"] else ""
    out += ["", f"- **Inbox** — {inbox['waiting']} waiting{empty}", ""]
    out.append(
        f"*{facts['open']} jobs open · {facts['on_hold']} on hold · "
        f"generated {datetime.now().strftime('%H:%M')}*"
    )
    return "\n".join(out) + "\n"


async def build() -> str:
    """Gather, write, return the markdown. Does not touch the vault."""
    facts = gather()
    try:
        prose = await one_shot(PROMPT + _facts_for_prompt(facts), timeout=90)
    except Exception:              # noqa: BLE001
        prose = ""
    if not prose.strip():
        # A brief without its prose is still worth having: the rows carry the
        # state, and a missing paragraph is better than a missing brief.
        prose = "_The summary could not be written this morning; the state below still stands._"
    return render(facts, prose)


def write(markdown: str) -> str:
    """Replace today's brief. Day-scoped and read-only by design: it is
    regenerated each morning, so nothing here is worth preserving."""
    vault_io.write_file(BRIEF_PATH, markdown)
    return BRIEF_PATH


def main() -> int:
    print(write(asyncio.run(build())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
