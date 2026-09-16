# STATUS.md

Last updated: 2026-09-16

Current state, not aspirational. History lives in [`CHANGELOG.md`](CHANGELOG.md); the reference is [`DOCUMENTATION.md`](DOCUMENTATION.md).

## Current state

**v2 is the daily driver, and the session is a real terminal.** The app hosts the interactive Claude Code CLI in a pseudo-terminal per tab; the `-p` orchestrator that preceded it is deleted. Stage 1 complete; Stage 2 items 1–9 closed, and nothing is left in the build order, the `launchd`-on-wake scheduler that was item 6's last piece was closed on 2026-09-15 rather than built, because the commit log is the record. v1 is gone entirely.

**Verified 2026-09-16 (evening):** 305 backend tests, 73 frontend, `tsc -b` and `cargo check` clean, `make doctor` reporting both halves up, no swallowed hook failures and no capability gap in any mode. A Playwright pass over every rail tab against the running app, and a second with a Faber terminal seeded in this repository, to see the record block, reports no page errors and no console errors. (The day's earlier commit bodies said "tsc clean" while `tsc -b` had seven errors, fixed in this pass; the number in a commit body is a claim, and `make test` is the check.)

v2's premise: the app drives Claude Code as a subprocess rather than calling the API, so it runs on the existing subscription at no marginal cost. The interface is the deliverable, v2 exists to stop Claude Desktop being the entry point.

The spec, the product brief and the PTY migration record live in the vault: `second-brain/wiki/Noctis OS/`.

## What works, end to end

Verified live, not only by tests.

- **Terminal**: the real `claude`, one per tab, in the app's palette. A fresh session opens by saying what it is; sessions survive a reload (the PTY registry outlives the page and reattaches with a replay), resume by engine session id, split into a grid (`⌘⇧-number`; a row to three, then 2×2, 3×2, 3×3), and a split's tabs drag as one bracket.
- **Repo**: the landing view, and the memory: one module per repository the open terminals are in. A lid (name, branch, the terminals' sprites, the GitHub link) and then one anatomy, used twice: the code's block, with its path, the figures (not on GitHub, behind, uncommitted), the uncommitted files, and a Commits fold with the push on its lid; and, for a dev job's project, the record's block under it at `<vault>/wiki/<Project>/`, with the record's own figures and its own commits. A commit opens to its body on click; red and green dots say pushed or not; each wears the sprite of whose work it was, by the transcript that made it. The repositories are read at once, and a revisit paints from the last answer while the fresh one loads. The **push button** runs as you, refuses attribution lines and bodiless commits (dated after 2026-09-17), and asks separately before a force push.
- **Stats**: the 5-hour and 7-day windows, lifetime tokens by kind read from the CLI's own transcripts, a year of activity, and every session's history indexed from those transcripts; `⌘K` searches it.
- **Settings**: the universal prompt and each mode's overlay, edited in the vault in place (uncommitted; Repo commits them); the **regression suite**, thirteen cases run from the card scoped to what an edit affects, each recorded against the prompt it ran on, with live progress and a line saying whether the record is current; and **Maintenance**: nightshift's last run as one sentence, and its proposals with accept/reject.
- **Nightshift**: nightly at 03:00 under `launchd`. Its first step is the staleness pass (a job untouched six hours with no clean session end is flagged in its own context); then the scan, which stages a status note for each flagged job and a distillation draft for each mode with undistilled lessons, into `maintenance/inbox/` where Settings reads. Its first run since the PATH fix, 2026-09-16 03:04, completed and recorded `quiet`.
- **MCP server**: five tools against the real vault, stdio, no third-party dependencies (it imports `retrieval/` and `jobs.py` from beside it), usable from any MCP client; registered at user scope so every session on the machine has `vault_search`.
- **Shell**: Tauri 2, Opt+Space summon, tray, launch-at-login; `⌘T` mode entry, `⌘⇧H` handoff, `⌘W` close, `⌘1–9` focus.
- **Limits**: the 5-hour and 7-day windows in the status bar, and a banner naming any model the engine is refusing, with the message it gave, read from the transcripts and cleared when that model answers again.
- **Telemetry**: hooks attribute actions to a mode and job for hosted sessions; the status line feeds the bar and survives a reload.

## Next

1. **The commit log as memory, in use.** It shipped 2026-09-15 evening; a week of mornings opening on Repo will say whether a commit body's last paragraph is enough to restart from, and whether the push's refusal of bodiless commits (from 2026-09-17) bites at the right moment.
2. **The regression suite ran for the first time on 2026-09-16: 13 of 13 pass**, current against that evening's prompts. What it has not done is fail, so the assertions are unproven in the direction that matters: a deliberately broken prompt would say whether a case can catch anything.
3. **Nightshift's distillation path** has still never executed on a night with undistilled lessons; the first one that does may surface bugs of its own. Watch the Maintenance line.

## Known gaps, accepted

- `busy` has no self-healing path if a `SessionEnd` hook never fires (force-quit, sleep).
- Nightshift's apply has no schema-aware validation of the target file beyond the accept click.
- Commit attribution by transcript matches on the subject line: two commits with one subject both credit the first session that ran it (DOCUMENTATION §21).

## Deploy

Local, single-user, single-machine, by design. Nothing to deploy. `VITE_API_TOKEN` is inlined into the bundle by Vite, acceptable only because the backend binds to localhost and anyone who can read the bundle can already read `.env`, recorded in `.env.example` so it is not copied somewhere it stops being true.
