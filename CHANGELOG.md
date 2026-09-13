# Changelog

## v2.0.0-dev — Stage 2 (in progress)

**v2 replaces Claude Desktop as the entry point. The app drives Claude Code as
a subprocess, so it runs on the existing subscription with no API billing.**

Stage 1 (foundation, prompts, retrieval eval, bootstrap) and Stage 2 items 1-5,
7, 8 and 9 are complete and verified live. Item 6 is done except its
scheduler, which is the only feature left in the build order.

### Under review: the real CLI in a PTY (2026-09-13)

**Not built, not decided.** Noctis spawns `claude -p` — "print response and
exit" in the CLI's own help — once per turn, and most of the orchestrator
exists to rebuild the interactive loop on top of a scripting mode. Running the
CLI in a pseudo-terminal instead would delete that reconstruction.

It was rejected twice before, correctly, under a premise that no longer holds:
`Modes.md` called PTY capture "the original trap" when the interface launched
sessions into Terminal.app and read state back from files. v2 hosts its
sessions, and under hosting a PTY is not mirroring — it is how you run an
interactive process. The rejection was never re-derived when its foundation
was removed.

Every assumption tested against 2.1.263 rather than argued: a `/status`
injected into a PTY from outside renders and the process exits with no
orphans; `statusLine` delivers `five_hour`/`seven_day`, context window,
effort, cost, `session_id` and `transcript_path`; the CLI writes its own
transcripts **incrementally**, so a session SIGKILLed mid-generation keeps its
partial output; `--resume` appends without forking; `portable-pty` builds on
this toolchain at 773 KB with 20 dependencies. Termic already ships this exact
architecture — xterm.js + WebGL2 in Tauri with the PTY in Rust.

**Stats gets one raw lifetime token count.** The CLI's background calls are
absent from the JSONL, which is 146,327 tokens against 82,174,586 — 0.178%.
`aux_input_tokens`/`aux_output_tokens` go with the migration.

Review: `PTY-MIGRATION.md`. Decision: `SPEC.md` Open questions 7.

### One command to run Noctis, and it opens the app (2026-09-13)

**`make app` is now `make dev`.** The naming had it backwards: the command with
the obvious name opened a browser tab, and the app was the thing you had to
know to ask for. You develop in the window you use, so a bug found while
working is a bug found in the real surface.

| before | after | |
|---|---|---|
| `make app` | **`make dev`** | Tauri window, supervised backend, `[tsc]` stream |
| `make dev` | `make browser` | browser tab at `:5180`, `uvicorn --reload`, no Rust build |
| `make backend` | `make reload` | kills uvicorn; the supervisor brings it back on current code |

`make browser` stays for backend-only work, where a Rust build is not worth
paying for. Product capabilities are identical across the two — everything
else is backend or frontend code.

`make reload` replaces `make backend`, which started a *second* uvicorn beside
the supervised one and clashed on the port. Killing it instead means a
deliberate restart and a crash take the same path, which is what crash-only
design is for rather than a special case bolted beside it.

**Fixed in the same pass, all found by sweeping rather than assumed:**

- **`desktop/NoctisOS.app` was broken.** Its launcher still ran `make app` — a
  target that no longer existed — so every double-click would have failed into
  `backend/runtime/desktop.log`, which nobody reads.
- **`test_the_supervised_backend_does_not_reload` had stopped running.** It
  sliced the Makefile at `\napp:` and threw `ValueError: substring not found`,
  so the "supervisor and reloader are alternatives, not layers" invariant was
  unchecked. It reads the `dev:` target now.
- **`supervise.py` pointed the wrong way twice** — its docstring and its
  already-answering error both told you to use `make dev` to get the reloader,
  which is now the opposite of what `make dev` is.
- **`DOCUMENTATION.md`'s troubleshooting table** still prescribed `make backend`
  for an absent backend.
- **`desktop/README.md`** described the pywebview shell deleted on 2026-09-12.
  Rewritten: the bundle is a double-click wrapper around `make dev`, plus the
  two lessons from that shell which still hold — cleanup needs process groups,
  and you verify by actually closing the window.

`CHANGELOG.md` and `STATUS.md` entries dated before today keep saying
`make app`; they are records of what the commands were at the time.

### The v1 cutover (2026-09-12)

