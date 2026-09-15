# STATUS.md

Last updated: 2026-09-15

Current state, not aspirational. History lives in [`CHANGELOG.md`](CHANGELOG.md); the reference is [`DOCUMENTATION.md`](DOCUMENTATION.md).

## Current state

**v2 is the daily driver, and the session is a real terminal.** The app hosts the interactive Claude Code CLI in a pseudo-terminal per tab; the `-p` orchestrator that preceded it is deleted. Stage 1 complete; Stage 2 items 1–5, 7, 8 and 9 closed; item 6 done except its scheduler. v1 is gone entirely.

**Verified 2026-09-15:** 298 backend tests, 67 frontend, `tsc -b` and `cargo check` clean, `make doctor` reporting both halves up and no capability gaps, `npm audit` and `pip-audit` clean. A Playwright pass over every rail tab, the launcher, the palette and the split keys reports no page errors.

v2's premise: the app drives Claude Code as a subprocess rather than calling the API, so it runs on the existing subscription at no marginal cost. The interface is the deliverable — v2 exists to stop Claude Desktop being the entry point.

The spec, the product brief and the PTY migration record live in the vault: `second-brain/wiki/Noctis OS/`.

## What works, end to end

Verified live, not only by tests.

- **Terminal** — the real `claude`, one per tab, in the app's palette. A fresh session opens by saying what it is; sessions survive a reload (the PTY registry outlives the page and reattaches with a replay), resume by engine session id, split into a grid (`⌘⇧-number`; a row to three, then 2×2, 3×2, 3×3), and a split's tabs drag as one bracket.
- **Repo** — one group per repository the open terminals are in; branch, ahead/behind, uncommitted files, the last twenty commits with red/green push dots and the sprite of whose work each is; GitHub's PRs and issues loaded after the local half; a **Record** section showing the vault side of a dev job's project; the **push button**, which runs as you, refuses attribution lines, and asks separately before a force push.
- **Stats** — the 5-hour and 7-day windows, lifetime tokens by kind, a year of activity, and every session's history indexed from the CLI's own transcripts; `⌘K` searches it.
- **Inbox** — first in the rail: the **digest** (what happened across Noctis since your last sitting and what is next — sessions by character, commits and unpushed counts per repository, arrivals, owed decisions — counted, composed into sentences, computed on open), then maintenance proposals as packages with a red/green diff; accepting applies the diff, archives the proposal and commits the vault. Replaced the Brief tab and the worklist on 2026-09-15.
- **Settings** — the universal prompt and each mode's overlay, edited in the vault in place, with the regression suite listed.
- **MCP server** — five tools against the real vault, dependency-free stdio, usable from any MCP client; registered at user scope so every session on the machine has `vault_search`.
- **Shell** — Tauri 2, Opt+Space summon, tray, launch-at-login; `⌘T` mode entry, `⌘⇧H` handoff, `⌘W` close, `⌘1–9` focus.
- **Telemetry** — hooks attribute actions to a mode and job for hosted sessions; the status line feeds the bar and survives a reload.

## Next

1. **The digest, in use.** It shipped 2026-09-15 with sentences tested to the string but read for one sitting; a week of mornings will say whether "since yesterday 23:40" and the next-line are the right facts, and whether the standing line earns its row.
2. **Effort at spawn.** `interactive-args` does not take `--effort`; a terminal session runs at the CLI's default. Should come back as a launcher option and a Settings default.
3. **Running the regression suite from Settings.** The cases are listed with their cost; running them means hosting thirteen sessions and reporting back.
4. **The MCP server travels as three directories.** `mcp/server.py` imports `retrieval/` and `orchestrator/`; "nothing to install" is true, "copy one file" is not. The adoption docs should say so.
5. **The Repo tab's Record section** — review its fold, the whole-vault push it carries, and whether every commit touching a job's `context.md` belongs in it (see the vault's job context for the open questions).

## Known gaps, accepted

- `busy` has no self-healing path if a `SessionEnd` hook never fires (force-quit, sleep).
- Nightshift's apply has no schema-aware validation of the target file beyond the accept click.
- The store's read-modify-write on `settings.md` is not atomic; accepted for a single-user, mostly-sequential app.

## Deploy

Local, single-user, single-machine, by design. Nothing to deploy. `VITE_API_TOKEN` is inlined into the bundle by Vite, acceptable only because the backend binds to localhost and anyone who can read the bundle can already read `.env` — recorded in `.env.example` so it is not copied somewhere it stops being true.
