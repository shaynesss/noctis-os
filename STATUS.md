# STATUS.md

Last updated: 2026-07-21

## Current state

Phase 1 and Phase 2 both complete. Repo scaffolded, `make setup`/`make dev` verified. Pushed to `origin/main`. Phase 3 underway — mode-folder build-out, backend, frontend tracker, and telemetry hooks milestones all done and smoke-tested live; nightshift infra is next.

## Locked (full detail in SPEC.md + wiki/Noctis OS/)

- Five-mode architecture, harness framing, stateless FastAPI + React/Vite + direct vault filesystem access
- Full mode-folder structure: `second-brain/modes/<name>/{<name>.md, lessons.md, state.md, jobs/, agents/}`
- Profile overlay card system, world backdrop, character sprite sheet — all delivered as real assets
- Session launch surfaces (Terminal.app tinted / VS Code for Dev), spec-completeness audit as a Custos capability
- Git for the vault, git for this repo — both done

## Done this pass (Phase 2)

- GitHub repo created (`shaynesss/noctis-os`, private)
- Backend: `main.py`, `routers/{mode,session,nightshift}.py`, `vault_io.py`, `requirements.txt` — auth is a TODO marker, not yet implemented
- Frontend: Vite + React/TS, Tailwind wired and verified, `@` alias, `World.tsx`/`ProfileOverlay.tsx` stubs — no shadcn (initialized then removed per the mid-session correction, confirmed clean rebuild)
- `/impeccable init` run, `PRODUCT.md` written, registered Product
- `Makefile` (`setup`/`dev`) — `make setup` timed ~10.5s warm-cache, `make dev` smoke-tested live
- `SETUP.md` — three-bucket checklist
- No secrets tracked

## Done this pass (Phase 3, mode-folder milestone)

- All five `second-brain/modes/<name>/` folders built (dev, learn, research, settings, nightshift): full methodology file (8-part mode anatomy), `lessons.md` (seeded with entry format + security note), `state.md` (seeded with the locked frontmatter contract per mode's card content), `jobs/` (empty, ready), `agents/*.md` (all seven v1 subagent stubs: critic, quizmaster, gap-finder, credibility-checker, synthesizer, lint-runner, distiller)
- `build-spine.md` moved into `modes/dev/dev.md`, restructured into the mode anatomy, Noctis-flavored (ship-gate step 9, library catalog, near-empty slack surface folded in). `~/.claude/CLAUDE.md` symlink retargeted directly to `modes/dev/dev.md` — no separate generic spine; this is now the one universal dev methodology for every project
- Every asserted-in reference to `build-spine.md` updated across the vault (`CLAUDE.md`, `README.md`, `index.md`, `wiki/Claude Code Workflow.md`) and this repo (`CLAUDE.md`, `README.md`)
- `.env.example`'s `VAULT_PATH` home-directory typo fixed (was tracked as a known issue, resolved in the doc-reconciliation commit)

## Done this pass (Phase 3, backend milestone)

- Auth: bearer-token + Origin middleware (`backend/auth.py`), applied to every router except `/health`
- `vault_io.py`: frontmatter read/write (`python-frontmatter`), serialized writer for `log.md`/`index.md`, file move/exists helpers
- `GET /mode/{name}` — reads a mode's `state.md` frontmatter, returns ambient state
- `POST /session/launch` — constructs the mode's invocation (methodology + lessons + job context), Dev opens VS Code (two-step, no `CLAUDE_CONFIG_DIR` override), the other four open a character-tinted Terminal.app window via `osascript` with `CLAUDE_CONFIG_DIR` pointed at `launch_config/nondev/`
- Nightshift inbox: `GET /inbox`, `GET /inbox/{id}` (full proposal content), `POST /inbox/{id}/accept|reject` (removes from index, archives the proposal file, logs the decision) — mode-specific diff-apply on accept is a known follow-up once a real proposal producer exists
- 23 passing pytest tests (`backend/tests/`) covering auth, vault_io, and all three routers

## Done this pass (Phase 3, frontend milestone)

- `World.tsx`: real character sprites at their locked footing coordinates, polls `GET /mode/{name}` every 15s, renders busy/idle state and Noctua/Echo's count badges per Interface.md's Views section
- `ProfileOverlay.tsx`: all five modes' locked card content — Faber's job rows w/ phase badges (+ idle copy when no jobs), Noctua/Vesper's stat blocks, Custos's trigger badges + diff count (+ idle copy), Echo's inbox rows with working accept/reject (no launch button, per spec)
- `api.ts` client, `frontend/public/assets` symlinked to the repo-level `assets/` (never duplicated into `src`, per the hard constraint), Press Start 2P + JetBrains Mono self-hosted, leftover Vite-template CSS replaced with the world's real design tokens
- Interim per-character sprite crops added (`assets/characters/*.png`) so the world has real art now — documented as interim, swappable at the same filenames once the locked grid-data/PIL pipeline exists
- **Smoke-tested live**: both dev servers started, driven with a headless Playwright browser (no `chromium-cli` in this environment), screenshotted the world and multiple profile overlays with real seeded backend data. Caught a real bug this way — missing CORS middleware was silently blocking every frontend fetch — fixed with two regression tests added to the backend suite (now 25 passing)
- A visual mockup of the world screen was also produced as a shareable Artifact before wiring, using the same real assets

## Done this pass (Phase 3, telemetry hooks milestone)

- `backend/hooks/log_action.py` — Claude Code PostToolUse hook, appends one action line (timestamp, tool name, short summary) per tool call to `backend/runtime/<mode>__<job>.log`. Job identity via `NOCTIS_MODE`/`NOCTIS_JOB_ID` env vars for Terminal.app launches (exported per-window, so concurrent nondev sessions never race on a shared settings file), or `--mode`/`--job-id` baked into the hook command for Dev/VS Code launches (whose URI-handler launch doesn't carry shell env)
- `launch_surfaces.py`: `_merge_hook()` idempotently registers the hook in a session's `settings.json` without clobbering Claude Code's own generated keys (theme, etc.) — nondev sessions get a static env-var-driven hook in `launch_config/nondev/settings.json`, Dev sessions get a per-project baked-args hook in `<project_path>/.claude/settings.local.json`
- `PATCH /mode/{name}/jobs/{slug}` — rewrites a job's `context.md` frontmatter at stage/track transitions (stage/status/track + `last_touched`) and syncs the mirrored entry in the mode's `state.md`
- `GET /mode/{name}/jobs/{slug}/log` — tailed read of a job's runtime log, the interface's poll target
- `ProfileOverlay.tsx`'s Faber job rows poll the log every 5s and show the most recent action line under the job's status (fixed-height card preserved — one line, not a full feed)
- 14 new pytest tests (hook script, launch-surface hook merging, new mode-router endpoints) — 37 passing total
- Smoke-tested live: real backend run, seeded a job, PATCHed its stage, piped a fake tool-call through the hook script, confirmed the log endpoint and synced `state.md` both reflected it, then cleaned the vault back to its pre-test state

## Not started

- Nightshift infra (launchd scheduler)
- Composite scale test, two background-image touch-ups, sprite sheet split into individual assets
- Custos's trigger thresholds (backend logic)
- Mode-specific proposal apply logic for nightshift's accept flow (currently archives only)
- Exact character hex palette (now sampled from real sprites rather than guessed, but still interim until the grid-data pass locks final production values)

## Blocking

Nothing. Mode folders, backend, frontend tracker, and telemetry hooks all done and verified live. Ready for nightshift infra.