v1 is gone. Removed: `World.tsx`, `ProfileOverlay.tsx`, `DesignLodge.tsx`,
`modes.ts`, `api.ts`, v1's `index.css` and `App.tsx`; the `mode`, `session`,
`nightshift` and `design_lodge` routers; `launch_surfaces.py`; every mode
config directory. The v2 shell calls only `/v2/*`, and nothing in it imported
from `src/` root, so the two halves came apart cleanly.

**Item 9, maintenance migration — closed.** Settings and Nightshift collapsed
into root-level `maintenance/` in September, but only their *methodology*
moved; two `MOVED.md` markers deferred the state because v1's pipeline still
read the old paths. With v1 gone the state followed: `state.md`, `lessons.md`,
`jobs/`, `inbox/` and `archive/` are now under `maintenance/`, the two state
files merged without key collisions beyond `mode` and `last_touched`, and the
two lessons files merged carrying nightshift's own security note — unattended
runs write with no human in the loop at write time, which the settings note
did not cover.

**The paths are named once.** There were eleven literals across six files, and
the mode→directory mapping had been restated three times and disagreed twice.
`jobs.py` owns them now, and `jobs_dir()` handles maintenance sitting outside
`modes/` rather than each caller assembling `modes/{mode}/...` and being wrong
for one of them.

**Item 8, tiered loading policy — removed rather than defined.** It appeared
in the build-order table and nowhere else: no description, no acceptance
condition, no trace in the vault. Its only defensible reading is what enters a
session's context at entry versus what it fetches on demand, and the system
already does that — capped job brief, overlay-as-pointer, opt-in retrieval.
The policy existed and was undocumented, not unbuilt. Written up in
DOCUMENTATION.md §6.

**api_error_status** is parsed, independently of `is_error`: a turn that died
on a provider 429 was reported as a plain empty turn, which sends you looking
in the harness for a fault that happened upstream.

**The v2 checkpoint is closed, passed.** Recorded four days late because until
09-11 the answer was contaminated — Faber could not run Bash, Edit or Write,
so any fallback to Desktop was forced rather than chosen.

### The harness itself (2026-09-11/12)

Not a numbered item — infrastructure debt that had been capping every one of
them. One cause, five symptoms, found by asking why Claude behaved worse
inside Noctis than outside it.

- **Sessions run against the real `~/.claude`.** `CLAUDE_CONFIG_DIR` pointed
  each mode at a private config root, and a config root is not a settings
  file: it is where plugins, skills, subagents, slash commands, MCP servers,
  accumulated permissions and memory all live. Redirecting it replaced the
  whole surface with an empty one, so Faber was reading a methodology naming
  Impeccable, the code-review plugin, a Critic subagent, Playwright,
  shadcn/Magic MCP and CodeRabbit — none of which it could reach. Neither
  launcher redirects now; a mode's methodology travels in the argv via
  `--append-system-prompt`, which also retires the only real argument for the
  split dirs (two sessions racing on a rewritten file) and turns off
  system-prompt snapshotting, so an edited methodology reaches a resumed
  session.
- **`~/.claude/CLAUDE.md` points at `prompts/system.md`, not `dev.md`.** The
  old symlink made the machine itself Faber. Harmless while every surface
  redirected away from it; a live leak into every mode the moment they
  stopped. The config root is infrastructure, never an identity.
- **Every mode gets the same tools.** `--disallowedTools` is gone. Capability
  was the wrong axis to vary on: a mode handed work it cannot perform ends
  its turn with nothing done and no way to say so. `git push` stays denied for
  all modes. Maintenance's propose-never-apply now rests on its methodology
  and the permission chip rather than a cage that also stopped it reading a
  repo it was asked to audit — a deliberate trade, recorded as one.
- **Permission requests are answered.** `--permission-prompts` took its `host`
  default with no host attached, so every request died unanswered and the
  chip's labels were fiction. The Noctis MCP server is the prompt tool now.
  Wiring it surfaced that the server had never been attached to any spawn
  since it was built — `vault_search` existed and nothing could call it.
- **Refusals and silence are events.** `permission_denials`, `terminal_reason`
  and `num_turns` had been sent on every result event and read by nothing. A
  turn ending with tool calls and no text renders as *"turn ended with no
  reply"*; one refused its tools renders as *"turn ended blocked"* with the
  refusals named. This is why `system.md`'s "never end a turn without
  user-visible text" kept failing: the rule was not ignored, it was
  unsatisfiable.
