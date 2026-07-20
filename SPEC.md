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

- **Persistent world screen** — single scene, no routing, five character sprites idling in fixed designated spots on a locked peak-dusk cloud-bed backdrop (see Design Brief).
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
- **Library catalog (was missing entirely).** A vault-native catalog of vetted dependencies — what it is, when to reach for it, verdict provenance — supplied by research mode's adopt-track verdicts. A `libraries:` field in job-context frontmatter; the launcher injects it so dev sessions start knowing their approved stack. Interface gains a catalog browse view. Standing rule: dev sessions shop from the vetted shelf first.
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
- **Nightshift inbox review lives inside Echo's profile** for v1 — no launch button on Echo's card, review happens per-item.
- **Per-mode default model + per-job launch override** — Claude family only in v1. Deliberate routing at launch, never silent mid-task fallback.
- **`make setup` / `make dev`** — single repo, fresh-Mac-to-running in under 10 minutes, both processes started together.

### Out of scope (explicit)

- Career mode
- Full PTY terminal mirroring (v2 reference exists via octogent, not built)
- Idle roaming/movement and the full expression library (v2)
- Noctis-as-MCP-server (parked; concrete trigger not yet named — see Open Questions)
- Tauri desktop wrap
- Any deployment — local-only
- Multi-user/auth of any kind
- A separate global cross-mode inbox view
- Cross-vendor model routing (non-Claude backends) — v2, named mechanism is a LiteLLM local proxy via `ANTHROPIC_BASE_URL`, gated on tool-calling reliability proof for the specific job shape
- In-app history views for Faber and Custos — idle states instead (see Design Brief)
- shadcn — not adopted for this project, see Design Brief (derived fact, not a rule)

### User flows

