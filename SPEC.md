# Noctis OS — Spec

Compiled from the vault's Noctis OS scoping via the Phase 1 spec process in `second-brain/build-spine.md`. Definition, PRD, EDD, and Design Brief all locked 2026-07-20. **Phase 1 fully closed — Phase 2 setup is unblocked.**

**This file is the compiled architecture spec. The reasoning, discussion, and full decision history behind every point here lives in the vault, not duplicated in this repo:**
- `second-brain/wiki/Noctis OS/Overview.md` — architecture decisions, harness framing, effort estimate, tool evaluations
- `second-brain/wiki/Noctis OS/Modes.md` — all five modes designed in full via the seven/eight-part frame, character roster, subagent rosters, dev's ship-gate security step
- `second-brain/wiki/Noctis OS/Interface.md` — the world/character interaction model, profile overlay card system, per-mode content design, session launch surfaces, the state-schema contract
- `second-brain/wiki/Noctis OS/Improvement Loops.md` — the lessons-file/methodology-diff self-improvement mechanism
- `second-brain/wiki/Noctis OS/Decision Log.md` — chronological record of every decision, disagreement, and pushback across the whole build
- `second-brain/wiki/Agent Harnesses.md` — the Model+Harness concept underpinning the Definition below

If this file and the wiki ever disagree, the wiki wins for *why* a decision was made; this file wins for *what* the architecture currently is. Both should be updated together — a decision isn't done until both sides reflect it. **This is not optional — a decision made in chat and not written here doesn't exist for a fresh Claude Code session, which reads only this file and `CLAUDE.md`, nothing else.**

**Completeness pass run 2026-07-20:** a full re-check of every wiki page against this file found thirteen locked decisions/features that existed in the wiki with zero trace here — not descoped, just never pulled in. All thirteen are folded in below. See the Decision Log for the full list of what was missing and why the earlier contradiction-only lint runs didn't catch it. Treat "in the wiki" and "in this file" as two different, both-required states from now on — checking one is not checking the other.

---

## Definition

**What:** Noctis OS generalizes the existing dev-only build-spine into five modes — Dev, Learn, Research, Settings, Nightshift. Each mode is a folder in the vault (`second-brain/modes/<name>/`) containing its methodology file, its own accumulating lessons file, its subagent definitions, and its state/job files (see EDD for the full breakdown — this structure is new as of the completeness pass). A local web app (stateless FastAPI backend + React frontend, nothing deployed, vault as the only database) tracks mode state and launches Claude Code sessions with the active mode's methodology + working context preloaded — that per-session injection is the orchestration.

**Framing: Noctis is a harness, not just an OS.** Agent = Model + Harness — the harness is everything wrapped around a model that isn't the model itself (system prompt, tools, context management, orchestration). Claude Code is a harness around Claude. Noctis OS sits one layer up: it decides *which* harness configuration — mode methodology file, toolset, subagent roster, working context — gets injected into a Claude Code session, and when. "OS" is the right metaphor for the always-on world/character interface; "harness" is the more precise word for what mode-switching actually does underneath. Full concept and supporting research: `wiki/Agent Harnesses.md`. This framing carries a concrete build constraint: mode files should stay tight, legible loops rather than accreting machinery — a benchmark (Harness-Bench) found a lightweight harness beat a heavier, more elaborate one on identical tasks with the same model. Same principle as this project's own "simplicity wins."

**The same framing applies to continuity, not just architecture.** A Claude Desktop chat carries memory across a whole conversation, which can feel like "the system remembering" — it isn't. Noctis OS itself only knows what's written into a file a session reads at launch. A decision that only exists in a chat transcript is invisible to every future session. This is why the rule above ("if chat and spec disagree, write it down immediately") isn't bureaucratic overhead — it's the actual mechanism by which anything persists at all. **The completeness gap this file just closed is the same failure mode at a longer time delay** — decisions made and written to the *wiki* correctly, but never carried into *this* file, are just as invisible to a fresh Claude Code session as decisions left only in chat. Both halves have to be checked.

**Who for:** single-user, single-machine. No auth, no multi-tenancy.

**Why:** `~/.claude/CLAUDE.md` currently hardcodes dev process into every session regardless of what kind of work is actually happening (learning, researching, building, maintaining). Noctis OS makes mode-switching structural instead of manually held context.

**Success criteria:** `make setup` gets a fresh Mac to running in under 10 minutes (tested once, not aspirational). Every mode's character shows live ambient state at a glance. A mode switch is a launcher action from a character's profile, not a manual context reload. Every mode is genuinely smarter session over session, without waiting on a human-gated methodology change to make that true (the lessons tier). Every mode fails visibly, small, and recoverably rather than silently (the failure-behavior element).

---

## PRD

### Core features (must-haves)

