# STATUS.md

Last updated: 2026-09-29

Current state, not aspirational. History lives in [`CHANGELOG.md`](CHANGELOG.md); the reference is [`DOCUMENTATION.md`](DOCUMENTATION.md).

## Current state

**v2 is the daily driver, and the session is a real terminal.** The app hosts the interactive Claude Code CLI in a pseudo-terminal per tab; the `-p` orchestrator that preceded it is deleted. Stage 1 complete; Stage 2 items 1–9 closed, and nothing is left in the build order, the `launchd`-on-wake scheduler that was item 6's last piece was closed on 2026-09-15 rather than built, because the commit log is the record. v1 is gone entirely.

**Audited 2026-09-29.** Seven read-only checks compared every doc's claims with the code, the logs and the live app. Most of what they found is fixed; each fix has a test that fails on the old code. The CHANGELOG's 09-29 entry lists them, and DOCUMENTATION §21 lists what was left and why.

**Verified 2026-09-29:** 462 backend tests, 82 frontend, `tsc -b` and `cargo check` clean, `make doctor` green. Checked live against the running backend: PUT and DELETE preflights answer 200, Stats reads 2.83B lifetime tokens, `history_search` returns past conversations, staleness sees the open Faber jobs as live. *Not re-run: the Playwright pass over the rail tabs, last green 2026-09-16, and the prompt regression suite, whose record is stale against the current prompts.*

v2's premise: the app drives Claude Code as a subprocess rather than calling the API, so it runs on the existing subscription at no marginal cost. The interface is the deliverable, v2 exists to stop Claude Desktop being the entry point.

The spec, the product brief and the PTY migration record live in the vault: `second-brain/wiki/Noctis OS/`.

## What works, end to end

Verified live, not only by tests.

- **Terminal**: the real `claude`, one per tab, in the app's palette. A fresh session opens by saying what it is; sessions survive a reload (the PTY registry outlives the page and reattaches with a replay), resume by engine session id, split into a grid (`⌘⇧-number`; a row to three, then 2×2, 3×2, 3×3), and a split's tabs drag as one bracket. General, Faber, Noctua and Vesper run Opus 5.5 by default; Maintenance runs Haiku 4.5.
- **Repo**: one module per repository the open terminals are in. A lid (name, branch, the terminals' sprites, the GitHub link) and one anatomy, used twice: the code's block (path, figures, uncommitted files, a Commits fold with the push on its lid), and for a dev job's project the record's block at `<vault>/wiki/<Project>/`. A commit opens to its body on click; dots say pushed or not, and a repository with no remote reads as not on GitHub. The **push button** runs as you, fetches first, checks exactly what no remote has, refuses attribution lines (every wording) and bodiless commits dated after 2026-09-17, refuses if it cannot read the commits, and asks separately before a leased force push.
- **Stats**: the 5-hour and 7-day windows, lifetime tokens by kind (one count per reply, deleted conversations excluded), a year of activity by local day, and every session's history indexed from the CLI's transcripts, tool calls named; `⌘K` searches it.
- **Settings**: the universal prompt and each mode's overlay, edited in the vault in place and saved (the save could not reach the backend until 2026-09-29); the **regression suite** in the same block; and **Maintenance**: nightshift's last run as one sentence, and its proposals with accept/reject. Accept refuses a diff that keeps the line it extends and reads the file back before it commits.
- **Nightshift**: nightly at 03:00 under `launchd`, held awake with `caffeinate` on AC power, and a draft the machine slept through retried on waking. Its first step is the staleness pass (a job untouched six hours with no clean session end and no live process is flagged); then the scan, which stages a distillation draft for each mode with undistilled lessons into `maintenance/inbox/`.
- **MCP server**: five tools against the real vault, stdio, no MCP library, run under the backend's venv (it needs python-frontmatter and PyYAML); registered at user scope, so every session on the machine has `vault_search` and `history_search`.
- **Shell**: Tauri 2, Opt+Space summon, tray; `⌘K` search, `⌘T` mode entry, `⌘⇧H` handoff, `⌘W` close, `⌘R` reload and reattach, `⌘1–9` focus, `⌘⇧1–9` split.
- **Limits**: the 5-hour and 7-day windows in the status bar, and a banner naming any model the engine is refusing, with the message it gave, read from the transcripts and cleared when that model answers again in any session.
- **Telemetry**: hooks attribute actions to a mode and job for hosted sessions; the status line feeds the bar and survives a reload. The two telemetry hooks come from a project's own `.claude/settings.local.json`, so they fire only in projects that register them (`second-brain` and `articulation-loop` do not, see DOCUMENTATION §21).
- **The shared-tree guard**: a `PreToolUse` hook refuses whole-tree git commands while another live session is in the same repository, and only then. It reads a command as a shell does, so multi-line commits, `bash -c`, `$(...)` and `cd`/`git -C` into another repository are all judged. It rides in the argv, so every **hosted** session carries it in every project; a session Noctis did not launch does not.

## Next

1. **Accept the staged `dev.md` fix.** Settings → Maintenance holds one proposal: remove the duplicated step 2 of the ship gate, left by the 09-28 accept.
2. **Run the regression suite** from Settings. Its record predates the current prompts, r08 and r09 were tightened on 09-29, and the rest of its cases can barely fail, so a deliberately broken prompt is still the test of whether it can catch anything.
3. **Decide three things the audit left open**: whether to switch on launch at login; whether hosted sessions should stop receiving `system.md` twice (argv and `~/.claude/CLAUDE.md`); and whether to tune retrieval, which scores 78% against its 80% gate.
4. **Tonight's nightshift run** should start at 03:00 BST and its log line should say so; it is the first run since the launchd reload and the sleep retry.

## Known gaps, accepted

- The busy marker is written and cleared but nothing reads it; `SESSION_END` is per mode and job, so one of two sessions on a job ending marks it closed for both.
- Three house rules have no code behind them (no mode rewrites methodology, no secrets in the vault, only Shayne pushes): any session can read the API token and call those routes. Accepted for a local single-user machine.
- Commit attribution by transcript matches on the subject line; a subject with a quote, a backslash or an em dash never matches (DOCUMENTATION §21).

## Deploy

Local, single-user, single-machine, by design. Nothing to deploy. `VITE_API_TOKEN` is inlined into the bundle by Vite, acceptable only because the backend binds to localhost and anyone who can read the bundle can already read `.env`, recorded in `.env.example` so it is not copied somewhere it stops being true.