- **The composer chip sets effort, not permission.** `low`/`medium`/`high`/
  `xhigh`, default high. `dev.md` had specified effort routing since it was
  written while no code passed `--effort`.
- **Vault subagents are registered.** The Critic, and Noctua's and Vesper's
  rosters, reach sessions via `--agents` for the first time.
- **The vault's absolute path is stated in the prompt.** `system.md` gives a
  relative `second-brain/`, which resolves against the project; a live session
  reported the vault unreadable while reading it through MCP.
- **Capability contract.** `backend/capabilities.py` — each mode declares what
  its methodology assumes, the harness reports what it has, `make doctor`
  prints the gap. `--migrate` emits a harness-migration brief covering
  everything that would not port, as intent rather than settings.
- **One mode→path mapping.** Three copies existed across `jobs.py`,
  `orchestrator/modes.py` and `mcp/server.py`, and two disagreed about
  maintenance. `jobs.py` owns both `jobs_dir()` and `methodology_path()`, which
  genuinely differ for maintenance and now say so.
- **`make test` covers the frontend**, and `make doctor` / `make backend`
  exist. `tsc --noEmit -p tsconfig.json` checks zero files against this repo's
  solution-style tsconfig and exits 0 — it reported a clean typecheck on a
  broken tree.

### Session orchestrator
- `orchestrator/` drives `claude -p --output-format stream-json --verbose` and
  normalizes the CLI's events into a stable union the frontend renders. Two
  concurrent sessions, queued rather than refused — the cap is a budget on the
  5h window, not a resource limit.
- Per-mode tool policy is enforced at spawn (`--disallowedTools`), not by
  instruction: maintenance's propose-never-apply failed a plainly-worded
  request in the regression suite, so it has a cage as well as a rule.
- `bypassPermissions` is excluded from the permission cycle and rejected over
  the wire — a guard that exists only in the client is not a guard.

### Noctis MCP server
- Dependency-free stdio server exposing `vault_search`, `history_search`,
  `job_context`, `worklist`, `propose`, plus prompts and resources. The
  portable half of the system: the body is Claude-Code-shaped, the brain is not.

### Shell
- Tauri v2 + React. Global Opt+Space summon, tray, launch-at-login,
  close-hides-not-quits.
- Chat with block-structured transcripts, mode entry (⌘T), handoff to another
  mode (⌘⇧H), cross-mode search (⌘K), stop (esc).
- Handoff opens a *new* session rather than switching a live one's mode: mode
  is a config dir, a model and a tool policy, and a running `claude -p` can
  change none of them mid-flight.
- Conversations survive a restart. Stats, Brief, Inbox and Settings read real
  data; where data does not exist yet the page says so and names the file it
  is waiting for.

### Panels — brief, worklist, inbox
- **Morning brief**, two halves deliberately separated: facts computed in
  Python (which jobs are open, how old, what is waiting) and prose written
  over them. Counted, not estimated, so nothing rounds 45 days to "about a
  month" or invents a job that closed in July.
- **The worklist is hand-kept, not generated** — a generated worklist is the
  job list again under a second name, and the two would disagree the moment
  one drifted. Editable in place, saved on idle, through a route that writes
  one fixed path: writing into the vault is only safe from a route that
  cannot be told where to write.
- **Inbox** parses proposal sections properly. It had been taking the body's
  first line as the summary — the markdown header — so every row read
  `## Rationale` while the sentence explaining the proposal sat unread below.
- The scheduler that would fire these does not exist yet, so Settings names
  what it *will* run rather than showing dead toggles.

### Bugs worth recording (all found by running it, not by tests)
- **PATH.** launchd starts processes with `/usr/bin:/bin:/usr/sbin:/sbin` — no
  Homebrew — so a scheduled backend would never have found `claude` while
  working perfectly from a terminal. The engine is now resolved explicitly.
- **Tauri origin.** The packaged app serves from `tauri://localhost`, not the
  dev server's port, so the built app could not have reached its own backend.
- **Model attribution.** `modelUsage` is keyed by model and its first key was
  the CLI's *background* tier, while the token counts beside it came from the
  primary — the name and the numbers described different models. Fixing it
  exposed a larger bug underneath: the background tier's tokens were counted
  nowhere at all. On a measured turn that was 899 of 901 input tokens.
- **sqlite across threads.** FastAPI runs sync routes on a threadpool, so a
  store opened at import was never on the thread that later read it. Every
  stats request would have raised.
