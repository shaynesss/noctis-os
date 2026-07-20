# CLAUDE.md — Noctis OS project overrides

Universal process (Phase 1-4, ship gate, Confusion Protocol, standing rules) is already active globally via `~/.claude/CLAUDE.md` → `build-spine.md`. This file adds only what's specific to *this* project — not a copy of the spine itself, to avoid recreating the two-copy drift the global symlink exists to prevent.

Full spec, with reasoning: `noctis-os/SPEC.md`. If anything here and `SPEC.md` disagree, `SPEC.md` wins — this file is a quick-reference, not the source of truth.

## Stack

FastAPI (stateless, no ORM, no migrations) + React/Vite. Vault (`second-brain/`) is the sole database — every backend endpoint reads/writes it directly on disk, no MCP dependency for the backend itself.

## Hard constraints, every session

- **No secrets in vault writes.** Job contexts and lessons entries included. `.env` stays local, never committed, never mirrored into the vault.
- **Backend auth is mandatory.** Every route needs bearer-token auth + Origin checking — localhost binding alone is not sufficient. Never pass skip-permissions flags for interactive sessions.
- **`assets/characters/`** is the sole source of truth for sprite grid data + render script + generated PNGs. Never duplicate grid data into `frontend/src`.
- **`assets/world/`** is the sole source of truth for the background plate + footing coordinates. Same rule.
- **Model routing is Claude-family only in v1** (`--model` flag, per-mode default + per-job override). No cross-vendor routing — see `wiki/Agent Harnesses.md` for why a model being *available* (e.g. Kimi K3) doesn't make it a safe swap.
- **Shared vault files (`log.md`, `index.md`) go through a single serialized writer** in the backend — never write these directly from multiple sessions in parallel.
- **Sessions run in parallel across modes, not within one job.** A mode is methodology + view focus, not an execution lock.

## Build order (locked)

git for the vault (done) → mode files (`second-brain/modes/<name>.md`, `build-spine.md` → `modes/dev.md`) → backend → frontend tracker → telemetry → nightshift.

## Design tooling (Phase 2, once frontend is scaffolded)

Run the standard kickoff sequence from `wiki/Tooling Decisions.md`'s "Phase 2 kickoff prompt" (Tailwind wiring, path alias, `shadcn init --preset bd1gAd4y --force`, `.mcp.json` for shadcn MCP, `/impeccable init`). Component sourcing beyond that: personal 21st.dev Library first, public shadcn registry second, hand-build anything that fights the pixel-art/world aesthetic.

## Launch surfaces (don't build a live PTY wrapper)

Learn/Research/Settings/Nightshift open macOS Terminal.app (background tinted per character, via `osascript`). Dev opens VS Code (`code <path>` then the Claude Code extension's URI handler). The interface is fire-and-forget — it launches a session and reads back state via hooks/job-context files, it never tries to watch or control a running session live. Full detail: `wiki/Noctis OS/Interface.md`.