1. **Cold start** — open the app → world loads → all five characters idle in their spots, ambient badges reflect current state.
2. **Start a session** — click a character → profile overlay opens (typewriter reveal) → review live state/context → launch (optionally overriding the mode's default model) → session opens in the mode's launch surface with methodology + lessons file + working context preloaded → telemetry action feed populates live in the profile.
3. **Check without starting** — click purely to see state → close overlay → back to world, nothing launched.
4. **Session close** — session appends to its mode's lessons file before ending — no gate, happens every time.
5. **Session failure** — job marked stale-and-flagged in the interface (never silently frozen); mode-specific retry/escalation rules apply.
6. **Nightshift review** — open Echo's profile → staged inbox items, each optionally carrying a confidence flag → accept/reject individually.
7. **Methodology diff review** — Custos digests accumulated lessons → drafts a proposed methodology diff with evidence → staged in the inbox → Shayne accepts or rejects.
8. **Mode-to-mode handoff** — e.g. research's inquiry track flags "worth a learn session" → close Vesper's profile → open Noctua's → topic already queued.

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

- **`second-brain/modes/<name>/state.md`** — lightweight index: current jobs and their statuses, ambient-state fields (busy/idle, due counts, etc.) as YAML frontmatter. **This is what the profile overlay and world ambient badges actually read** — not every job file individually. Contract-first: this frontmatter shape is locked before any card is built against it.
- **`second-brain/modes/<name>/jobs/<job-slug>/context.md`** — per-job durable state (the "tentacle"/jobs-layer pattern): frontmatter for stage/track/last-touched/one-line-status, freeform prose below. One mode can hold several jobs at once (Faber's multi-build case is the clearest example).
- **`second-brain/modes/<name>/agents/*.md`** — subagent definitions, colocated per mode (see PRD's subagent roster feature).
- **`second-brain/modes/<name>/lessons.md`** — accumulating lessons (below).
- **Runtime scratch, explicitly NOT the vault:** hook-driven action-feed logs (one line per tool action, high-churn, ephemeral) live in a gitignored backend runtime folder, e.g. `noctis-os/backend/runtime/<job-id>.log` — not in `second-brain/`. Durable job state (`context.md`) is vault-worthy; raw session noise is not. This split was adopted from octogent's own runtime/durable-context separation and had never been given a concrete path before this pass.

### Per-mode lessons files

- **Location: `second-brain/modes/<name>/lessons.md`**, colocated with the mode's methodology and state files.
- **Write path:** any session appends at close — no gate, no serialized-writer requirement, since each mode's lessons file has exactly one writer-type even under parallel sessions.
- **Read path:** the launcher preloads it alongside the methodology file and working context.
- **Consumption:** Custos scans `modes/*/lessons.md` during its Audit stage, drafts proposed methodology diffs with specific lesson entries cited as evidence, stages them in the inbox. Settings mode keeps its own lessons file at `modes/settings/lessons.md` — recursive, deliberately.
- **Guardrail unchanged:** lessons accumulate freely; methodology only changes via this staged, human-gated path.

### Session launch surfaces, per mode

- **Learn, Research, Settings, Nightshift → macOS Terminal.app.** Launcher opens a new Terminal.app window via `osascript`, sets background to a darkened/desaturated version of the character's locked hex (HSL lightness ~15-20%, hue preserved), sets window title to `{character} — {mode} — {current job/topic}`. Terminal.app has no separate "border" — window chrome is OS-drawn — so background tint is the real equivalent of the original colored-border idea.
- **Dev → VS Code**, via Claude Code's VS Code extension. Two-step launch: `code <project-path>` first, then `open "vscode://anthropic.claude-code/open?prompt=<url-encoded methodology+context>"`.
- **VS Code localhost preview** — `workbench.browser.openLocalhostLinks`, a global VS Code user setting (not per-repo), routes localhost links into VS Code's Integrated Browser. One-time manual step in `SETUP.md`.

### Mode files + CLAUDE.md migration

- Mode folders live at `second-brain/modes/<name>/` (dev, learn, research, settings, nightshift) — methodology (`<name>.md`), lessons (`lessons.md`), state (`state.md`), jobs (`jobs/<slug>/context.md`), agents (`agents/*.md`).
- `build-spine.md` **becomes** `modes/dev/dev.md`.
- `~/.claude/CLAUDE.md` shrinks to universal rules only; the launcher injects the active mode's methodology per session. **Exact residue contents not yet decided — see Open Questions.**
- Sequenced as the first build milestone: **mode folders (methodology + lessons + state + agents) → backend → frontend tracker → telemetry → nightshift.**

### Version control workflow

**Claude Code commits as work progresses.** Shayne pushes manually — matches Portfolio Platform, not Articulation Loop's fully-manual-commits rule.

### Stack and justification

- **FastAPI** — stateless-by-design fits "vault is the database."
- **React + Vite** — component/dependency sourcing follows the derivation rule below.
- **What gets installed in Phase 2 setup is derived from this file, not hardcoded.** Setup installs exactly what this Stack section and the Design Brief declare, plus whatever's globally always-on (Impeccable). Nothing is excluded by a blanket rule. Currently declared: **Tailwind + Impeccable. No shadcn** — not forbidden, just not needed here (see Design Brief).
- **No database** — vault files ARE the persistence layer.
- **Sprites** — PIL-rendered PNGs from grid-data text files. `assets/characters/` is the sole source of truth.
- **World background** — a static illustrated plate, hand-picked footing coordinates. See `assets/world/README.md`.
- **Profile overlay** — Press Start 2P (header) + JetBrains Mono (body); typewriter-reveal entrance; fixed card height across four modes, Echo the exception. 100% hand-coded CSS.

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

### File/folder structure (target — created at Phase 2)

```
noctis-os/
├── backend/
│   ├── main.py
│   ├── routers/          # mode.py, session.py, nightshift.py
│   ├── vault_io.py       # all vault read/write goes through here
│   └── runtime/           # gitignored — per-job hook action-feed logs, NOT vault content
├── frontend/
│   ├── src/
│   │   ├── World.tsx
│   │   ├── ProfileOverlay.tsx
│   │   ├── LibraryCatalog.tsx   # dev mode's vetted-dependency browse view
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

Vault side (not this repo): `second-brain/modes/<name>/` per mode — `<name>.md`, `lessons.md`, `state.md`, `jobs/<slug>/context.md`, `agents/*.md`.

### External dependencies

Claude Code CLI, the Claude Code VS Code extension, PIL, a Python frontmatter/YAML library, Google Fonts, macOS `osascript`, Impeccable (global). No shadcn currently declared. No other services, no MCP servers at runtime.

### Prerequisite — done (2026-07-20)

**Git for the vault.** Done.

---

## Design Brief — locked 2026-07-20

**World backdrop, character art, interface chrome:** all locked, full detail in `wiki/Noctis OS/Interface.md` and `Modes.md`, palette/coordinates in `assets/world/README.md` and `assets/characters/README.md`.

**Component sourcing — no shadcn, fully hand-built, and this is a derived fact, not a rule.** Every element of the card system fought the pixel-art/world aesthetic enough to warrant hand-building. Setup installs whatever the Stack section declares — currently that's Tailwind + Impeccable, no shadcn — because nothing here needed it, not because of a standing ban. A different project's Design Brief could resolve the other way.

**Design Brief is complete.** Remaining items are asset-production tasks: two touch-ups on the background image, a composite scale test, Custos's trigger thresholds (backend-logic, not blocking).

---

## Open questions — genuinely unresolved, tracked here so they don't disappear (added 2026-07-20)

These are correctly undecided — not gaps to silently fill, decisions for Shayne to close when ready:

1. **Interface sub-name** — Deck / Bridge / Console / none.
2. **Exact residue of `~/.claude/CLAUDE.md`** once the dev process moves out to `modes/dev/dev.md`.
3. **Noctis-as-MCP-server's concrete trigger** — parked, no trigger condition named yet beyond "a session needs OS state and can't get it cleanly through files."

---

## Phase 1 — CLOSED (2026-07-20)

Definition, PRD, EDD, and Design Brief all locked, including the thirteen items recovered in the 2026-07-20 completeness pass. Next: Phase 2 setup — GitHub repo, `.env.example`, project `CLAUDE.md`, folder structure, per `second-brain/build-spine.md`'s checklist.
