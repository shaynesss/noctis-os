# CLAUDE.md — Noctis OS project overrides

Universal process is already active globally via `~/.claude/CLAUDE.md` → `second-brain/modes/dev/dev.md` (Faber, moved from `build-spine.md` 2026-07-20 as part of this project's own mode-folder build-out). This file adds only what's specific to *this* project.

Full spec, with reasoning: `noctis-os/SPEC.md`. If anything here and `SPEC.md` disagree, `SPEC.md` wins. **If a decision gets made about this project anywhere other than in a file both of these read, it doesn't count — write it here or in SPEC.md immediately, not after the fact.** As of 2026-07-20, this includes checking the *wiki* too — several locked decisions sat in the vault for a day without ever reaching `SPEC.md`. Both directions need checking, not just chat-vs-file.

## Stack

FastAPI (stateless, no ORM, no migrations) + React/Vite. Vault (`second-brain/`) is the sole database.

## Dependencies are derived from SPEC.md, never hardcoded

Phase 2 setup installs exactly what `SPEC.md`'s Stack + Design Brief sections declare, plus globally-always-on tools (Impeccable). No shadcn currently — because it isn't declared, not because it's banned. If a future need arises, add it to `SPEC.md` explicitly.

## Version control

Commit as work progresses. Shayne pushes manually. (Matches Portfolio Platform, not Articulation Loop's fully-manual-commits rule.)

## Mode folder structure — every mode is a folder, not a flat file

`second-brain/modes/<name>/` contains:
- `<name>.md` — methodology (the mode file itself)
- `lessons.md` — accumulating retros, appended freely at session close, no gate
- `state.md` — the interface's actual read target for ambient cards (current jobs + statuses as frontmatter)
- `jobs/<slug>/context.md` — per-job durable state (stage/track/status frontmatter + prose)
- `agents/*.md` — this mode's subagent definitions

Hook-driven action-feed logs (high-churn, ephemeral) are **not** vault content — they live in `noctis-os/backend/runtime/`, gitignored.

## Hard constraints, every session

- **No secrets in vault writes**, ever.
- **Backend auth is mandatory** — bearer-token + Origin checking on every route.
- **`assets/characters/`** and **`assets/world/`** are sole sources of truth — never duplicated into `frontend/src`.
- **Model routing: Claude-family only in v1.** See `wiki/Agent Harnesses.md` for why availability ≠ safety.
- **`log.md`/`index.md` go through a single serialized writer.** Per-mode lessons/state/job files don't need this — one writer-type each.
- **Sessions run in parallel across modes, not within one job.**
- **No mode ever rewrites its own or another mode's live methodology file** — lessons accumulate freely, methodology only changes through Custos's staged, evidence-backed diffs.
- **Deterministic-where-possible:** date math, staleness checks, health checks, git commits are backend code, never left to session judgment.

## Build order (locked)

git for the vault (done) → mode folders (methodology + lessons + state + agents) → backend → frontend tracker → telemetry → nightshift.

## Design tooling (Phase 2, once frontend is scaffolded)

Tailwind wiring + path alias. `/impeccable init`, register as **Product** (not Brand). No shadcn step.

## Launch surfaces

Learn/Research/Settings/Nightshift → Terminal.app (tinted per character), launched with `CLAUDE_CONFIG_DIR` set to `noctis-os/backend/launch_config/nondev/` so these sessions get a minimal universal CLAUDE.md instead of Dev's full methodology. Dev → VS Code, no override — reads the default `~/.claude/CLAUDE.md` → `modes/dev/dev.md`. Fire-and-forget — the interface launches and reads back state via hooks/state files, never watches or controls a running session live. Full detail: `wiki/Noctis OS/Interface.md`, `SPEC.md`'s "Mode files + CLAUDE.md migration" section.
