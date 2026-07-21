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

## Done this pass (Custos's trigger thresholds — resolves the last open Design Brief item)

- `backend/triggers.py`: friction/accumulation/suspicion computed live on every `GET /mode/settings` poll, same pattern as `staleness.py`'s dev job flagging. Accumulation reuses nightshift's undistilled-lessons cursor signal exactly (no separate tracking); friction is an opt-in `FRICTION:` marker in a mode's lessons.md text since the last distillation pass (documented in all five modes' `lessons.md`, not inferred from prose — deterministic); suspicion is a 7-day `state.md` mtime staleness check.
- 6 new pytest tests — 75 passing total. Verified live end-to-end against the running backend: appended a real `FRICTION:`-tagged lessons entry, confirmed both badges lit via the API and a Playwright screenshot of Custos's actual card, then cleaned up and confirmed the badges correctly cleared.
- Design Brief's last open item (`SPEC.md`: "Custos's trigger thresholds, backend-logic, not blocking") is now resolved.

## Done this pass (Custos scoped-task launches — address a lit trigger, run a completeness check)

- `POST /mode/{name}/jobs` gained a `notes` field, which becomes the job's `context.md` prose body — previously always empty, meaning a scoped launch had no more direction than a bare methodology dump (`POST /session/launch` injects that prose, not the frontmatter, into the actual prompt).
- Frontend: each lit trigger badge on Custos's card gets an "address" button (creates a task-specific job with real starting instructions, then launches); an always-available "run completeness check" action does the same for Custos's spec-completeness audit capability, targeting Noctis OS's own `SPEC.md`/`CLAUDE.md` against the wiki (not a per-project picker — Shayne's call).
- Custos itself still never runs on a schedule, by design (`settings.md`: "deliberately no calendar") — this only makes the on-demand path scoped instead of generic; nightshift's existing nightly borrow of the distiller subagent for undistilled lessons is the only automatic path, unchanged.
- 2 new/updated pytest tests — 76 passing total. Verified live: confirmed via the running API that a job's `notes` field lands correctly in `context.md`'s prose, and via Playwright screenshots that address buttons appear only next to lit triggers and disappear when unlit.

## Done this pass (nightshift's accept-flow apply logic — the propose/review/apply loop is real end-to-end now)

- `backend/nightshift/apply.py`: parses a proposal's `## Diff` section and applies it — a literal find-the-old-block-and-replace-it applier tolerant of the inbox format's simplified diff shape (no line numbers), not a general unified-diff/patch implementation. Refuses to guess: raises if the old text isn't found, or is found more than once (ambiguous).
- `POST /nightshift/inbox/{id}/accept` now applies before removing from the inbox — a failed apply (422) leaves the item still pending review rather than losing it. Dev's flagged-job proposals (no diff, by design) apply as a no-op and archive normally.
- The `lessons_distilled_through` cursor-advance follow-up flagged in the nightshift milestone is done: `runner.py`'s distillation drafts now leave a machine-readable `<!-- cursor-advance: mode=count -->` marker (computed deterministically at draft time, not re-derived from the slug later — slug/slug_hint aren't a reliable place to recover which mode a distillation targeted). Accept parses it and advances the cursor.
- 11 new/updated pytest tests — 87 passing total. Verified live against the running backend and real vault: staged a real diff-bearing proposal, accepted it, confirmed the target file actually changed; staged a malformed proposal, confirmed accept returned 422 and the item stayed in the inbox untouched; cleaned up all smoke-test artifacts including a stray log.md entry the accept flow itself wrote.

## Done this pass (world/sprite polish — sprite drift fix, background touch-ups, expression extraction)

