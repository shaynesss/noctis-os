# Noctis OS — Spec

Compiled from the vault's Noctis OS scoping via the Phase 1 spec process in `second-brain/build-spine.md`. Definition, PRD, EDD, and Design Brief all locked 2026-07-20. **Phase 1 fully closed — Phase 2 setup is unblocked.**

**This file is the compiled architecture spec. The reasoning, discussion, and full decision history behind every point here lives in the vault, not duplicated in this repo:**
- `second-brain/wiki/Noctis OS/Overview.md` — architecture decisions, harness framing, effort estimate, tool evaluations
- `second-brain/wiki/Noctis OS/Modes.md` — all five modes designed in full via the seven/eight-part frame, character roster
- `second-brain/wiki/Noctis OS/Interface.md` — the world/character interaction model, profile overlay card system, per-mode content design, session launch surfaces
- `second-brain/wiki/Noctis OS/Decision Log.md` — chronological record of every decision, disagreement, and pushback across the whole build
- `second-brain/wiki/Agent Harnesses.md` — the Model+Harness concept underpinning the Definition below

If this file and the wiki ever disagree, the wiki wins for *why* a decision was made; this file wins for *what* the architecture currently is. Both should be updated together — a decision isn't done until both sides reflect it.

---

## Definition

**What:** Noctis OS generalizes the existing dev-only build-spine into five modes — Dev, Learn, Research, Settings, Nightshift. Each mode is a methodology file in the vault (`second-brain/modes/<name>.md`) with its own stages, subagent roster, and vault scope. A local web app (stateless FastAPI backend + React frontend, nothing deployed, vault as the only database) tracks mode state and launches Claude Code sessions with the active mode's methodology + working context preloaded — that per-session injection is the orchestration.

**Framing: Noctis is a harness, not just an OS.** Agent = Model + Harness — the harness is everything wrapped around a model that isn't the model itself (system prompt, tools, context management, orchestration). Claude Code is a harness around Claude. Noctis OS sits one layer up: it decides *which* harness configuration — mode methodology file, toolset, subagent roster, working context — gets injected into a Claude Code session, and when. "OS" is the right metaphor for the always-on world/character interface; "harness" is the more precise word for what mode-switching actually does underneath. Full concept and supporting research: `wiki/Agent Harnesses.md`. This framing carries a concrete build constraint: mode files should stay tight, legible loops rather than accreting machinery — a benchmark (Harness-Bench) found a lightweight harness beat a heavier, more elaborate one on identical tasks with the same model. Same principle as this project's own "simplicity wins."

**Who for:** single-user, single-machine. No auth, no multi-tenancy.

**Why:** `~/.claude/CLAUDE.md` currently hardcodes dev process into every session regardless of what kind of work is actually happening (learning, researching, building, maintaining). Noctis OS makes mode-switching structural instead of manually held context.

**Success criteria:** `make setup` gets a fresh Mac to running in under 10 minutes (tested once, not aspirational). Every mode's character shows live ambient state at a glance. A mode switch is a launcher action from a character's profile, not a manual context reload.

---

## PRD

### Core features (must-haves)

- **Persistent world screen** — single scene, no routing, five character sprites idling in fixed designated spots on a locked peak-dusk cloud-bed backdrop (see Design Brief).
- **Ambient state per character** — each sprite reflects its mode's live state at a glance (busy/idle, count badges where relevant — due reviews for Noctua, pending inbox items for Echo). Sourced from the same job-context frontmatter and hook-driven status files the profile view reads. No new data — a rendering of state already tracked.
- **Profile overlay** — click a character → panel opens over the world, world stays mounted underneath. Full card content design (per-mode layouts, idle states, typography, animation) locked — see `wiki/Noctis OS/Interface.md`.
- **Session launch from profile** — the only way a Claude Code session starts. Launcher injects that mode's methodology file + working context into the session. Launch button always present, permanently tinted in the character's own color. Launch surface is mode-specific (see EDD) — four modes open Terminal.app with a character-tinted background, Dev opens VS Code.
- **Five modes fully built** — Dev, Learn, Research, Settings, Nightshift — each wired to real vault reads/writes per the methodology already designed in `wiki/Noctis OS/Modes.md`.
- **Vault as sole database** — backend stateless, no separate persistence layer, no ORM, no migrations.
- **Session telemetry** — Claude Code hooks append one line per tool action to a per-job status file; job-context frontmatter updates at stage/track transitions; interface polls/streams these files.
- **Nightshift** — scheduled/triggerable slack-picker, staging-inbox-only writes, propose-never-commit. In v1 (pulled forward from v2), but first on the degrade-gracefully list under build pressure.
- **Nightshift inbox review lives inside Echo's profile** for v1 — no separate global inbox view yet, no launch button on Echo's card (review happens per-item).
- **Per-mode default model + per-job launch override** — each mode file declares a default model; the launch action offers an override. V1 scope: Claude family only (`--model`, same auth, zero new infra). Deliberate routing at launch, never silent mid-task fallback.
- **`make setup` / `make dev`** — single repo, fresh-Mac-to-running in under 10 minutes, both processes started together.

