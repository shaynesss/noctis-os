# STATUS.md

Last updated: 2026-07-21

## Current state

Phase 1 and Phase 2 both complete. Repo scaffolded, `make setup`/`make dev` verified. Pushed to `origin/main`. **Phase 3 complete** — mode-folder build-out, backend, frontend tracker, telemetry hooks, and nightshift infra all done and smoke-tested live. All items on the locked build order (mode folders → backend → frontend tracker → telemetry → nightshift) are built. **First full ship-gate pass run 2026-07-21** — README/CHANGELOG staleness fixed, dependency audits clean, and a security-focused code review caught and fixed real path-traversal and correctness bugs (see below). Deploy decision: stays local, per the locked EDD ("Any deployment — local-only," single-user single-machine).

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

## Done this pass (Phase 3, nightshift infra milestone)

- `backend/nightshift/slack_surface.py` — the deterministic Scan step, one checker function per mode (`SLACK_CHECKS` registry, nightshift.md's "tap-in contract": no hardcoded per-mode knowledge in nightshift itself). Real checkers for dev (`flagged: true` jobs, a new optional field on job-context frontmatter) and settings (undistilled lessons, via a `lessons_distilled_through` line-count cursor on `modes/settings/state.md`). Learn and research are registered but return an honest empty list — no real due-recall-item/parked-trigger data model exists yet, and nightshift.md is explicit that a quiet surface is a correct outcome, not a gap to fake.
- `backend/nightshift/runner.py` — Advance + Stage. Dev's advance stays fully mechanical (templated status note, matching dev's deliberately near-empty, code/branch-free slack surface). Settings' advance genuinely borrows the distiller subagent at reduced permission via a real headless `claude -p` call (`--allowedTools`/`--disallowedTools` scoped to Read/Grep + Write on exactly one inbox file, no Bash/network). Stage writes the proposal file and the mirrored `state.md` index entry, parsing `rationale` out of the drafted `## Rationale` section rather than drafting it twice. Idempotent against already-pending items (matches on the slug's stable prefix, not the date-stamped full slug, so a second run on a later day doesn't restage the same slack).
- `scripts/nightshift_run.sh` rewritten (was a TODO stub) to actually invoke the runner; `launchd/com.noctis-os.nightshift.plist` (nightly 03:00) + `SETUP.md` load/unload instructions.
- Same `load_dotenv()` fix as main.py applied to the runner — launchd runs with no shell env at all, would otherwise fail on `VAULT_PATH` exactly like the earlier `make dev` bug.
- 11 new pytest tests (slack-surface checkers, runner dedup/rationale-parsing/staging) — 48 passing total.
- **Smoke-tested live, real cost incurred on purpose:** seeded a flagged dev job, ran the actual launchd script end-to-end, confirmed a correctly-shaped inbox item + index entry, confirmed a second run doesn't duplicate it. Also ran the real distiller headless call against the live (boilerplate-only) `lessons.md` files — it correctly judged there was nothing to distill and declined to write a proposal rather than fabricating one. That run surfaced a real bug in the deterministic cursor check (an empty `{}` cursor treats every mode's still-boilerplate lessons.md as "undistilled," which would have cost a real API call every night for nothing) — fixed by seeding the cursor to each file's actual current line count (12) instead of 0. All smoke-test vault writes cleaned up before committing.

## Done this pass (dev job lifecycle — closes the gaps nightshift's own build exposed)

- `POST /mode/{name}/jobs` creates a job; `_sync_state_job_entry` fixed to mirror `flagged` into `state.md` (it was silently dropping the field, meaning nightshift could never actually see a flag even if one got set)
- `backend/staleness.py`: deterministic flag_stale_dev_jobs, 6-hour no-activity threshold, skips jobs closed cleanly via a new `Stop` hook (`backend/hooks/mark_session_end.py`, SESSION_END sentinel in the runtime log). Runs inline on `GET /mode/dev` — live, not just nightly.
- Frontend: per-job "resume" launch on Faber's job rows, idle-state button starts a new build (creates the job, then launches) — `window.prompt`-based placeholder, not a designed input yet. Bottom button relabels "+ NEW BUILD" once jobs exist.
- This repo's own build registered as a real job (`noctis-os`, stage Build) — Faber's card now genuinely reflects the work instead of showing idle all session.
- 8 new pytest tests (staleness checker, Stop hook, create-job endpoint) — 57 passing total. Verified live: created and corrected the real job via the live API, screenshotted the actual card showing the phase badge, resume button, and relabeled launch button.