- **A row per turn.** `engine_session_id` is UNIQUE, so the second turn of any
  resumed session died on the constraint — and the same mistake scattered one
  conversation's transcript across many rows. A row is the conversation now.
- **No user messages.** `record()` folds engine *events*, and the person's own
  prompt is not one, so every stored transcript was answers with no questions.
- **Permissions never reached a session.** `CLAUDE_CONFIG_DIR` redirects where
  user settings are read from, so `~/.claude/settings.json` — and every rule
  ever accumulated in it — is invisible to a spawned session. Every mode had
  been starting with an empty allowlist. Fixed with one tracked
  `permissions.json` passed via `--settings`.
- **MCP version echo.** The handshake returned whatever version the client
  asked for. Told `1999-01-01` it agreed — and a client told its requested
  version is supported will then use features that were never implemented.
  The spec's handshake is a negotiation, not an echo.
- **Fonts vendored and never loaded.** JetBrains Mono shipped in every build
  with its `@font-face` in v1's `index.css`, which stopped being imported at
  the v2 cutover. The guard written to catch that then missed Cascadia Code
  itself, deriving the family from the filename before stripping the
  extension — the test would have passed while the font went unloaded.
- **Absence rendered as an answer.** The activity grid drew "0 sessions in the
  last year" while its data was still loading; ⌘K rendered "No matches." for a
  query it never ran against an unreachable backend; and "Loading…" could
  outlive its request, because a restarting backend can accept a connection
  and never answer while `fetch` has no timeout of its own — so the failure
  state the UI already knew how to draw could not be entered.
- **A cwd of `~`.** `openSession` fell back to it when a stored transcript had
  none, and the handoff built `~/Developer/`. Both are real directories, so
  validation passed and the session simply started in the wrong place — which
  made filesystem search sweep the home folder and time out, reading as a
  broken tool rather than a bad working directory.

383 backend tests, 76 frontend, `tsc -b` clean.

## v1.5.2 — 2026-07-28

**Fix: frontend dev-server port collided with other projects on this machine; nightshift's distiller model was a hardcoded literal.**

- `frontend/vite.config.ts` pins the dev server to `:5180` with `strictPort: true`, instead of relying on Vite's `:5173` default — which collides with other local projects' dev servers on this machine. `backend/auth.py`'s `ALLOWED_ORIGIN` and `backend/tests/test_auth.py` updated to match.
- `backend/nightshift/runner.py`'s `DISTILLER_MODEL` is now overridable via a new `NIGHTSHIFT_DISTILLER_MODEL` env var (documented in `.env.example`), rather than a hardcoded literal — the fix the model-upgrade audit (Custos, 2026-07-23) flagged: a smaller/newer tier can now be adopted without a code change.
- `.gitignore` gains `backend/launch_config/nondev/{chrome,ide,tasks}/` — Claude Code's own runtime state (a native-host binary, a PID lock file, session-UUID folders), same category as the other generated `launch_config/nondev/` entries already ignored, previously untracked but not excluded.

## v1.5.1 — 2026-07-27

**Fix: backend reload was dropping in-flight requests, plus two apply-pipeline bugs found by Custos's own spec-completeness audit on Noctis OS itself.**