### Out of scope (explicit)

- Career mode
- Full PTY terminal mirroring (v2 reference exists via octogent, not built)
- Idle roaming/movement and the full expression library (v2 — v1 ships ambient *state* indicators only, not animation/movement)
- Noctis-as-MCP-server
- Tauri desktop wrap
- Any deployment — local-only, nothing goes to Railway/Vercel
- Multi-user/auth of any kind
- A separate global cross-mode inbox view (fair v2 upgrade if a proposal doesn't fit any single character's context)
- Cross-vendor model routing (non-Claude backends) — v2, gated on tool-calling reliability proof for the job shape in question, see EDD caution below
- In-app history views for Faber and Custos — their record lives in GitHub Issues/CHANGELOG and the settings lessons file respectively; both got idle states instead (see Design Brief)

### User flows

1. **Cold start** — open the app → world loads → all five characters idle in their spots, ambient badges reflect current state.
2. **Start a session** — click a character → profile overlay opens (typewriter reveal) → review live state/context → launch (optionally overriding the mode's default model) → session opens in the mode's launch surface (Terminal.app or VS Code) with methodology + working context preloaded → telemetry action feed populates live in the profile.
3. **Check without starting** — click purely to see state (due items, last session, current job) → close overlay → back to world, nothing launched.
4. **Nightshift review** — open Echo's profile → see staged inbox items from unattended runs → accept/reject individually (git-diff apply on accept).
5. **Mode-to-mode handoff** — e.g. research's inquiry track flags "worth a learn session" → close Vesper's profile → open Noctua's → topic already queued from the handoff.

---

## EDD

### Architecture overview

Two local processes, one repo, nothing deployed:

- **Backend** — FastAPI, stateless. No ORM, no migrations, no auth layer beyond bearer-token + Origin checking (see Decisions below — localhost binding alone is not sufficient). Every endpoint reads or writes vault files directly on disk (decided: no MCP dependency) and returns state.
- **Frontend** — React + Vite, single persistent scene (the world), no router. Character sprites render as static PNGs consumed from the asset pipeline; profile overlay is a component that mounts/unmounts over the world without unmounting the world itself.
- **Session launcher** — backend endpoint that constructs the mode's invocation (methodology file + working context + model flag) and opens it in that mode's designated launch surface (see "Session launch surfaces" below). Constructs invocation per-session — this is why per-mode/per-job model routing costs nothing architecturally (see Decisions).
- **Hooks** — Claude Code hooks configured per session append action lines to a per-job status file on tool-use events; job-context frontmatter rewrites at stage transitions. Backend/frontend poll these files.
- **Nightshift** — runs via **launchd** (decided below), a constrained subset of subagents against each mode's declared "slack surface," writing only to a staging inbox directory, never to live vault pages or code. Tool allowlist enforced (see Decisions).

### Session launch surfaces, per mode (locked 2026-07-20)

Where each mode's session actually renders — a separate layer from orchestration itself.

- **Learn, Research, Settings, Nightshift → macOS Terminal.app.** Launcher opens a new Terminal.app window via `osascript`, sets background to a darkened/desaturated version of the character's locked hex (HSL lightness ~15-20%, hue preserved — full saturation was considered and rejected for fighting text readability), sets window title to `{character} — {mode} — {current job/topic}`. Terminal.app has no separate "border" — window chrome is OS-drawn — so background tint is the real, fully-scriptable equivalent of the original colored-border idea. Title persists the whole session; tint is the at-a-glance signal across parallel windows.
- **Dev → VS Code**, via Claude Code's own VS Code extension. Two-step launch: `code <project-path>` first (the extension's URI handler has no path parameter — it only opens a tab in whatever workspace VS Code already has open), then `open "vscode://anthropic.claude-code/open?prompt=<url-encoded methodology+context>"` (pre-fills the prompt box, does not auto-submit).
- **VS Code localhost preview — global one-time setup, not per-session.** The `workbench.browser.openLocalhostLinks` VS Code setting routes any localhost link (including ones Claude Code prints in its own chat) into VS Code's built-in Integrated Browser panel instead of a system browser tab. Decided as a **global VS Code user setting**, not a per-repo committed one, since the goal was reducing friction every time regardless of which project is open. One-time manual step, goes in `SETUP.md`'s Noctis OS runtime checklist alongside Claude login.

