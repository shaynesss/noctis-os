# STATUS.md

Last updated: 2026-07-20

## Current state

Phase 1 and Phase 2 both complete. Repo scaffolded, backend/frontend running, `make setup`/`make dev` verified. Three local commits, nothing pushed (manual push, per this project's git workflow). Next real work is Phase 3 — building out the mode folders.

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

## Known issue

`.env.example`'s `VAULT_PATH` has the wrong home directory — my error, not Claude Code's. One-line manual fix needed (`sed` command given), couldn't be fixed from Desktop due to a dotfile-indexing limitation in the vault connector.

## Not started

- Phase 3: actual mode-folder build-out (`second-brain/modes/<name>/` per mode — methodology, lessons, state, jobs, agents)
- Backend auth implementation (currently a TODO)
- Composite scale test, two background-image touch-ups, sprite sheet split into individual assets
- Custos's trigger thresholds (backend logic)

## Blocking

Nothing. Ready to start Phase 3.