- `uvicorn --reload` watched `backend/runtime/` with no exclusion — the PostToolUse/Stop hooks write action-feed logs and busy markers into that directory on every tool call of every live session, so ordinary hook activity was restarting the backend mid-request. Surfaced live as "Load failed" in the desktop app's WKWebView when an Echo accept/reject click landed in a restart window (Chromium reports the identical failure as "Failed to fetch", which is why a same-machine browser-tab repro came back clean). Fixed with `--reload-exclude 'runtime/*'` on both `make dev` and the desktop app's uvicorn invocation.
- `vault_io.py` could only ever resolve paths inside `VAULT_PATH` — a diff proposal targeting `noctis-os/SPEC.md` (a sibling repo, not vault content) had nowhere to resolve to and raised a bare `FileNotFoundError`. Every prior accepted proposal only ever targeted a vault mode file (`modes/<name>/<name>.md`), so this was never exercised before. Fixed with a narrow, explicit `noctis-os/` project-root allowlist rather than widening vault_io's writable root generally.
- `backend/nightshift/apply.py`'s target-path regex (`\S+`) stopped at the first space, truncating the one proposal targeting a wiki page (`wiki/Noctis OS/Modes.md`, a real space in a real folder name) to `wiki/Noctis`. Fixed to capture the whole line.
- 4 new regression tests (project-root resolution + traversal guard, the space-in-path fix, a mechanical check that the reload-exclude flag can't silently disappear from either launch path again) — 151/151 backend tests passing.
- `SPEC.md` itself gained 6 fixes from the audit that found these bugs: a direct contradiction (`busy` documented as a `state.md` field when it's actually been a separate runtime marker since 2026-07-22), three missing-but-shipped mechanisms (the `--append-system-prompt` session-start channel, Echo's History section, Faber's new-build scratch-directory flow), one undocumented pair of 2026-07-24 telemetry fixes, and one stale self-contradiction in its own Open Questions list (nightshift's scheduler was already locked as launchd elsewhere in the same file).

## v1.5.0 — 2026-07-25

**Design Lodge** — a vault-native, browsable/editable catalog of design assets, built as a full Overhaul (Plan amendments through `SPEC.md`'s PRD/EDD/Design Brief, Build, Ship). Distinct from the existing (still-unbuilt) "library catalog" feature, which is vetted *code dependencies* fed by research verdicts — this one is design components/patterns/palettes, fed by Faber's own build and capture flow.

- Backend: `backend/routers/design_lodge.py` — CRUD for entries plus a quick-capture inbox queue, all behind the existing bearer-token + Origin auth. `vault_io.py` gains `list_dir` and the vault's first binary read/write helpers (`read_binary`/`write_binary`) for preview images.
- Storage: `second-brain/design-lodge/index.md` (lightweight index, same pattern as every mode's `state.md`) + `entries/<slug>.md` per entry, vault-level rather than per-project so every future Faber build reads the same shelf.
- Frontend: new "design lodge" tab inside Faber's profile-overlay card (`DesignLodge.tsx`) — category-filtered browse grid with image-first previews (fetched as authenticated blobs, never a token in a URL), expand-to-reveal code/reference/tags, inline add/edit form with image upload, and the quick-capture inbox. Faber's card gains the same fixed-height exception already granted to Echo (auto-height, wider, viewport-capped) since the default card was too small for this content.
- Seeded with 7 real entries pulled from this repo and Portfolio Platform (typography pairing, world/character palette, typewriter reveal, caret-expand disclosure row, the 3D project card's rest-state camera-fit math, its separate expand/dive animation curve, and the two-column repo-card hero) — not fabricated placeholders; two Portfolio Platform visuals are honestly labeled schematic, not live WebGL captures.
- `dev.md` (global Faber methodology, applied via Custos's staged-diff process, not edited directly by this build): the Overhaul mechanic gained an explicit four-stage breakdown (Plan amends only, Setup is treated as already-satisfied with feature scaffolding folding into Build, Build re-triggers 3.0 scoped to the change, Ship keeps the full nine-step gate with an integration-fit lens) — plus three new Design Lodge touchpoints (Plan: browse before gathering references; Build 3.0: check-first before shadcn/Magic MCP/fresh inference, save keepers back; Ship: consistency check) and an opportunistic, non-blocking inbox-processing pass at session-bootstrap.

## v1.0.0 — 2026-07-21

Full build order complete (mode folders, backend, frontend tracker, telemetry hooks, nightshift infra, dev job lifecycle), two ship-gate passes run, deployed locally per the locked EDD (single-user, single-machine — nothing to deploy). Everything below.

- Fix: `desktop/NoctisOS.app` failed to launch from Spotlight/Finder double-click (`FileNotFoundError: 'npm'`, confirmed live) — LaunchServices runs the app with a minimal PATH that excludes Homebrew, unlike a terminal-launched `make app`. Resolves npm's absolute path with Homebrew-path fallbacks and passes an augmented PATH to its subprocess (npm's own `env node` shebang needs it too). Icon switched to the faber-building expression (2026-07-21)

- Desktop: `desktop/NoctisOS.app` is a real double-clickable app now (thin wrapper around `desktop/app.py`, always runs live source, not a frozen build) with a proper bundled icon — closes the "real .app bundle" follow-up flagged when the pywebview wrapper first shipped. Added a Refresh command (native menu item + Cmd+R/Ctrl+R) since a code change to this always-live-source bundle only needs a reload, never a rebuild. `make open-app` alongside the existing `make app` (2026-07-21)

- Fix: the busy indicator (expression swap + new label-highlight) was dropping mid-session because `mark_session_end.py` was registered on Claude Code's `Stop` hook, which fires after every agent turn, not on real session termination. Moved to `SessionEnd`; `_merge_hook` now also purges a script from any other event bucket it's still registered under, so old settings.json files don't end up firing the hook on both events. Label now also stays accent-colored while a mode's session is running, independent of the profile overlay being open, using the same `busy` flag as the expression swap (2026-07-21)

- Closed two spec-completeness gaps found by a real audit against `SPEC.md`: nightshift's confidence flag was always staged as `null` (settings' distiller now writes a genuine high/low self-assessment into a fourth mandatory `## Confidence` proposal section; dev's mechanical flagged-job note always gets `high`, no judgment involved); and staleness-flagging only worked for dev despite learn/research/settings promising the same failure behavior (`staleness.py` generalized to `flag_stale_jobs(mode)`, wired into all four; Noctua/Vesper/Custos's cards never rendered job rows at all, so extracted a shared `JobList` component so a flagged job is actually visible, not just tracked server-side). 10 new/updated tests, 94 passing (2026-07-21)
- Fix: `busy` was never set anywhere in the backend for any mode (found live — launching Noctua's session didn't update its card). `POST /session/launch` now sets it true; the Stop hook (`mark_session_end.py`) clears it false on clean exit. Hooks now invoke the venv's own Python explicitly rather than bare `python3` (2026-07-21)
- Fix: world screen letterboxed instead of filling the window (third pass) — `.world` is now `100vw`/`100vh` with the backdrop stretched to fill exactly, instead of a fixed 1376×768 canvas; sprite sizing stays tied to the container so it can never drift from the background regardless of window shape (2026-07-21)
- Desktop app: backend now runs with `--reload` (was missing, only frontend hot-reloaded); placeholder Dock icon via AppKit (Faber's sprite, real art to follow); flagged jobs can now be un-flagged (`JobUpdate.flagged`, resume clears it) — found live when noctis-os's own job got flagged from this session's file-edit-not-launched-session workflow (2026-07-21)
- Native desktop window: `make app` (`desktop/app.py`) opens Noctis OS as a frameless pywebview window (not Tauri — researched alternatives, pywebview stays 100% Python with no new toolchain, chosen for this single-user local tool). Fixed a real subprocess-cleanup bug found by actually closing the window (`npm run dev`'s child process survived `.terminate()`) using process groups; verified live with a real Cmd+Q keystroke, zero leftover processes. Custom app icon needs a bundler pass (`py2app`/`PyInstaller`), a follow-up (2026-07-21)
- World screen: fixed 1376×768 canvas, not responsive (supersedes the earlier aspect-ratio/container-query scaling attempts — direct feedback that the large-window layout should be the only layout); label font switched from Press Start 2P to JetBrains Mono for legibility at small sizes, reverted an opaque-fill experiment back to transparent per feedback; status dot removed and replaced with expression-based busy/idle sprite swapping (hard-hat, magnifier, sleepy, alert, etc. from the extracted expression set) — supersedes Interface.md's original v1 scoping, SPEC.md updated (2026-07-21)
- Fix: sprite size wasn't locked to the world scene, only position was — `--sprite-w` and health-strip spacing used `vw` (viewport width) instead of the world container's own width, so sprites scaled out of proportion to the background whenever letterboxing changed. Fixed with CSS container queries (`cqw` instead of `vw`). Real "new build" modal replaces the `window.prompt` placeholder (2026-07-21)
- World/sprite polish: fixed a real sprite-drift bug (`.world`'s `background-size:cover` cropped differently at every window size since the container's aspect ratio didn't match the image — now locked to the backdrop's native ratio, verified at three window shapes); removed the stray sky artifact and unified the star field on one sparkle shape; extracted 19 expression-variant sprites from the reference sheet into `assets/characters/expressions/` (not wired into the app, v2 scope); composite scale test satisfied implicitly by every live screenshot already taken (2026-07-21)
- Nightshift accept-flow apply logic: `backend/nightshift/apply.py` parses and applies a proposal's `## Diff` section for real (was archive-only), fails safe (422, item stays pending) rather than guessing on an ambiguous or stale diff; distillation proposals now carry a cursor-advance marker so accepting one actually advances `lessons_distilled_through`. 11 new/updated tests, 87 passing. Verified live against the running backend (2026-07-21)
- Custos scoped-task launches: `POST /mode/{name}/jobs` gained a `notes` field (the actual job context.md prose, previously always empty); each lit trigger badge on Custos's card gets an "address" button, plus an always-available "run completeness check" action targeting Noctis OS's own SPEC.md/wiki. Custos still never runs on a schedule by design; this only scopes the on-demand launch (2026-07-21)
- Custos's trigger thresholds: `backend/triggers.py` computes friction/accumulation/suspicion live on every `GET /mode/settings` poll. Accumulation reuses nightshift's undistilled-lessons cursor; friction is an opt-in `FRICTION:` marker in lessons.md entries (documented in all five modes' lessons files); suspicion is a 7-day state.md staleness check. Resolves the Design Brief's last open item. Verified live end-to-end (2026-07-21)
- Security: first full ship-gate pass (dev.md's 9-step FINISH checklist) fixed stale README/CHANGELOG, and an 8-angle security-focused review found and fixed real path-traversal (unsanitized job slugs reaching filesystem paths), a hook-accumulation bug that defeated staleness flagging, missing per-item fault isolation in nightshift's run loop, an unlocked concurrent-write race on `state.md`, and an unanchored sentinel string match. `vault_io.py` now enforces path containment on every read/write and exposes `is_safe_slug()` for API-boundary validation. Verified live against the running backend with real attack payloads (2026-07-21)
- Fix: restore the locked typewriter-reveal entrance for profile-overlay card content — the card container had a fade/scale entrance, but the actual per-character content typing was never built (2026-07-21)
- Fix: vertically center idle-note text within the profile card body, was top-anchored via margin (2026-07-21)
- Fix: `load_dotenv()` in `main.py` — the backend only worked when the launching shell happened to have `.env` manually sourced; broke `make dev` silently otherwise (2026-07-21)
- Dev job lifecycle: `POST /mode/{name}/jobs` (create), `backend/staleness.py` (deterministic flag-on-death via a new `Stop` hook + 6h no-activity threshold, checked live on `GET /mode/dev`), per-job "resume" launch + new-build flow in the frontend. Closes the two gaps nightshift's own build exposed — no job ever got created, and `flagged` was silently dropped when syncing to `state.md` (2026-07-21)
- Nightshift infra: `backend/nightshift/{slack_surface,runner}.py` implement Scan (deterministic per-mode slack checks: dev's `flagged` jobs, settings' undistilled-lessons cursor) and Advance/Stage (dev is templated, settings borrows the distiller subagent via a real tool-scoped headless `claude -p` call); `scripts/nightshift_run.sh` + `launchd/com.noctis-os.nightshift.plist` wire it to a nightly launchd run. Closes out the locked Phase 3 build order (2026-07-21)
- Telemetry hooks: PostToolUse hook (`backend/hooks/log_action.py`) appends one action line per tool call to `backend/runtime/<mode>__<job>.log`; `PATCH /mode/{name}/jobs/{slug}` rewrites job-context frontmatter at stage transitions and syncs `state.md`; `GET /mode/{name}/jobs/{slug}/log` is the interface's poll target; ProfileOverlay's Faber job rows show a live last-action line (2026-07-21)
- Frontend tracker: `World.tsx` (real character sprites, live ambient state polling), `ProfileOverlay.tsx` (all five modes' locked card content), `api.ts` client, self-hosted fonts, `assets/` symlinked rather than duplicated. Fixed a missing-CORS bug and two sprite rendering bugs (opaque backgrounds, stray black column from a clamped-crop edge case) caught by actually running the app (2026-07-20/21)
- Backend: bearer-token + Origin auth, `vault_io.py` (frontmatter read/write, serialized writer for shared files), `GET /mode/{name}`, `POST /session/launch` (VS Code two-step for Dev, tinted Terminal.app + `CLAUDE_CONFIG_DIR` for the rest), nightshift inbox endpoints (2026-07-20)
- Mode folders: all five `second-brain/modes/<name>/` folders built (methodology, lessons, state, jobs, agents); `build-spine.md` migrated into `modes/dev/dev.md` as the one universal dev methodology (2026-07-20)
- Repo scaffolded: FastAPI + React/Vite, `.env.example`, `Makefile` (`setup`/`dev`), `SETUP.md` (2026-07-20)
- Spec drafted: Definition, PRD, EDD, Design Brief locked (2026-07-19/20)
