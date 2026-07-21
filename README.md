> **Status: see STATUS.md.** Spec (Definition/PRD/EDD/Design Brief) locked. **v1 shipped, 2026-07-21** — full build order complete (mode folders, backend, frontend tracker, telemetry hooks, nightshift infra, dev job lifecycle), two ship-gate passes run. Everything below actually runs.

# Noctis OS

A local operating system for working with AI — five modes (Dev, Learn, Research, Settings, Nightshift), each a methodology domain with its own stages and subagents, living in a persistent "world" interface where each mode is a clickable character. The vault (`second-brain/`) is the only database. Nothing deploys; this runs on one machine.

Full scoping and design history lives in the vault at `second-brain/wiki/Noctis OS/` (Overview, Modes, Interface, Improvement Loops, Decision Log). This file and `SPEC.md` are the compiled spec artifacts for the build itself.

## What it is, in one line

Modes as spaces with distinct personalities, characters as the way you enter them, and the Obsidian vault as shared ground truth underneath everything.

## Running it

```
make setup     # installs backend + frontend deps, copies .env.example -> .env
make dev       # starts backend (FastAPI, :8000) + frontend (Vite, :5173) together, browser tab
make open-app  # double-click equivalent -- starts both servers, opens the native window
```

Fill in `.env` first (`VAULT_PATH`, `NOCTIS_API_TOKEN`) — see `SETUP.md` for the full one-time machine checklist (Claude Code login, VS Code setting, nightshift's launchd job).

`make open-app` opens `desktop/NoctisOS.app` — a real Dock/Finder-icon app (macOS, pywebview-based), but a thin wrapper around live source, not a frozen build: a code change just needs the app's own Refresh command (Cmd+R, or the "Noctis OS" menu), never a rebuild. `make app` runs the same thing without the bundle, for from-source dev work.

## Current state

Full spec locked, full build order complete: mode folders, FastAPI backend (auth, vault I/O, session launcher, telemetry hooks, dev job lifecycle), React frontend (world screen, profile overlay cards), and nightshift's launchd-scheduled propose-only inbox. See `SPEC.md` for full detail and `STATUS.md` for the live state — what's built, what's smoke-tested, what's still open.

## Where the real process docs live

- `second-brain/wiki/Noctis OS/Overview.md` — architecture decisions, effort estimate, tool evaluations
- `second-brain/wiki/Noctis OS/Modes.md` — all five modes designed in full via the seven-part frame
- `second-brain/wiki/Noctis OS/Decision Log.md` — chronological decision record
- `SPEC.md` (this repo) — the compiled Definition / PRD / EDD / Design Brief
- `STATUS.md` (this repo) — live build state, not aspirational
- `SETUP.md` (this repo) — one-time machine setup checklist
