# STATUS.md

Last updated: 2026-07-20

## Current state

Phase 1 fully closed (Definition/PRD/EDD/Design Brief locked). Phase 2 setup starting: `.env.example` and project `CLAUDE.md` written. Repo scaffolding, GitHub repo creation, and dependency installs still need a Claude Code session — nothing in this list requires shell execution I can't do from here has been skipped, it's queued for that session.

## Locked (full detail in SPEC.md + wiki/Noctis OS/)

- Five-mode architecture, harness framing, stateless FastAPI + React/Vite + direct vault filesystem access
- Profile overlay card system (per-mode content, idle states, typography, animation) — see Interface.md
- World backdrop (peak-dusk cloud bed) + character sprite sheet — both delivered as real assets in `assets/`
- Session launch surfaces: Terminal.app (tinted per character) for four modes, VS Code for Dev
- Git for the vault — done

## Not started

- Phase 2 repo scaffolding (backend/frontend folder structure, GitHub repo, Makefile, dependency installs) — next Claude Code session
- Mode files (`second-brain/modes/<name>.md`) — first real build milestone once Phase 2 setup completes
- Composite scale test (sprite vs. background at real size) and two minor background touch-ups (stray artifact, star-shape consistency)
- Custos's trigger thresholds (backend logic, not blocking)

## Blocking

Nothing. Ready for a Claude Code session to run Phase 2 setup.