### Mode files + CLAUDE.md migration (core architecture, part of the build)

- Mode methodology files live at `second-brain/modes/<name>.md` (dev, learn, research, settings, nightshift), each following the eight-part anatomy in `wiki/Noctis OS/Modes.md` (seven-part frame plus failure behavior, added 2026-07-19).
- `build-spine.md` **becomes** `modes/dev.md` — moved and restructured into the anatomy, one canonical file as always (wrapper option rejected as recreating two-copy drift).
- `~/.claude/CLAUDE.md` shrinks to universal rules only (write discipline, communication style, vault schema pointer); the symlink retargets accordingly. The launcher injects the active mode's methodology per session — this per-session injection replaces the global symlink as the orchestration mechanism and is the largest single input-token cut pending.
- Sequenced as the first build milestone: **mode files → backend → frontend tracker → telemetry → nightshift.** (Git-for-the-vault prerequisite is done — see below.)

### Stack and justification

- **FastAPI** — matches existing stack, stateless-by-design fits "vault is the database."
- **React + Vite** — same; component sourcing for the overlay chrome follows build-spine's standing 3.0 rule, see Decisions below.
- **No database** — vault files ARE the persistence layer. Avoids a second source of truth drifting from the vault.
- **Sprites** — PIL-rendered PNGs from grid-data text files (git-diffable, true pixel grid, no runtime pixel-art library). Generated at asset time, not runtime. `assets/characters/` is the sole source of truth for grid definitions and the render script; the frontend only consumes generated PNGs — grid data is never duplicated into `frontend/src`.
- **World background** — a static illustrated plate (AI-generated, art-directed, hand-picked footing coordinates), not a procedural/canvas-drawn scene. Simpler than rendering the world programmatically, and matches the flat-illustration register locked in the Design Brief. See `assets/world/README.md`.
- **Profile overlay** — Press Start 2P (header) + JetBrains Mono (body) loaded via Google Fonts; typewriter-reveal entrance animation; fixed card height across four of the five modes with Echo as the deliberate exception. Full content design per mode in `wiki/Noctis OS/Interface.md`.

### Decisions locked during EDD

- **Nightshift execution mechanism: launchd.** Considered cron (fine but less native to sleep/wake handling), in-process asyncio (rejected — only runs while the app is open, contradicting nightshift's unattended premise), and Cowork bridge (parking-lot heavier option, no clear win here).
- **Vault access: direct filesystem read/write, no istefox/MCP dependency.** MCP is built for Claude-as-client calling tools; wiring a FastAPI backend to speak MCP just to read markdown is an unnecessary dependency and a running-Obsidian requirement. Tradeoff accepted: loses Obsidian's metadata cache (backlinks, tag aggregation, orphan detection), atomic frontmatter ops (solvable with a small Python YAML frontmatter lib), semantic search, and Dataview/canvas/bookmarks. None of the five modes' designed v1 methodology currently calls for any of these. Named trigger to revisit: if research mode's synthesizer later wants semantic recall across the vault.
- **Note on istefox's continuing role:** istefox stays required for the Claude Desktop / claude.ai workflow (this is how Desktop sessions read the vault) — it is only removed as a dependency *of the Noctis OS backend*. SETUP.md documents it under the Desktop workflow checklist, clearly separated from Noctis OS runtime requirements.
- **Overlay chrome component sourcing: no whole-preset decision.** Not "adopt shadcn's `bd1gAd4y` preset wholesale" vs. "go fully custom" — that framing was wrong. Instead, standard build-spine 3.0 sourcing applies: check the personal 21st.dev Library first, public shadcn registry second, per component the overlay spec actually needs. Anything that fights the pixel-art/world aesthetic gets hand-built rather than forced from a registry component. Resolved as process, not a design-taste call.
- **Backend auth is mandatory, not optional.** Localhost binding alone is not sufficient — browser tabs can reach localhost APIs (CSRF/DNS-rebinding class of attack). Every route requires bearer-token auth + Origin checking. The launcher never passes skip-permissions flags for interactive sessions.
- **Model routing is per-mode-default + per-job-override, Claude-family only in v1.** The session launcher already owns invocation construction, so this costs nothing architecturally. **Caution, not a v1 gap:** a specific model being available (e.g. Kimi K3, or any non-Claude backend) doesn't make it a safe swap — see `wiki/Agent Harnesses.md`. Cross-vendor routing stays v2, gated on proven tool-calling reliability for the specific job shape.
- **Nightshift gets a tool allowlist**, on top of propose-only: staging-inbox writes only, minimal bash, no network by default.
- **No secret values ever written to the vault** — job contexts and lessons entries included. `.env` stays in repos; the ship gate's secrets-grep extends to vault writes.
- **Serialized write path for shared vault files.** Per-session job/lessons files are written freely by their own session; shared files (`log.md`, `index.md`) are written through the backend as a single serialized writer, to prevent the duplicate-heading/silent-double-append failure class from scaling with writer count under parallel sessions.
- **Sessions run in parallel across modes** — a mode is methodology + view focus, never an execution lock. Parallelism is a token-usage multiplier, so posture is: parallel when jobs genuinely don't block on each other, not parallel by default.
- **In-app History views for Faber and Custos: rejected in favor of idle states.** Both modes' completed-work record already lives elsewhere (GitHub Issues/CHANGELOG; settings' own lessons file) — an in-app History would be a second source of truth. Both get a character-voiced idle line instead when nothing's active.