- **Sprite drift bug, fixed.** `.world`'s footing-spot percentages were always correct in principle, but `background-size:cover` on a container whose aspect ratio didn't match the image (`width:100%; height:100vh`) cropped differently at every window size, so characters visibly drifted off their cloud footing on resize. Fixed by locking `.world` to the backdrop's native 1376:768 ratio; letterboxes/pillarboxes against the sky-deep background outside that ratio instead. Verified at three very different window shapes (wide/tall/ultrawide) — same relative footing every time.
- **Both documented background touch-ups, done.** Removed the stray comma-shaped artifact (cloned a clean nearby sky patch over it, matching local JPEG grain rather than a flat fill that would show a seam). Standardized the star field on the four-point sparkle shape (was mixing dots and sparkles) — the 6 dot stars were erased and restamped using an actual existing sparkle's real pixel signal, not hand-drawn, for guaranteed visual consistency.
- **Composite scale test — done implicitly.** Every live Playwright screenshot taken across this whole build already is real sprites at real render size against the real background; scale reads correctly (legible, proportionate, no adjustment needed).
- **Sprite sheet expressions extracted.** `assets/characters/expressions/` — 19 non-idle variants (hard-hat, sleepy, magnifier, and 16 others) found via connected-component labeling on the reference sheet (not hand-picked crops) and cleaned with the same pipeline as the 5 locked idle sprites. Not wired into the app — idle roaming/expression swapping is explicitly v2 scope — this is asset-production only, ready for when that's built. A few labels are honest best-guesses from visual inspection, flagged as such in `expressions/README.md`.
- Answered a process question: this stays a local web app (browser tab / VS Code Integrated Browser), not a native Mac app — `SPEC.md` explicitly lists "Tauri desktop wrap" under out-of-scope, a deliberate parked decision, not an oversight. (Confirmed again: Tauri would wrap this exact backend/frontend unchanged into a native bundle — a real, named, deliberately-not-built-yet option, not a rewrite.)

## Done this pass (sprite size scaling fix + real new-build input)

- **Sprite size, not just position, wasn't actually locked to the scene.** The aspect-ratio fix above locked *position*, but `--sprite-w` and `.health-strip`'s spacing were still sized off `vw` (raw viewport width) — as the world container's width diverged from the viewport (letterboxing on tall/wide windows), sprites grew or shrank out of proportion to the background even though their position stayed correct. Fixed with CSS container queries: `.world` is now a size container (`container-type: inline-size`), and everything inside it sizes off `cqw` (the container's own width) instead of `vw`. Verified numerically across four window shapes — sprite width holds at a consistent ~6% of the world container's width every time (only hitting the 46px readability floor at very small sizes, which is intended).
- **Real "new build" input, replacing `window.prompt`.** A designed modal (`NewBuildModal` in `ProfileOverlay.tsx`) matching the existing card system's language — paper background, accent border, pixel-font header — with labeled name/project-path fields, disabled-until-valid submit, cancel. Verified live: submit correctly disabled empty, enabled once both fields have content, screenshot confirms it renders correctly layered over the dimmed profile card.
- **Hex palette re-verified, not changed.** Precisely re-sampled each sprite's dominant opaque pixel color — exact match to the already-documented values (`#E53311` Faber, `#ECA207` Noctua, `#953EAD` Vesper, `#DA5B00` Custos, `#293187` Echo). Still interim pending the future PIL grid-data pipeline (a separate, larger deferred task, not a "fix"), but confirmed maximally accurate for the current interim art.

## Done this pass (world screen: fixed canvas, legible labels, expression-based status)

**Supersedes both entries above about responsive scaling.** Direct feedback: the responsive approach itself was wrong, not just its execution — Shayne wants the large-window layout to be the *only* layout, not something that reflows. `.world` is now a fixed 1376×768 canvas (the backdrop's native resolution, which the footing fractions and the sprite clamp's own max were already designed against), centered in the viewport, letterboxed/cropped at the edges on a smaller window rather than scaling. `--sprite-w` is a fixed 84px. The `aspect-ratio`/`min(vw,vh)` lock and the `container-type`/`cqw` sizing from the two passes above are both gone — replaced, not layered on top of.

- **Label legibility, round two.** First attempt (opaque fill) was rejected on sight ("nope i still like the transparent/white box") — reverted to the original transparent background, kept the font-size bump, moved legibility onto a text-shadow instead. Separately, switched the label's font from Press Start 2P to JetBrains Mono — a display pixel font isn't built to stay legible at small copy sizes, every glyph read as an ambiguous block; the mono font already carries the same game-ish register everywhere else in the UI and actually resolves at 11px.
- **Status dot removed; busy/idle now told through which expression is showing.** The dot's position-overlap bug got fixed once already but the underlying idea was replaced instead: each character now swaps between an idle sprite (a "sleepy" expression from the newly-extracted set, where a clean one exists) and a busy sprite (hard-hat for Faber, magnifier for Custos, alert-eyes for Vesper/Echo, default-eyes-open for Noctua). This directly uses the 19 expression variants extracted earlier the same day — supersedes `Interface.md`'s original "ambient state indicators only, no expression swapping in v1" scoping, Shayne's direct call, `SPEC.md` updated to record it. Idle *roaming* and the rest of the expression set beyond one busy/idle pair per character stay v2.
- Verified live: idle state screenshot shows Noctua/Vesper/Custos in their sleepy variants; forced all five modes `busy: true` via the real API and re-screenshotted — Faber in hard-hat, Custos with the magnifier, Echo alert-eyed, confirmed correct per-character, then reset state back to idle.
- Answered plainly: Tauri would wrap this exact backend/frontend unchanged into a native bundle, hot-reloading from the dev server exactly like now during development; only a packaged/distributed build snapshots the frontend, needing a rebuild for further changes, same as any desktop app. Shayne asked to move Tauri into v1 — scoping that as a distinct next step, not done in this pass (new toolchain, real architecture change, wants a plan first).

