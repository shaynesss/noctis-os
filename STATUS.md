# STATUS.md

Last updated: 2026-07-20

## Current state

Phase 1 and Phase 2 both complete. Repo scaffolded, frontend running, `make setup`/`make dev` verified. Pushed to `origin/main`. Phase 3 underway — mode-folder build-out and backend milestones both done; frontend tracker is next.

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

## Not started

- Frontend tracker (World/ProfileOverlay wired to real backend data), telemetry hooks, nightshift infra (launchd scheduler)
- Composite scale test, two background-image touch-ups, sprite sheet split into individual assets
- Custos's trigger thresholds (backend logic)
- Mode-specific proposal apply logic for nightshift's accept flow (currently archives only)
- Exact character hex palette (backend currently uses placeholder approximations for Terminal tint colors)

## Blocking

Nothing. Mode folders and backend both done, ready to start the frontend tracker.