- **Persistent world screen** — single scene, no routing, five character sprites idling in fixed designated spots on a locked peak-dusk cloud-bed backdrop (see Design Brief). **Always fills the window, no letterboxing (locked 2026-07-21, third pass):** `.world` is `width:100vw; height:100vh` with the backdrop stretched (`background-size:100% 100%`, not `cover`) so every pixel maps proportionally regardless of window shape — the earlier fixed-1376×768-canvas pass (previous entry, superseded) letterboxed on any window that wasn't exactly that size, which read as "doesn't fill full screen." The real constraint underneath all three passes was always "sprite size and position must never drift apart from the background," never "don't scale" — stretch-fill satisfies that without needing to give up filling the window.
- **Ambient state per character** — each sprite reflects its mode's live state at a glance (busy/idle, count badges where relevant). Sourced from each mode's `state.md` (see EDD's new "State files and the state-schema contract" section) — no new data, a rendering of state already tracked.
- **Profile overlay** — click a character → panel opens over the world, world stays mounted underneath. Full card content design locked — see `wiki/Noctis OS/Interface.md`.
- **Session launch from profile** — the only way a Claude Code session starts. Launcher injects that mode's methodology file + lessons file + working context into the session. Launch button always present, permanently tinted in the character's own color. Launch surface is mode-specific — four modes open Terminal.app with a character-tinted background, Dev opens VS Code.
- **Five modes fully built** — Dev, Learn, Research, Settings, Nightshift — each wired to real vault reads/writes per the methodology in `wiki/Noctis OS/Modes.md`.
- **Subagent roster per mode (was entirely missing from this file until 2026-07-20).** Subagents are `.claude/agents/*.md`-style scoped workers, cheap and narrowly permissioned, colocated at `modes/<name>/agents/*.md`. Locked v1 rosters:
  - **Dev:** critic (spec-compliance review, can't write code), code-review plugin, refactor tooling (low priority).
  - **Learn:** quizmaster (generates retention checks), gap-finder (probes what's actually understood vs. assumed).
  - **Research:** credibility-checker (isolated source-check pass), synthesizer (merges findings into vault pages, touches nothing else).
  - **Settings:** lint-runner (the vault health-check operation as a scoped worker), distiller (reads lessons files, drafts diff candidates, touches nothing).
  - The anti-sprawl test governs additions: before adding a new mode, ask "is this just a subagent of an existing mode?"
- **Skills-absorb-upward mapping (was missing).** Existing skills fold into the new mode system rather than staying standalone: `teach` → learn mode's spine, `ingest` → research mode's intake stage, `rationalise` + `vault-capture` → cross-mode utilities any mode can invoke. Not new capabilities — a migration of what already exists.
- **Failure behavior, per mode (was missing as a general feature — only Faber's specific case had been mentioned in chat).** Every mode declares: what happens when a session of it dies or hangs (job marked stale-and-flagged in the interface, never silently frozen), what retries are allowed, what escalates to the inbox. Mundane failure is designed, not just malicious failure.
- **Escalation via confidence flag (was missing).** Beyond binary staged/free, inbox proposals can carry a confidence flag — a third state ("done, but unsure — look at this one") so morning review sorts rubber-stamps from real reads. Applies especially to nightshift and the synthesizer subagent.
- **Library catalog (was missing entirely).** A vault-native catalog of vetted dependencies — what it is, when to reach for it, verdict provenance — supplied by research mode's adopt-track verdicts. A `libraries:` field in job-context frontmatter; the launcher injects it so dev sessions start knowing their approved stack. Interface gains a catalog browse view. Standing rule: dev sessions shop from the vetted shelf first. **Distinct from Design Lodge below — this one is vetted code dependencies, not design assets. Not to be conflated.**
- **Design Lodge (Overhaul, added 2026-07-24) — a vault-native, browsable and editable catalog of design assets** (components, layouts, palettes, typography, icons, animation patterns), organized by category: Interactables (buttons, modals/overlays, data display — folded together rather than split further), Navigation, Hero section, Typography, Color themes/palette, Icons, Animation patterns. Cross-project (`second-brain/design-lodge/`, not scoped to noctis-os — every future Faber build reads the same shelf), seeded retroactively from already-shipped projects. Absorbs the "Personal 21st.dev Library" habit (see `wiki/Tooling Decisions.md`) — presets/components sourced from 21st.dev and similar sites get pulled in here instead of saved externally. Per entry: name, category, tags, source, code (or its core logic) and/or reference (screenshot + note) — whichever's smarter for that entry — plus which projects it's been used in. Browse view shows a visual preview only by default, expands to reveal code/source/tags; tag search alongside category browsing; a staleness/superseded-by flag carries lineage across a pattern's evolution, not just a boolean. Standing rule: check the Lodge first, but infer fresh from the Design Brief's current theme rather than stalling if nothing fits. Lives as a new tab inside Faber's profile overlay — reachable any time the Interface is open, independent of an active dev session.
- **Design Lodge's quick-capture inbox** — a low-friction path inside the Lodge tab: paste a link + short note, sorting deferred. Opportunistic, non-blocking housekeeping at the start of any Faber dev session processes pending items (visit link, decide code-vs-reference, categorize, file, mark processed); a dead or ambiguous link gets flagged and skipped rather than stalling the session.
- **Design Brief gains a Lodge-aware reference step (Overhaul, added 2026-07-24).** Stage 1.2 gets a second reference-gathering path — custom media (video/images supplied directly), alongside manual web browsing — and a new "Lodge entries considered/used" subsection. Palette/typography reuse is checked at Design Brief time too, not just component-picking at Build time. The Playwright final-approval gate (3.0) gains a design-consistency check confirming shipped screens match what the Design Brief locked/referenced.
- **Deploy security review — dev mode's ship gate step 9 (was missing).** Before anything deploys: deterministic dependency audit (`npm audit`/`pip-audit`, always) → code-review plugin on the full diff with a security lens → CodeRabbit on the PR for anything public-facing or user-data-handling. Nothing deploys unreviewed.
- **Token audit — one of settings mode's explicit capabilities (was missing from the feature list, though implied elsewhere).** What loads into sessions without earning its cost, audited by Custos alongside drift and vault-health audits.
- **Spec-completeness audit (added 2026-07-20, same day this rule was needed for real).** Custos can diff a project's wiki/planning pages against its compiled spec and flag anything discussed and locked but never pulled in — the exact check that was missing when this very file turned out to be missing thirteen features. Applies to Noctis's own `SPEC.md` too, not just projects Noctis builds.
- **Per-mode self-improvement loop (two-tier — see `wiki/Noctis OS/Improvement Loops.md`):**
  - **Lessons tier, automatic, no gate.** Every mode owns a lessons file. Sessions append freely at close and load it at start. This is data, not methodology.
  - **Methodology tier, human-gated.** Settings mode (Custos) periodically digests accumulated lessons across all modes and drafts *proposed diffs* to a mode's methodology file, staged in the inbox with the specific lesson entries that motivated each diff. Shayne accepts or rejects. No mode ever rewrites its own live methodology file.
  - **Security mitigation (was missing).** The lessons tier is a named memory-poisoning vector — auto-written and auto-loaded means poisoned external content could persist into every future session of a mode. Mitigated by: a strict lessons-entry format, settings mode's distillation doubling as a review pass, the standing rule that all external content is data-being-analyzed and never instructions, and nightshift staying fully staged.
- **Vault as sole database** — backend stateless, no separate persistence layer, no ORM, no migrations.
- **Session telemetry** — Claude Code hooks append one line per tool action to a per-job runtime status file (not the vault — see EDD); job-context frontmatter updates at stage/track transitions. Interface polls/streams these files.
- **Deterministic-where-possible (was missing as a stated rule).** Recall-bank date math, staleness detection, health checks, and git commits are backend code, never left to session judgment.
- **Nightshift** — scheduled/triggerable slack-picker, staging-inbox-only writes, propose-never-commit. In v1, first on the degrade-gracefully list under build pressure.
- **Nightshift's slack-surface mechanism (was missing).** Each mode declares what it considers pending/undone and safe for unattended pre-work (learn: due recall items; research: parked triggers + standing sweeps; settings: undistilled lessons, overdue audits; dev: flagged-not-frozen jobs only). This is nightshift's tap-in contract — no hardcoded per-mode knowledge lives in nightshift itself.
- **Nightshift inbox review lives inside Echo's profile** for v1 — no launch button on Echo's card, review happens per-item. **Echo's card also carries a collapsible History section (added 2026-07-22)** — a deliberate, flagged exception to the Faber/Custos idle-state-instead-of-History rule (Design Brief/Interface), since accepted/rejected proposals were durably recorded (`log.md`, `modes/nightshift/archive/<slug>.md`) but never reachable from the app itself. `GET /nightshift/history` parses `log.md`'s decision-line format (most recent first); `GET /nightshift/archive/{slug}` returns the full archived proposal text.
- **Per-mode default model + per-job launch override** — Claude family only in v1. Deliberate routing at launch, never silent mid-task fallback.
- **`make setup` / `make dev`** — single repo, fresh-Mac-to-running in under 10 minutes, both processes started together.

### Out of scope (explicit)

- Career mode
- Full PTY terminal mirroring (v2 reference exists via octogent, not built)
- Idle roaming/movement and the full expression library (v2) — **partially superseded 2026-07-21**: busy/idle status is now told through swapping which extracted expression is showing (a "sleepy" vs. an "active/working" sprite per character) instead of a separate status-dot indicator, Shayne's direct call. Idle *roaming* (characters moving around the scene) and the rest of the expression set beyond one busy/idle pair per character stay v2.
- Noctis-as-MCP-server (parked; concrete trigger not yet named — see Open Questions)
- Tauri desktop wrap — **superseded 2026-07-21, moved into v1, built with pywebview instead of Tauri.** Shayne's direct call: a native window matters, but Tauri's Rust toolchain doesn't buy anything for a single-user local tool with no distribution need. `make app` opens a frameless pywebview window wrapping the same backend/frontend, hot-reloading from the same dev servers `make dev` starts. See `desktop/README.md` for the real bug this surfaced (subprocess-tree cleanup) and how it was fixed and verified. Custom app icon needs a bundler pass (`py2app`/`PyInstaller`) — that part is still a follow-up, not done yet.
- Any deployment — local-only
- Multi-user/auth of any kind
- A separate global cross-mode inbox view
- Cross-vendor model routing (non-Claude backends) — v2, named mechanism is a LiteLLM local proxy via `ANTHROPIC_BASE_URL`, gated on tool-calling reliability proof for the specific job shape
- In-app history views for Faber and Custos — idle states instead (see Design Brief)
- shadcn — not adopted for this project, see Design Brief (derived fact, not a rule)
- Design Lodge: a per-entry adaptation-notes field (considered during the Overhaul brainstorm, dropped)
- Design Lodge: generalizing beyond design assets into other dependency types — that's the separate Library catalog feature above, not to be merged in
- Design Lodge: blocking dev-session start on a non-empty quick-capture inbox — opportunistic only, never a gate

### User flows

1. **Cold start** — open the app → world loads → all five characters idle in their spots, ambient badges reflect current state.
2. **Start a session** — click a character → profile overlay opens (typewriter reveal) → review live state/context → launch (optionally overriding the mode's default model) → session opens in the mode's launch surface with methodology + lessons file + working context preloaded → telemetry action feed populates live in the profile.
3. **Check without starting** — click purely to see state → close overlay → back to world, nothing launched.
4. **Session close** — session appends to its mode's lessons file before ending — no gate, happens every time.
5. **Session failure** — job marked stale-and-flagged in the interface (never silently frozen); mode-specific retry/escalation rules apply.
6. **Nightshift review** — open Echo's profile → staged inbox items, each optionally carrying a confidence flag → accept/reject individually.
7. **Methodology diff review** — Custos digests accumulated lessons → drafts a proposed methodology diff with evidence → staged in the inbox → Shayne accepts or rejects.
8. **Mode-to-mode handoff** — e.g. research's inquiry track flags "worth a learn session" → close Vesper's profile → open Noctua's → topic already queued.
9. **Design Lodge browse/edit, no session** — open the Interface → Faber's profile → Lodge tab → browse by category or search tags → expand an entry for code/reference/source, or add/edit one directly via a plain form. No Claude Code session required.
10. **Design Lodge quick capture** — same tab, paste a link + short note into the inbox, close the Interface. Sorting deferred.
11. **Design Lodge session-start housekeeping** — next Faber dev session starts, opportunistically processes any pending inbox items before its own task; flags dead/ambiguous links rather than stalling.
12. **Design Lodge in Plan/Build/Ship** — Plan: browse before gathering fresh references or amending a Design Brief section. Build (3.0): check first → shadcn/Magic MCP/fresh-inference fallback → save new keepers back immediately. Ship: consistency check confirms shipped screens match what was locked/referenced, catches anything not yet saved back.

---

## EDD

### Architecture overview

Two local processes, one repo, nothing deployed:

- **Backend** — FastAPI, stateless. No ORM, no migrations, no auth layer beyond bearer-token + Origin checking. Every endpoint reads or writes vault files directly on disk and returns state.
- **Frontend** — React + Vite, single persistent scene (the world), no router. Character sprites render as static PNGs; profile overlay mounts/unmounts over the world without unmounting it.
- **Session launcher** — backend endpoint that constructs the mode's invocation (methodology file + lessons file + working context + model flag) and opens it in that mode's designated launch surface.
- **Hooks** — Claude Code hooks append action lines to a per-job runtime status file (see "State files" below — this is explicitly NOT a vault file) on tool-use events; job-context frontmatter rewrites at stage transitions.
- **Nightshift** — runs via **launchd**, a constrained subset of subagents against each mode's declared slack surface, writing only to a staging inbox directory. Tool allowlist enforced.

### State files and the state-schema contract (locked here 2026-07-20 — was completely missing; this is the file the entire interface actually reads)

The interface can only render what's structured. Per mode:

- **`second-brain/modes/<name>/state.md`** — lightweight index: current jobs and their statuses, ambient-state fields (due counts, etc., excluding busy — see the Runtime scratch bullet below) as YAML frontmatter. **This is what the profile overlay and world ambient badges actually read** — not every job file individually. Contract-first: this frontmatter shape is locked before any card is built against it.
- **`second-brain/modes/<name>/jobs/<job-slug>/context.md`** — per-job durable state (the "tentacle"/jobs-layer pattern): frontmatter for stage/track/last-touched/one-line-status, freeform prose below. One mode can hold several jobs at once (Faber's multi-build case is the clearest example).
- **`second-brain/modes/<name>/agents/*.md`** — subagent definitions, colocated per mode (see PRD's subagent roster feature).
- **`second-brain/modes/<name>/lessons.md`** — accumulating lessons (below).
- **Runtime scratch, explicitly NOT the vault:** hook-driven action-feed logs (one line per tool action, high-churn, ephemeral) live in a gitignored backend runtime folder, e.g. `noctis-os/backend/runtime/<job-id>.log` — not in `second-brain/`. Durable job state (`context.md`) is vault-worthy; raw session noise is not. This split was adopted from octogent's own runtime/durable-context separation and had never been given a concrete path before this pass. **`busy` is also runtime scratch, not vault content (locked 2026-07-22):** each mode's live busy/idle status lives at `backend/runtime/<mode>.busy` (`busy_marker.py`), set by `POST /session/launch` and cleared by the `Stop` hook — never a `state.md` frontmatter field. A running session freely rewrites its own `state.md` via its own Edit-tool calls and has no way to know `busy` must be preserved, so `GET /mode/<name>` always overrides whatever value happens to sit in the vault file with the runtime marker's value.

### Per-mode lessons files

- **Location: `second-brain/modes/<name>/lessons.md`**, colocated with the mode's methodology and state files.
- **Write path:** any session appends at close — no gate, no serialized-writer requirement, since each mode's lessons file has exactly one writer-type even under parallel sessions.
- **Read path:** the launcher preloads it alongside the methodology file and working context.
- **Consumption:** Custos scans `modes/*/lessons.md` during its Audit stage, drafts proposed methodology diffs with specific lesson entries cited as evidence, stages them in the inbox. Settings mode keeps its own lessons file at `modes/settings/lessons.md` — recursive, deliberately.
- **Guardrail unchanged:** lessons accumulate freely; methodology only changes via this staged, human-gated path.
- **Inbox proposal format (added 2026-07-20 — was underspecified: "cites evidence" didn't say where the evidence or the diff itself actually live).** Each staged item is indexed in `modes/nightshift/state.md`'s `inbox` array (`slug`, `origin_mode`, `description`, `rationale`, `confidence`, `staged_at`) with full content in `modes/nightshift/inbox/<slug>.md` — see that folder's `README.md` for the exact three-part shape (plain-language rationale, the diff, cited evidence). The `rationale` field is mandatory: a proposal is not staged until it has a plain-English "what changes and why" line, not just a diff plus a citation Shayne would otherwise have to go read to understand.

### Session launch surfaces, per mode

- **Learn, Research, Settings, Nightshift → macOS Terminal.app.** Launcher opens a new Terminal.app window via `osascript`, sets background to a darkened/desaturated version of the character's locked hex (HSL lightness ~15-20%, hue preserved), sets window title to `{character} — {mode} — {current job/topic}`. Terminal.app has no separate "border" — window chrome is OS-drawn — so background tint is the real equivalent of the original colored-border idea. **The `claude` invocation for these four is launched with `CLAUDE_CONFIG_DIR` set to `noctis-os/backend/launch_config/nondev/`** — see "Mode files + CLAUDE.md migration" above — so these sessions get a minimal universal CLAUDE.md instead of Dev's full methodology.
- **Session-start callouts get a second delivery channel: `--append-system-prompt` (locked 2026-07-22).** A mode's methodology file can carry a `> **SESSION START...` blockquote (e.g. Vesper's/Noctua's track question, dev.md's Patch/Overhaul marker); `session_prompt.py` extracts it at launch time and passes it through `launch_terminal`'s `system_prompt` argument into `claude --append-system-prompt`, additive to (not replacing) the full methodology text still going into the first user turn. Added after a live reliability gap: an ordinary user message, however explicit, doesn't reliably carry the same instruction-following weight as a genuine system-level directive once followed by thousands more characters of reference material.
- **Dev → VS Code**, via Claude Code's VS Code extension. Two-step launch: `code <project-path>` first, then `open "vscode://anthropic.claude-code/open?prompt=<url-encoded methodology+context>"`. No `CLAUDE_CONFIG_DIR` override — Dev wants the default `~/.claude/CLAUDE.md` → `modes/dev/dev.md`, and the VS Code extension doesn't respect the env var regardless.
- **VS Code localhost preview** — `workbench.browser.openLocalhostLinks`, a global VS Code user setting (not per-repo), routes localhost links into VS Code's Integrated Browser. One-time manual step in `SETUP.md`.

### Mode files + CLAUDE.md migration

- Mode folders live at `second-brain/modes/<name>/` (dev, learn, research, settings, nightshift) — methodology (`<name>.md`), lessons (`lessons.md`), state (`state.md`), jobs (`jobs/<slug>/context.md`), agents (`agents/*.md`).
- `build-spine.md` **becomes** `modes/dev/dev.md`.
- Sequenced as the first build milestone: **mode folders (methodology + lessons + state + agents) → backend → frontend tracker → telemetry → nightshift.**
- **Mode folders: done (2026-07-20).** All five `second-brain/modes/<name>/` folders built: methodology file, `lessons.md`, `state.md` (seeded with the locked frontmatter contract per mode), `jobs/` (empty, ready for real jobs), `agents/*.md` (all seven v1 subagent stubs). `build-spine.md` retired; `~/.claude/CLAUDE.md` symlinks directly to `modes/dev/dev.md`.
- **Telemetry hooks: done (2026-07-21).** `backend/hooks/log_action.py` is the PostToolUse hook, appending one action line per tool call to `backend/runtime/<mode>__<job>.log` (per the "Runtime scratch" split above). `launch_surfaces._merge_hook()` registers it idempotently without clobbering Claude Code's own generated settings keys: Terminal.app launches get a static, env-var-driven hook in `launch_config/nondev/settings.json` (job identity via per-window `NOCTIS_MODE`/`NOCTIS_JOB_ID`, so concurrent nondev sessions sharing that one settings file never race on whose job gets logged); Dev/VS Code launches get a per-project hook with `--mode`/`--job-id` baked into the command in `<project_path>/.claude/settings.local.json`, since the URI-handler launch doesn't carry shell env. `PATCH /mode/{name}/jobs/{slug}` handles the other half — job-context frontmatter rewrites at stage/track transitions, syncing the mirrored entry in `state.md` — and `GET /mode/{name}/jobs/{slug}/log` is the interface's poll target, wired into Faber's job rows as a single live last-action line. **Two liveness/attribution fixes landed 2026-07-24:** the busy marker is now touched on every tool call via the `PostToolUse` hook, not only at launch, so a long-running session no longer self-reports idle past its original 6h staleness window; and both `log_action.py` and `mark_session_end.py` now prefer a session's own `NOCTIS_MODE`/`NOCTIS_JOB_ID` environment over the args baked into a project's `settings.local.json`, since Claude Code applies that file by working directory regardless of which mode actually launched the session — without this, a settings session working inside `noctis-os` could have its own exit misattributed as a dev session's.
- **Dev job lifecycle gaps closed (2026-07-21) — found by dogfooding the nightshift build.** Nightshift's dev flagged-job check had nothing to ever find: no mechanism created a job in the first place (Interface.md's "launch stays available even idle, since that's how a new build starts" had no actual implementation), and nothing ever set `flagged: true` on a dead session. Fixed: `POST /mode/{name}/jobs` creates a job (`context.md` + synced `state.md` entry); `_sync_state_job_entry` also fixed to mirror `flagged` into `state.md`, which it was silently dropping. Flagging is a new `backend/staleness.py`, dev's own domain (nightshift only ever reads the field) — a job is flagged when its last activity (runtime log or `last_touched`) exceeds a 6-hour threshold *and* it never got a `SESSION_END` sentinel, written by a new `Stop` hook (`backend/hooks/mark_session_end.py`, registered alongside the existing `PostToolUse` telemetry hook) on clean exit. The staleness check runs inline on `GET /mode/dev`, already polled every 15s by the World screen, so a dead session surfaces live rather than waiting for nightshift's nightly sweep. Frontend: Faber's job rows get a per-job "resume" launch (Dev can hold several simultaneous jobs, so the one shared card-chrome launch button can't express "resume job B"); the idle-state button becomes "start a new build" (currently a `window.prompt` placeholder for name/path, not a designed input) and the bottom button relabels to "+ NEW BUILD" once jobs exist. This repo's own build was registered as a real job (`noctis-os`, stage Build) via the new endpoint.
- **Nightshift infra: done (2026-07-21) — last item on the build order.** `backend/nightshift/slack_surface.py` is the Scan step, one checker per mode (`SLACK_CHECKS` registry — nightshift.md's tap-in contract, no hardcoded per-mode knowledge in nightshift itself). Real checkers for dev (a new optional `flagged` field on job-context frontmatter, per dev's deliberately near-empty slack surface) and settings (undistilled lessons via a `lessons_distilled_through` line-count cursor on `modes/settings/state.md`); learn/research are registered but honestly return empty — no real due-recall/parked-trigger data model exists yet. `backend/nightshift/runner.py` is Advance + Stage: dev's advance is a fully mechanical templated status note (never code/branch content); settings' advance genuinely borrows the distiller subagent at reduced permission via a real headless `claude -p` call, tool-scoped to Read/Grep plus Write on exactly one inbox file, no Bash/network. Stage is idempotent against already-pending items (matched on slug's stable prefix, not its date stamp) and parses `rationale` out of the drafted proposal rather than drafting it twice. `scripts/nightshift_run.sh` (previously a TODO stub) now invokes it for real; `launchd/com.noctis-os.nightshift.plist` schedules a nightly 03:00 run, load/unload steps in `SETUP.md`. Smoke-tested live end-to-end including one real distiller call, which caught and fixed a genuine bug: an empty cursor treated every mode's still-boilerplate `lessons.md` as undistilled, which would have spent a real API call every night for nothing — cursor is now seeded to each file's actual current line count.
- **Faber new-build scratch-directory mechanism (2026-07-23).** A brand-new build's session starts in a temporary scratch directory with no project name locked yet (per dev.md's Stage 1.1); `POST /mode/{name}/jobs` auto-creates that scratch directory, and `PATCH /mode/dev/jobs/{slug}` with a new `project_path` moves the directory on disk and updates the job record in one call — the first action of Setup (dev.md Stage 2). `NewBuildModal` simplified accordingly (no upfront project-path field).
- **`~/.claude/CLAUDE.md` residue — fully resolved (2026-07-20, second pass).** The symlink stays pointed at `modes/dev/dev.md` unchanged — correct for Dev-mode launches and any ad hoc terminal `claude` use in Shayne's other projects, since those are all dev-mode work. For Learn/Research/Settings/Nightshift launches specifically, the launcher sets the `CLAUDE_CONFIG_DIR` environment variable (undocumented by Anthropic but confirmed CLI-respected — redirects which directory Claude Code reads its config/CLAUDE.md from) to `noctis-os/backend/launch_config/nondev/`, which holds a minimal universal-rules-only `CLAUDE.md` (vault write discipline, communication style, session-close lessons-append reminder — nothing dev-specific). Per-process env var, so it's safe under the locked parallel-sessions requirement (no shared-file race, unlike the alternative of renaming the real file in and out). Known limitation: the VS Code extension doesn't respect `CLAUDE_CONFIG_DIR` — irrelevant here since Dev launches via VS Code and wants the global file anyway; only the four Terminal.app/CLI launches need the override, and the CLI does respect it.

### Design Lodge (Overhaul, added 2026-07-24)

- **Storage:** `second-brain/design-lodge/`, vault-level (not per-project), category-organized. Each entry is a vault-native page — frontmatter: `name`, `category`, `tags`, `source`, `projects_used`, `superseded_by`; body: a code block and/or a reference description, whichever fits the entry.
- **Preview images (added 2026-07-24, second pass).** Browse-first (per the Design Brief) needed an actual visual, not just code/reference text. First binary vault content — `second-brain/design-lodge/entries/<slug>.png`, read/written via new `vault_io.read_binary`/`write_binary` helpers. `POST /entries/{slug}/preview` (base64 upload) and `GET /entries/{slug}/preview` (serves the PNG, `image/png`); list/get responses carry a computed `has_preview` bool so the frontend doesn't fire a request per entry against ones with none. Frontend fetches the image as an authenticated blob (`fetch` + bearer header, `URL.createObjectURL`) — never a token in an `<img src>` query string.
- **Inbox:** a separate pending queue for quick-capture (`link` + `note`), processed opportunistically at the start of any Faber dev session — not a blocking gate. A dead or ambiguous link gets flagged and skipped, not stalled on.
- **Backend:** new router (`backend/routers/design_lodge.py`) — CRUD for entries plus the inbox queue (add/list/mark-processed), same mandatory bearer-token + Origin-check auth as every other route.
- **Frontend:** new tab inside `ProfileOverlay.tsx`'s Faber card — category-filtered grid of visual previews (image-first, expand-to-reveal-detail), a minimal capture form (link + note), and a fuller add/edit form (code, image, tags, category). Reachable any time the Interface is open, independent of any active dev session — the Interface is a persistent app, sessions are fire-and-forget launches from it.
- **Session integration:** `modes/dev/dev.md` gains three stage touchpoints (Plan: browse before gathering references / amending a Design Brief section; Build 3.0: check-first → fallback → save-back; Ship: consistency check) plus the opportunistic inbox-processing pass at session-bootstrap, same tier as the existing resumed-job track check.
- **Distinct from the Library catalog** (PRD, above) — that one is vetted code dependencies fed by Vesper's research verdicts; Design Lodge is design assets (components, layouts, palettes, typography, icons, animation), fed by Faber's own build/capture flow. Two separate vault directories, two separate concerns, not to be conflated.

### Version control workflow

**Claude Code commits as work progresses.** Shayne pushes manually — matches Portfolio Platform, not Articulation Loop's fully-manual-commits rule.

### Stack and justification

- **FastAPI** — stateless-by-design fits "vault is the database."
- **React + Vite** — component/dependency sourcing follows the derivation rule below.
- **What gets installed in Phase 2 setup is derived from this file, not hardcoded.** Setup installs exactly what this Stack section and the Design Brief declare, plus whatever's globally always-on (Impeccable). Nothing is excluded by a blanket rule. Currently declared: **Tailwind + Impeccable. No shadcn** — not forbidden, just not needed here (see Design Brief).
- **No database** — vault files ARE the persistence layer.
- **Sprites** — PIL-rendered PNGs from grid-data text files. `assets/characters/` is the sole source of truth.
- **World background** — a static illustrated plate, hand-picked footing coordinates. See `assets/world/README.md`.
- **Profile overlay** — Press Start 2P (header) + JetBrains Mono (body); typewriter-reveal entrance; fixed card height across four modes, Echo and Faber the exceptions (auto-height, wider, viewport-capped — Faber's added 2026-07-24 for the Design Lodge tab's browse grid/forms, same reasoning as Echo's inbox). 100% hand-coded CSS.

### Decisions locked during EDD

- **Nightshift execution mechanism: launchd.**
- **Vault access: direct filesystem read/write, no istefox/MCP dependency.** Tradeoff accepted (loses Obsidian's metadata cache, semantic search, Dataview) — none of v1's methodology needs any of it. Trigger to revisit: research's synthesizer wanting semantic recall.
- **istefox stays required for the Claude Desktop workflow** — only removed as a Noctis OS backend dependency.
- **Overlay chrome: zero shadcn, project-specific outcome, not a standing rule** (see Stack, Design Brief).
- **Backend auth is mandatory** — bearer-token + Origin checking on every route, localhost binding alone is not sufficient.
- **Model routing: per-mode-default + per-job-override, Claude-family only in v1.** Cross-vendor stays v2 (LiteLLM proxy mechanism named, not built), gated on proven tool-calling reliability. A model's *availability* (e.g. Kimi K3) never implies safety — see `wiki/Agent Harnesses.md`.
- **Nightshift gets a tool allowlist**, staging-inbox writes only, minimal bash, no network by default.
- **No secret values ever written to the vault.**
- **Serialized write path for shared vault files** (`log.md`, `index.md`) — a single backend writer. Per-mode lessons/state/job files don't need this (one writer-type each).
- **Sessions run in parallel across modes** — a mode is methodology + view focus, never an execution lock.
- **In-app History for Faber and Custos: rejected in favor of idle states.**
- **Deterministic-where-possible:** recall-bank math, staleness detection, health checks, git commits are backend code, never session judgment.
- **Personal 21st.dev Library superseded by Design Lodge (2026-07-24).** The external, 21st.dev-hosted "components you like" library (`wiki/Tooling Decisions.md`) is replaced by the vault-native Design Lodge — sourced components now get pulled into `second-brain/design-lodge/` instead of saved externally.

### File/folder structure (target — created at Phase 2)

```
noctis-os/
├── backend/
│   ├── main.py
│   ├── routers/          # mode.py, session.py, nightshift.py, design_lodge.py
│   ├── vault_io.py       # all vault read/write goes through here
│   └── runtime/           # gitignored — per-job hook action-feed logs, NOT vault content
├── frontend/
│   ├── src/
│   │   ├── World.tsx
│   │   ├── ProfileOverlay.tsx
│   │   ├── LibraryCatalog.tsx   # dev mode's vetted-dependency browse view
│   │   ├── DesignLodge.tsx      # Faber tab: design-asset catalog + quick-capture inbox
│   │   └── ...           # consumes assets/, holds no grid data or world-plate copies
├── assets/
│   ├── characters/        # SOLE source of truth: grid definitions + render script + generated PNGs
│   └── world/             # background plate(s) + footing-spot coordinates
├── scripts/
│   ├── setup.sh
│   └── nightshift_run.sh
├── Makefile
├── .env.example
└── SETUP.md
```

Vault side (not this repo): `second-brain/modes/<name>/` per mode — `<name>.md`, `lessons.md`, `state.md`, `jobs/<slug>/context.md`, `agents/*.md`. Also `second-brain/design-lodge/` — vault-level, not per-mode (see EDD's "Design Lodge" section).

### External dependencies

Claude Code CLI, the Claude Code VS Code extension, PIL, a Python frontmatter/YAML library, Google Fonts, macOS `osascript`, Impeccable (global), pywebview (native desktop window, added 2026-07-21). No shadcn currently declared. No other services, no MCP servers at runtime.

### Prerequisite — done (2026-07-20)

**Git for the vault.** Done.

---

## Design Brief — locked 2026-07-20

**World backdrop, character art, interface chrome:** all locked, full detail in `wiki/Noctis OS/Interface.md` and `Modes.md`, palette/coordinates in `assets/world/README.md` and `assets/characters/README.md`.

**Component sourcing — no shadcn, fully hand-built, and this is a derived fact, not a rule.** Every element of the card system fought the pixel-art/world aesthetic enough to warrant hand-building. Setup installs whatever the Stack section declares — currently that's Tailwind + Impeccable, no shadcn — because nothing here needed it, not because of a standing ban. A different project's Design Brief could resolve the other way.

**Design Brief is complete.** Remaining items are asset-production tasks: two touch-ups on the background image, a composite scale test. Custos's trigger thresholds — done (2026-07-21): `backend/triggers.py` computes friction/accumulation/suspicion live on every `GET /mode/settings` poll (accumulation reuses nightshift's undistilled-lessons cursor signal; friction is an opt-in `FRICTION:` marker in a mode's lessons.md, documented in each mode's lessons.md; suspicion is a 7-day state.md staleness check).

**Design Lodge tab — locked 2026-07-24 (Overhaul amendment, not a rewrite of the above).** New tab inside Faber's existing profile-overlay chrome — same paper/accent-border/pixel-font language as the rest of the card system, Faber's warm red (`#E53311`) as the tab's accent. Grid-of-previews browsing, image-first, expand-to-reveal-detail. Category filter chips: Interactables, Navigation, Hero section, Typography, Color themes/palette, Icons, Animation patterns. Quick-capture inbox visually separated from the main browse grid, deliberately minimal (link + note only) to keep free-time capture low-friction. Faber's card gains the same fixed-card-height exception already granted to Echo (auto-height, wider, viewport-capped) — the default 420×360 card was too small for the browse grid plus forms.

---

## Open questions — genuinely unresolved, tracked here so they don't disappear (added 2026-07-20)

These are correctly undecided — not gaps to silently fill, decisions for Shayne to close when ready:

1. **Interface sub-name** — Deck / Bridge / Console / none.
2. ~~Exact residue of `~/.claude/CLAUDE.md` once the dev process moves out to `modes/dev/dev.md`.~~ **Resolved 2026-07-20** — see "Mode files + CLAUDE.md migration" (`CLAUDE_CONFIG_DIR` override for non-dev launches, minimal universal file at `noctis-os/backend/launch_config/nondev/CLAUDE.md`).
3. **Noctis-as-MCP-server's concrete trigger** — parked, no trigger condition named yet beyond "a session needs OS state and can't get it cleanly through files."
4. ~~Nightshift's scheduler mechanism (cron+headless / Cowork bridge / launchd) — EDD-time decision.~~ **Resolved 2026-07-21** — launchd, per "Decisions locked during EDD" and the "Nightshift infra: done" EDD entry (`launchd/com.noctis-os.nightshift.plist`, load/unload steps in `SETUP.md`). Left unstruck here until now — a completeness gap in this file's own Open Questions list, not a live disagreement.

---

## Phase 1 — CLOSED (2026-07-20)

Definition, PRD, EDD, and Design Brief all locked, including the thirteen items recovered in the 2026-07-20 completeness pass. Next: Phase 2 setup — GitHub repo, `.env.example`, project `CLAUDE.md`, folder structure, per `second-brain/build-spine.md`'s checklist.