## Done this pass (native desktop window — pywebview, not Tauri)

Researched alternatives rather than defaulting to Tauri: compared pywebview, Tauri (+ FastAPI sidecar, a real documented pattern), and Electron. Recommended and built **pywebview** — stays 100% Python (no Rust toolchain), and Tauri's main advantage (tiny distributable bundle) doesn't matter for a single-user local tool nobody else downloads.

- **`make app`** (`desktop/app.py`) starts the same two dev servers `make dev` does, waits for both to answer, opens a frameless native window (`frameless=True`, no OS chrome at all) pointed at the frontend. Hot reload works exactly like a browser tab, same dev server underneath.
- **Confirmed both things Shayne asked for**: frameless (`frameless=True` + `easy_drag=True` since removing OS chrome also removes the normal drag-to-move behavior) and a path to a custom app icon (needs a bundler — `py2app`/`PyInstaller` — since pywebview's `icon` param only works on Linux/GTK; a deliberate next step, not done in this pass).
- **A real bug found and fixed by actually closing the window, not by assuming `.terminate()` was enough**: `npm run dev` spawns a *child* process running the real Vite server; `Popen.terminate()` only signals the immediate `npm` process, so the actual server (and its bound port) kept running invisibly after the window closed. Fixed with process groups (`start_new_session=True` + `os.killpg` on cleanup), registered three ways (window-closed event, `atexit`, `SIGTERM`) for defense in depth.
- **Verified live end-to-end**, not just code-reviewed: launched via `make app`, screenshotted the actual native window (confirmed genuinely frameless — content runs right to the window edge, no titlebar), confirmed the loaded app was making real live requests (continuous polling in the backend log). Closed it with a real simulated Cmd+Q keystroke (not the launching script's own cleanup call) and confirmed zero leftover processes and zero leftover bound ports via `ps`/`lsof`.
- `pywebview` added to `backend/requirements.txt` (already covered by `make setup`, nothing extra to install), `SPEC.md`'s Tauri out-of-scope line updated to record the actual decision.

## Done this pass (backend live reload for `make app`, placeholder Dock icon, flagged-job clear)

- **Backend hot reload for the desktop app.** `desktop/app.py` was starting `uvicorn` without `--reload` — added it, matching `make dev`. Verified the running desktop instance actually picked it up (two `uvicorn` reloader+worker processes, same pattern `make dev` already showed).
- **Placeholder Dock icon.** Neither pywebview's `create_window` nor `start` icon params work on macOS (both documented GTK/QT-only) — worked around with AppKit directly (`NSApplication.setApplicationIconImage_`, run once the GUI loop is live via `webview.start(func=...)`), using Faber's sprite as the placeholder per Shayne's own call ("can be random for now, actual art down the line"). Ran clean with no exception using the standard API; couldn't get a clean screenshot confirming the Dock icon specifically in this environment (auto-hiding Dock, synthetic mouse events didn't reliably force the reveal) — worth a glance at the real Dock next run rather than treated as fully confirmed.
- **Flagged jobs could never be un-flagged.** Found live: `noctis-os`'s own job was showing `FLAGGED` on Faber's card because `last_touched` hadn't moved since an early PATCH and the 6-hour staleness threshold had passed — a real, honest consequence of this whole session's work happening through direct file edits rather than the app's own launch-a-session flow, which is the only thing the telemetry hooks can observe. Real behavior, not a bug, but exposed a real gap: `staleness.py` can set `flagged`, nothing could clear it. `JobUpdate` gained a `flagged` field; `handleResumeJob` (World.tsx) now clears it before launching, since resuming is the natural point a flagged job gets addressed. Verified live against the real running job via the API — flag cleared, `last_touched` refreshed.
- 1 new test (flag-clearing), 88 passing total.

## Not started

- Sprite sheet split into individual per-character assets (distinct from the expression extraction above — this is about the *idle* sprites' own source format)
- Exact character hex palette (now sampled from real sprites rather than guessed, but still interim until the grid-data pass locks final production values)

## Blocking

Nothing. All Phase 3 build-order milestones (mode folders, backend, frontend tracker, telemetry hooks, nightshift infra) are done and verified live.