## Done this pass (ship-gate security review — first full ship gate for the project)

Ran dev.md's 9-step FINISH checklist for real (test suite, diff review, doc accuracy, secrets scan, dependency audit, security-lens code review). Fixed two stale docs (README claimed Phase 3 was still in progress; CHANGELOG was missing the mode-folder/backend/frontend-tracker milestones and several bugfixes). Dependency audits clean (`npm audit`, `pip-audit` — the latter's initial 6 findings were a stray leftover `setuptools` metadata dir in the local `.venv`, not a real dependency issue, and `.venv/` is gitignored regardless).

An 8-angle security-focused code review (3 correctness + 3 cleanup + altitude + conventions, cross-verified) found and fixed real issues, all in code from this session's own earlier milestones:

- **Path traversal, confirmed:** `job.slug`/`job_slug` reached filesystem paths (vault writes via `POST /mode/{name}/jobs`, runtime-log paths via the telemetry hooks) with no character validation — a crafted slug could write outside the vault or `backend/runtime/`. Fixed at two layers: `vault_io.py` now verifies every resolved path stays inside the vault root (`_resolve_within_vault`), and a new `vault_io.is_safe_slug()` validates slugs at every API boundary (`POST`/`PATCH /mode/{name}/jobs*`, `POST /session/launch`) for a clean 400 instead of a low-level error. Verified live against the running backend with real attack payloads — both rejected, nothing written.
- **Hook accumulation, confirmed:** `_merge_hook` matched on exact command string, so a new job in the same `project_path` added a hook entry without removing the previous job's — every prior job's hooks kept firing on every future session in that project, permanently defeating `staleness.py`'s flagging. Fixed: `_merge_hook` now replaces any existing entry for the same script rather than appending, so at most one hook per script per event ever exists.
- **No per-item fault isolation, confirmed:** nightshift's `run()` had no exception handling around each item's Advance step — one failing/timing-out `claude -p` call would silently abort the whole run, dropping every other independent item. Fixed: each item's advance is now wrapped, logging the failure and continuing to the next item.
- **Unlocked concurrent writes, confirmed:** `state.md`/job `context.md` writes had no lock (the project's own write-lock was scoped to `log.md`/`index.md` only, an assumption this session's own staleness-check-on-every-poll + PATCH combination falsified). Fixed: `vault_io`'s write lock now covers every write, not just the two special-cased files (full read-modify-write atomicity across the read step remains an open, lower-priority gap — noted, not solved, as disproportionate to this app's actual concurrency).
- **Unanchored sentinel match, plausible → fixed:** `"SESSION_END" in last_line` would misread a tool-call summary that happens to contain that literal text as a clean session close. Fixed to check the log line is exactly the two-token sentinel format.
- **One claim verified live and refuted:** the distiller's `--allowedTools "Write(path)"` scoping was flagged as possibly unenforced by the CLI. Tested for real (a live headless call instructed to write off-target) — confirmed the CLI's permission system genuinely blocks it (`permission_denials` in the response). Not a vulnerability.

12 new/updated pytest tests, 69 passing total. All fixes verified live against the running backend, not just unit-tested.

## Not started

- Composite scale test, two background-image touch-ups, sprite sheet split into individual assets
- Custos's trigger thresholds (backend logic)
- Mode-specific proposal apply logic for nightshift's accept flow (currently archives only) — this now includes advancing the `lessons_distilled_through` cursor on accept, a known follow-up from the nightshift milestone above
- A real designed "new build" input (name/path) — currently `window.prompt`, a functional placeholder, not the intended final UI
- Exact character hex palette (now sampled from real sprites rather than guessed, but still interim until the grid-data pass locks final production values)

## Blocking

Nothing. All Phase 3 build-order milestones (mode folders, backend, frontend tracker, telemetry hooks, nightshift infra) are done and verified live.