### File/folder structure (target — created at Phase 2)

```
noctis-os/
├── backend/
│   ├── main.py
│   ├── routers/          # mode.py, session.py, nightshift.py
│   └── vault_io.py       # all vault read/write goes through here
├── frontend/
│   ├── src/
│   │   ├── World.tsx
│   │   ├── ProfileOverlay.tsx
│   │   └── ...           # consumes assets/, holds no grid data or world-plate copies
├── assets/
│   ├── characters/        # SOLE source of truth: grid definitions + render script + generated PNGs
│   └── world/             # background plate(s) + footing-spot coordinates, see assets/world/README.md
├── scripts/
│   ├── setup.sh
│   └── nightshift_run.sh # launchd target
├── Makefile               # setup, dev
├── .env.example
└── SETUP.md               # manual machine-level checklist — three buckets: Noctis OS runtime (Claude Code login, vault path, global VS Code "openLocalhostLinks" setting), Desktop workflow (Obsidian, istefox plugin), and nothing else — everything else is scripted by make setup
```

### External dependencies

Claude Code CLI (`claude`), the Claude Code VS Code extension (Dev mode's launch surface), PIL (sprite rendering), a Python frontmatter/YAML library (small, replaces istefox's atomic frontmatter ops), Google Fonts (Press Start 2P, JetBrains Mono), macOS `osascript`/AppleScript (Terminal.app launch + tinting, four of five modes). No other services, no MCP servers required at runtime.

### Prerequisite — done (2026-07-20)

**Git for the vault.** `second-brain/` is now its own git repo (initialized separately from the sibling project repos already living under `~/Developer`), initial commit made, `.gitignore` excludes Obsidian workspace state and Drive conflict-copy artifacts. The "one revert away from clean" guarantee now actually holds before Noctis OS adds automatic, parallel, and eventually unattended writers.

---

## Design Brief — locked 2026-07-20

**World backdrop.** Peak-dusk cloud bed as the literal ground plane: flat vector illustration, no gradients within any shape, no photorealism, no landmarks/props, ambient-only lighting (no rays, no sun). Dark indigo-to-violet sky with sparse asymmetric stars. Full brief, palette table, and locked footing-spot coordinates for all five characters live in `assets/world/README.md`.

**Character art direction** locked separately in `wiki/Noctis OS/Modes.md` — pixel grid style, per-character palette. Sprite sheet delivered, restated for asset-time reference in `assets/characters/README.md`.

**Interface chrome (profile overlay).** Typography (Press Start 2P header / JetBrains Mono body), typewriter-reveal entrance animation, fixed card height across four modes, per-mode content layout (Faber's phase+status jobs, Noctua/Vesper's two-track stat blocks, Custos's stacked trigger badges, Echo's aligned inbox rows), idle states for Faber and Custos, and permanently color-tinted launch buttons — all locked. Full reasoning and every content decision: `wiki/Noctis OS/Interface.md`.

**Design Brief is complete.** Remaining items are asset-production tasks, not open design questions:
1. Two touch-ups on the world background reference image (a stray artifact, inconsistent star shapes).
2. Composite scale test (sprite at real size against the background) not yet run.
3. Custos's trigger thresholds (what numerically fires friction/accumulation/suspicion) — an EDD/backend-logic question, doesn't block card design.

---

## Phase 1 — CLOSED (2026-07-20)

Definition, PRD, EDD, and Design Brief all locked. The only prerequisite blocking Phase 2 (git for the vault) is done. Next session can start Phase 2 setup directly: GitHub repo, `.env.example`, project `CLAUDE.md`, folder structure, per the checklist in `second-brain/build-spine.md`.
