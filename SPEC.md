# Noctis OS — Spec

**Compiled architecture spec for v2.** Recompiled 2026-09-12 against `second-brain/wiki/Noctis OS/noctis-v2-SPEC.md` (drafted 2026-08-29, amended 09-06) and verified against the build.

**This file states *what* the architecture is. The vault states *why*.** Where they disagree on reasoning, the vault wins; where they disagree on current shape, this file wins — and both must be updated together. A decision made in chat and written in neither does not exist for a fresh session.

| Source | Holds |
|---|---|
| **This file** | The compiled current architecture |
| `second-brain/wiki/Noctis OS/noctis-v2-SPEC.md` | The v2 design record — definition, product, technical, risks, feasibility, build order |
| `second-brain/wiki/Noctis OS/{Overview,Modes,Interface,Improvement Loops,Decision Log}.md` | Reasoning, per-decision history |
| `STATUS.md` · `CHANGELOG.md` | What works today · what changed when |

> **This file previously described v1** and was locked 2026-07-20. It was recompiled because the repo's own `CLAUDE.md` points every fresh session here, and it was pointing them at a superseded architecture. v1's spec content is not preserved inline — `git log SPEC.md` has it, and the v1↔v2 delta is in the vault spec's "How this improves on v1".

---

## Definition

**What:** one always-present front door onto a vault of accumulated method, where every mode of work opens with its full context already in hand.

Two halves, deliberately unequal:

- **The body** — interface, orchestration, live session hosting. Claude-Code-shaped, a chosen dependency: it buys frictionless entry at zero marginal cost and inherits a tool loop, permission model and subagent system that would otherwise be a year of work.
- **The brain** — vault, retrieval, mode state, the methodology compounding in `lessons.md`. Answers to no client. Speaks MCP, and will serve whatever sits in front of it.

**Interfaces are disposable; knowledge compounds.** Build the disposable half well enough to live in daily, the durable half well enough to survive rehousing.

**Why:** v1 was built and unused. Mode entry had a context cost, Desktop had none, so the fallback won. Fixing entry is the only change that makes the rest worth building.

**"Agnostic" means adaptability, not breadth** — not being locked in when a better model lands, rather than running several providers at once. The seam sits at the MCP layer.

**Success criteria**

1. Centralised — daily work reachable from one place
2. Engineering is demonstrable (portfolio test)
3. Adaptable — the vault service runs against a client Noctis didn't write
4. Retrieval works — referencing a past conversation succeeds without saying where
5. Morning brief waiting daily, zero hand-maintenance
6. Mode entry carries context — nothing restated
7. Zero marginal cost — no per-token billing on top of the subscription

**Out of scope, with triggers:** execution isolation *(unattended tool access)* · messaging adapters *(missed something away from desk)* · containerised packaging *(second machine)* · code editing / custom IDE — *permanent* · multi-user or hosting — **permanent, and load-bearing for the licensing position.**

---

## PRD

### Session surface

**The real CLI, in a terminal.** A session is `claude` interactive in a pseudo-terminal the shell owns, rendered by xterm.js in Noctis's palette: its own prompt, its own tool display, its own permission questions, its own thinking indicator. Nothing is reimplemented; the composer, the block transcript and the permission dialog that used to stand in for these are gone with the `-p` orchestrator (EDD, "Session host").

**Several at once.** A strip of terminals, positional labels, `⌘T` opens one in a mode and a directory, `⌘W` closes, `⌘1–9` selects. The arrangement is remembered and comes back resumed.

**History is read-only and resumable.** `⌘K` searches history and the vault; a past conversation opens as blocks from the store, with one action — resume in a terminal.

**Status block, four rows.** cwd · branch · model · clock. Context % · 5h and 7d windows with reset countdowns and the reading's age · live/max sessions. Mode state. Every figure comes from the terminal's own `statusLine` report.

**No cost is displayed as spend.** Under a subscription the figure is notional and never charged. Limits are the real currency. Settings shows a lifetime list-price total, stated outright as not charged; the column is named `list_cost_usd` and `/v2/billing` returns `charged: false`, so the UI has no excuse to render it as a bill. **Overage is the one exception that can mean money** and the only thing that raises a banner.

**Table stakes:** searchable history · handoff between modes · search.

### Modes

Five session configurations. They differ by **methodology and model, never by capability**.

| Mode | For | Model | Methodology |
|---|---|---|---|
| General | Unscoped questions, comparisons | Opus 5 | none, by design |
| Faber | Build: spec, implement, ship | Opus 5 | `modes/dev/dev.md` |
| Noctua | Learn: read closely, explain, retain | Opus 5 | `modes/learn/learn.md` |
| Vesper | Research: gather, weigh, verdict | Opus 5 | `modes/research/research.md` |
| Maintenance | Audit the vault, propose repairs | Haiku 4.5 | `maintenance/audit.md` |

> **Amended against the vault spec (2026-09-12).** It specifies "Modes: 3" with general as "main session" and maintenance as infrastructure. The build makes all five first-class session configurations: general has no methodology overlay, and maintenance is infrastructure-shaped but launches like any other mode. Five is what ships.

**Modes are session configurations, not subagents.** A subagent is task-scoped and holds no conversation. Subagents live *within* a mode's session — `critic` for Faber, `gap-finder`/`quizmaster` for Noctua, `credibility-checker`/`synthesizer` for Vesper — registered per launch from the vault.

**Routing is explicit.** No model classifier: a classification call costs ~1.9s before the first token, and entry friction is the thing v2 exists to remove. Hotkey summons, `⌘T` selects. **Drift is detected, not pre-empted** — a local BM25 heuristic over mode descriptions can offer a switch before sending, and the session's own prompt instructs it to notice when a conversation has strayed and offer a handoff. The second matters more: straying happens several turns in. Handoffs carry a summary, not the transcript, and go through chat rather than mode-to-mode.

### The rest of the surface

**Rail:** Brief · Terminal · Stats · Inbox · Settings.

**Maintenance** — root-level `second-brain/maintenance/`, not a mode folder. Retains Audit → Propose → Apply and propose-never-commit.

**Scheduler** — `launchd`, fires on wake. Morning brief · vault auto-commit and push (secret-scan first) · maintenance. Exits if already run today.

**Brief and worklist.** `brief/today.md` is day-scoped and replaced each morning. `worklist.md` is durable and **hand-kept** — a generated worklist is the job list under a second name, and the two would disagree the moment one drifted. The brief is generated in two halves: facts counted in Python, prose written by a cheap-tier session from those facts and nothing else. If the prose call fails the brief still renders, because the rows are the part that must not be missing.

**Stats — three sections, no cost.** Usage (5h and 7d meters with reset countdowns) · Activity (one contribution grid, sessions per day) · Lifetime tokens (input / output / cache read / cache write). The cache-read line is diagnostic, not decorative: an orchestrated workload reloads methodology and job context every turn, so cache reads dominate, and a *drop* in that ratio is the earliest warning that context structure has started thrashing.

**Settings — four sections:** Models · Prompts (editor + regression runner) · Schedule · Maintenance inbox.

**Design Lodge** — vault-only, no UI tab in v2. Faber sessions keep reading it.

---

## EDD

```
┌─────────────────────────────────────────┐
│  NOCTIS — the entry point               │  ← the product
│  hotkey / tray · chat · brief · inbox   │
└──────────────────┬──────────────────────┘
                   │ orchestrates
┌──────────────────▼──────────────────────┐
│  Session orchestrator                   │
│  spawn / resume per mode · argv-passed  │
│  identity · parse stream-json → Event   │
└──────────────────┬──────────────────────┘
                   │ sessions call
┌──────────────────▼──────────────────────┐
│  Noctis MCP server                      │
│  vault_search · history_search          │
│  job_context · worklist · propose       │
│  prompts/* → enter_<mode>               │
└──────────────────┬──────────────────────┘
                   │
      vault (files) + history (SQLite/FTS5)
```

### Session host

**A session is a real interactive `claude` in a pseudo-terminal.** The shell's Rust side (`src-tauri/src/pty.rs`) owns the PTY — spawn, write, resize, kill — and knows nothing about modes; `backend/interactive.py` owns the mode and knows nothing about terminals. The shell asks `GET /v2/sessions/interactive-args` for an argv and hands it to `pty_spawn`. xterm.js renders the CLI's own TUI, themed from `tokens.css`.

**Identity travels in the argv, not on disk.** `--append-system-prompt` carries the composed methodology and the job brief, `--agents` the mode's subagent roster, `--settings` the shared permissions plus the status-line command, `--add-dir` the vault. `--resume` gives continuity: a remembered terminal comes back resumed, a history row reopens in a terminal.

**What the CLI reports, the shell reads.** `statusLine` runs every five seconds inside the session and POSTs its payload to `/v2/sessions/statusline` — the 5h/7d windows, context occupancy, model, effort, the session id and its transcript path. That is the status bar's source, and it survives a reload.

**The page outlives the window's visibility.** Closing hides to the tray, and the web view is configured not to throttle or suspend while hidden (`backgroundThrottling: disabled`): the shell keeps polling, remembering and indexing whether or not anyone is looking, which is what an always-there app means.

**Sessions outlive the page.** The PTY registry belongs to the Rust process, so a reload of the web view leaves every session running, and the shell comes back to them: slots keep their ids, each session keeps a capped scrollback of what it printed with its frames numbered, and `pty_attach` hands a returning terminal the replay plus the number of the last frame it contains, so only later frames are written after it. Ending a session is an intent — ⌘W, or `r` on a dead pane — never a side effect of a component unmounting, because React unmounts for reasons that are not that. The same shape as VS Code's terminal across a window reload.

**History is read, not recorded.** The CLI writes a complete transcript per session to `~/.claude/projects/**/*.jsonl`, incrementally; `orchestrator/jsonl.py` indexes those into the same SQLite tables search and Stats read. It counts every session on the machine, not only the ones Noctis hosted.

> **Supersedes the `-p` orchestrator (2026-09-14).** From 09-11 to 09-13 Noctis drove `claude -p --output-format stream-json` once per turn and rebuilt the interactive loop on top of a scripting mode: a closing pass because `Stop` does not fire under `--print`, a permission host because `-p` has no dialog, per-turn respawn, `TurnEnd` bookkeeping. A pseudo-terminal was rejected twice before (`Modes.md`, the v2 deferral table) under the fire-and-forget premise, where it would have meant scraping a terminal Noctis did not own; v2 hosts its sessions, and under hosting a PTY is simply how an interactive process is run. Every assumption was tested before the switch (`PTY-MIGRATION.md` §3), and the recorder-vs-transcript diff that gated it found the recorder undercounting every session it saw. The orchestrator — `driver`, `manager`, `parser`, `wire`, `events`, the permission host — is deleted.

> **Supersedes the vault spec (2026-09-11/12).** It specifies a per-mode `CLAUDE_CONFIG_DIR` whose `CLAUDE.md` is rewritten per launch. The config root is where plugins, skills, subagents, MCP servers, accumulated permissions and memory live, so redirecting it replaced the whole surface with an empty one. Sessions use the real `~/.claude` and inherit all of it; nothing per-mode is written to disk.

**`~/.claude/CLAUDE.md` is the universal prompt** (`prompts/system.md`), not a mode.

**Concurrency is advisory.** `NOCTIS_MAX_CONCURRENT` (ceiling 9) is what the shell reports; a terminal is a process the shell owns, and a backend that does not own the process would be lying if it enforced a cap. What is live is what the terminals themselves report — a status line silent for half a minute is a session that has gone.

**`one_shot` is the one place `-p` remains**, and it is the right use of it: a scripting mode used for a script, summarising text it is handed on the cheap tier with every tool refused.

### Desktop shell and supervision

**Tauri.** A Rust shell around the OS's WebView, which is the same
architecture VS Code uses — Electron is Chromium plus Node — minus the
bundled Chromium. Global hotkey summon (Opt+Space), tray, launch-at-login,
notifications; the window hides rather than quits, because an always-there
app that exits on the close button is not always there.

This overrides v1's rejection of Tauri on 2026-07-21, and the reason the
earlier decision was right for v1 is the same reason it is wrong for v2: v1
was a *launcher*, so native OS integration bought nothing. v2 is the front
door, which makes summon and tray load-bearing rather than polish.

> **Amended 2026-09-12.** The `app` target ran `desktop/app.py`, v1's pywebview
> shell, for five days after Tauri shipped — a third v1/v2 straddle alongside
> the two specs and `modes/settings`, and the one that mattered most because
> it is the path a person actually opens. pywebview is deleted; the loop is
> the Tauri shell, and `desktop/NoctisOS.app` wraps that.

**Two run paths, and only two.**

| | `make dev` | `make browser` |
|---|---|---|
| Window | native Tauri window | browser tab at `:5180` |
| Backend | under `backend/supervise.py` | `uvicorn --reload` |
| Typecheck | `[tsc]` stream | `[tsc]` stream |

**You develop in the window you use**, so a bug found while working is a bug
found in the real surface. `make browser` is the fallback for backend-only
work, where a Rust build is not worth paying for. **Both carry
the same product capabilities** — everything else is backend or frontend code
and identical in either.

**The backend is supervised, not merely started.** `backend/supervise.py`
polls `/health` rather than the process table, because a process can be alive
and wedged; backs off 1s→30s and then gives up with a reason, because a
supervisor that never quits turns a permanent fault into invisible thrash;
and reaps before respawning, because the probe fires for a wedged process too
and spawning beside one leaves it holding the port.

**The supervisor and `--reload` are mutually exclusive**, not layered: a
reload is indistinguishable from a death to a health probe, so the supervisor
would reap the process the reloader had just started. That is why `dev` has
the reloader and no supervisor, and `app` has the supervisor and no reloader.

**What supervision does not buy.** Sessions are subprocesses of uvicorn, so a
backend restart still kills any turn in flight. This shortens how long you are
down; it does not stop work being lost. That needs sessions to outlive the
request, with the orphan questions recorded under Open questions.

### Permissions

**Every mode gets the same tool surface.** `permissions.json` pre-approves the ordinary tools and Noctis's own retrieval for every mode; anything outside it the CLI asks about in its own terminal, which is where a person is looking. Capability was the wrong axis to vary on: a mode handed work it cannot perform ends with nothing done and no way to say so. Maintenance's propose-never-apply rests on its methodology.

**Denied outright, for every mode:** `git push`. Commits happen; pushing is manual.

**`crossSessionInbound` is `accept`**, so a peer session's message is delivered rather than held five minutes and expired. Bounded by the socket, which is user-only.

**Effort and permission mode are the CLI's own.** Shift+Tab cycles the permission mode inside the terminal, as it does anywhere; effort is set at spawn. The closing pass, the silent-turn states and the permission dialog existed to patch what `-p` could not do, and went with it.

### Noctis MCP server

**It solves one thing: ranked retrieval from inside a running session.** Sessions already have Read/Grep/Glob. Two things they cannot do: **rank** (grep cannot answer "what did I decide about X" when the wording is forgotten) and **reach history** (SQLite, not files).

**A component, not the product.** No UI, no initiative; it cannot spawn sessions or render chat.

**Surface:** `vault_search` · `history_search` · `job_context` · `worklist` · `propose` · `permission_prompt` (internal). MCP **prompts** expose `enter_<mode>`, which is what extends criterion 6 beyond Noctis's own UI. **Resources** expose vault documents.

**Design risk, mitigated twice:** an MCP tool only helps if the model calls it, and retrieval here is opt-in where Desktop's is automatic. Both mitigations are required — an explicit when-to-search rule in every mode's prompt, and automatic first-pass retrieval on entry.

**Dependency-free stdio JSON-RPC.** That is what makes it the half that travels.

### Retrieval

BM25 over SQLite FTS5. **Heading chunking, column weighting `1/8/4/1` (path/title/heading/body), k=20**, and the session reranks — agentic retrieval, free because the model is already in the loop.

**Measured 80% recall@20**, and the eval harness imports the same constants the server ships, so a ranking change surfaces as a regression. Lexical, vague-recall, temporal and multi-hop all at 100%; paraphrase plateaus at 73–82%, which is lexical search's real ceiling and the only thing embeddings would buy. Negatives stay at 0% because a BM25 score is not a confidence signal — saying "nothing here" is the session's job.

A hosted embeddings API over vault content is ruled out: nothing vault-touching routes through third-party providers.

### Storage

**The vault is sole source of truth for knowledge.** Markdown with YAML frontmatter, one directory per mode. `vault_io.py` is fully native — no Obsidian dependency; Obsidian is an optional viewer.

**History lives in SQLite, not the vault, and is indexed from the CLI's own transcripts.** The index is a derived cache, rebuildable from `~/.claude/projects/` by `POST /v2/sessions/index`, and deleting it loses nothing. Worth-keeping material is **promoted** into the vault as a note. Markdown transcripts would make every message a git diff.

### Cost and licensing

**Subscription and API are separate billing systems.** A client making its own model calls must use the API. The rejected path costs roughly $110/month on top of the subscription, indefinitely.

**v2 drives the Claude Code CLI as a subprocess. Zero marginal cost.**

**Licensing is load-bearing.** Anthropic's Agent SDK terms forbid third-party developers offering claude.ai login or subscription rate limits *in distributed products*. Running the CLI on your own machine under your own subscription is using Claude Code, not redistributing it. **The permanent multi-user/hosting exclusion is what keeps this onside and must not be softened.**

### Distribution — the half that travels

| | Distributable | Why |
|---|---|---|
| `noctis-mcp` server | **yes** | No Anthropic auth. Reads markdown, returns JSON. |
| `vault-template` | **yes** | Generated public skeleton — schemas, never content. |
| The app | **no** | Ships subscription auth. Permanent. |

Someone else generates a vault with the template's shape, points the server at it, pastes one JSON block into whichever MCP client they use, and has the retrieval half working against their own notes:

```json
{"mcpServers": {"noctis": {
  "command": "python3",
  "args": ["/path/to/noctis-mcp/server.py"],
  "env": {"VAULT_PATH": "/Users/you/my-vault"}}}}
```

**Be honest about what is shared.** `server.py` is small; the value is the structure it assumes — that jobs carry stage and status, that proposals go to an inbox, that modes have methodology files. Against a flat folder of markdown it degrades to `vault_search` alone. Adoption means adopting the methodology, not installing a tool.

**Agnosticism is a byproduct**, not a reorganising principle. The server never talks to a model — it speaks JSON-RPC to a *client*, so the brain works with any MCP-speaking client driving any model, including open-weight ones. What does not travel is the body.

---

## Harness portability — locked 2026-09-12

Full reasoning: `second-brain/wiki/Harness Portability.md`.

**"Workflow agnostic" means a move states what it costs, not that everything survives it.**

- **Portable because it is text** — `prompts/system.md`, mode overlays, `modes/*/[mode].md`, agent definitions, the vault.
- **Portable because MCP is the standard** — `tools/*` (retrieval) *and* `prompts/*` (`enter_<mode>` — identity, not just tools).
- **Not portable** — permissions, hooks, spawn flags, `parser.py`'s dependence on `stream-json`. Confined to three files under the `events.py` seam.

**Capability contract — built.** `backend/capabilities.py` declares what each mode's methodology assumes, probes what the harness has, reports the gap. `make doctor` prints it; `python -m capabilities` exits non-zero on a gap. Requirements live in code, not the vault: they are claims about infrastructure, not method.

**Multi-harness adapter — deliberately not built.** One harness, and an abstraction with a single implementation encodes guesses about the second rather than knowledge of it. `python -m capabilities --migrate` emits the brief instead.

**Bring-your-own-subscription is already in place** for Anthropic. Extending to other providers is N× driver and parser, not a licensing wall. Provider terms differ on scale, sharing and resale; personal single-seat use is the intended path.

---

## Design Brief

**An IDE, not a world.** v1's pixel scene is retired. v2 is a surface you sit inside for hours, so it takes the look of the tools that job already lives in. Sober, near-black, dense, keyboard-first. The characters survive and, with the world gone, are the only carrier of Noctis's identity.

**Glass, 2026-09-14.** The window is a macOS vibrancy material — `windowEffects: hudWindow` with `transparent: true` in `tauri.conf.json` — so the desktop shows through, blurred, the way Finder's sidebar and Spotlight do. The ground tokens are translucent to let it: ground most open, surface and elevated progressively more opaque so text stays readable whatever is behind the window. The terminal paints with `allowTransparency`, so it is not the one solid slab in a glass window. **This requires `macOSPrivateApi: true`**, which uses a private Apple API — a deliberate choice, recorded as one: it closes the App Store door and nothing else, and Noctis has no distribution story that would open it. On Intel a large vibrant window is a visible GPU tax; on Apple Silicon it is nothing.

**Palette** — verified against `frontend/src/shell/tokens.css`.

| Token | Value | Use |
|---|---|---|
| `--color-ground` | `rgba(15,15,15,0.42)` | app background, over the material |
| `--color-surface` | `rgba(22,22,22,0.55)` | panels, rail, cards |
| `--color-elevated` | `rgba(28,28,28,0.70)` | inputs, hover, active tab |
| `--color-line` | `#2a2a2a` | dividers |
| `--color-ink` | `#cccccc` | primary text |
| `--color-ink-dim` | `#8a8a8a` | secondary |
| `--color-ink-faint` | `#6a6a6a` | labels, timestamps |

**Accents**, one `--accent` swapped per active context: Faber `#e53311` · Noctua `#eca207` · Vesper `#953ead` · Maintenance `#da5b00`. Retired: the indigo sky ramp and Echo's `#293187`.

**Typography.** Press Start 2P is retired — a pixel face is a reading burden in a text-dense tool. Mono: **Cascadia Code**, fallback JetBrains Mono then Menlo. Sans: `system-ui`. No third face.

**Components:** rail · tab bar · block-structured transcript · tool-call disclosure rows · composer with mode and effort chips · four-row status block · limit meters · character bar · brief card · worklist · inbox · settings forms.

**References:** Raycast (summon/dismiss — the entry-friction pattern v2 is built around) · Linear (dense keyboard-first dark surfaces) · Cursor / VS Code Dark Modern (ground, mono/sans split) · Ghostty (text density and rendering — *not* turn structure, since `stream-json` gives discrete events and the transcript is block-shaped underneath).

---

## Open questions

Genuinely unresolved. Not gaps to silently fill.

1. **Interface sub-name** — Deck / Bridge / Console / none.

> **Closed 2026-09-12 — "tiered loading policy" (Stage 2 item 8), removed rather than defined.** It appeared in the build-order table and nowhere else: no description, no reasoning, no acceptance condition, and no trace anywhere in the vault. Its only defensible reading is *what enters a session's context at entry versus what it fetches on demand* — and the system already implements that: the job brief is capped and carries the tail, a mode's overlay is a pointer rather than the methodology, and retrieval is opt-in. The policy exists; it was undocumented, not unbuilt. Written up in `DOCUMENTATION.md` §6 rather than kept as a build item implying work that does not exist.
3. ~~**The v2 checkpoint** — *"do I still open Desktop?"*~~ **Closed 2026-09-12: passed.** The shell has been the daily driver since 2026-09-08. Recorded late deliberately — until 09-11 the answer was contaminated, because Faber inside Noctis could not do build work and the fallback to Desktop was therefore forced rather than chosen. With that fixed the question could be asked cleanly, and the answer held.
4. **`seven_day_opus` window** — present in the CLI binary and the statusline schema, absent from an observed Haiku run. Unverified.
5. **`--input-format stream-json` as a persistent bidirectional session** — untested. Would address spawn-per-turn latency (~1.9s).
7. ~~**Should the conversation surface be a PTY rather than `stream-json`?**~~ **Closed 2026-09-14: yes, and done.** *Opened 2026-09-13.* Noctis does not
stream a running CLI — it drives `-p`, which the CLI's own help calls "print
response and exit", once per turn. Most of the orchestrator exists to rebuild,
on top of a scripting mode, the loop the interactive mode already has. Running
`claude` in a pseudo-terminal instead would delete that reconstruction and give
the real thing.

**This was considered and rejected twice, and the rejection is now stale.**
`Modes.md` (2026-07-19) calls PTY capture "the original trap" and defers "full
terminal mirroring" to a v2 that "if ever wanted" should use octogent's PTY code;
the v2 spec's deferral table drops "PTY mirroring" outright. Both were correct
*under the fire-and-forget premise* — the interface launched sessions in
Terminal.app and VS Code and read state back from files, so a PTY meant scraping
a terminal Noctis did not own. **v2 replaced that premise**: the app hosts its
sessions now. Under hosting, a PTY is not mirroring, it is simply how an
interactive process is run. The decision was never re-derived when the thing it
rested on was removed, which is the failure `dev.md`'s completeness check exists
to catch — a decision outliving its premise.

Four load-bearing assumptions were tested on 2026-09-13 rather than argued:
chrome can drive the terminal (`/status` injected into a PTY rendered correctly,
survived resize, exited with no orphans); the `statusLine` command delivers
`rate_limits.five_hour`/`seven_day`, `context_window`, `effort`, `cost`,
`session_id` and `transcript_path` as JSON from an interactive session; the CLI
writes a complete transcript per session to `~/.claude/projects/**/*.jsonl`
carrying messages, tool calls, thinking, per-turn `usage` and its own `aiTitle`;
and `/status` reports `Login method: Claude Pro account`, so the subscription
premise is unchanged.

**Settled 2026-09-13 — Stats shows one raw lifetime token count, sourced from
the JSONL.** No split, no tiers, no footnote; it is a fun stat and should read
like one. The CLI's own background calls (naming a session, checking quota)
are not in the JSONL and go uncounted: measured, 146,327 against 82,174,586, or
**0.178%**. `CLAUDE_CODE_ENABLE_TELEMETRY` would recover that exactly for the
price of an OTel collector in a single-user app — not a trade worth making for
a fifth of one percent. `aux_input_tokens`/`aux_output_tokens` are deleted with
the migration and the word "aux" leaves the codebase.

**Transcript coverage — the open risk — cleared 2026-09-13.** Three real
sessions: a short one exits with its transcript, usage and the CLI's own
`aiTitle`; one **SIGKILLed mid-generation** already had its partial output on
disk, so transcripts are written incrementally rather than flushed at exit; a
`--resume` appends to the same file without forking. (23 of 73 stored sessions
lack a JSONL, but all 50 missing are `-p` spawns — the mode being left.)

**`portable-pty` builds and runs on this project's toolchain**: a Rust binary
spawned `claude`, took an injected `/status`, resized, and exited with no
orphans. 20 transitive dependencies, 773 KB size-optimised, inside the release
profile's bundle-size intent.

**The renderer path has production precedent.** Termic runs xterm.js with the
WebGL2 addon inside a Tauri/Rust app with the PTY on the Rust side — this exact
architecture — and DomTerm supports Tauri/Wry. WKWebView rasterises glyphs
slightly lighter than Terminal.app; a `fontWeight` bump closes it, and Cascadia
Code is already vendored as a 200–700 variable font. Styling is not a
constraint: `ITheme` covers all 16 ANSI colours plus brights, `extendedAnsi`,
selection and scrollbar, and `ITerminalOptions` covers font, weight, leading,
letter spacing, cursor style and density — generated from `tokens.css` so there
is one source of truth.

**Steps 1–3 shipped 2026-09-13, and step 3's first result changes the plan.**
The indexer runs beside the recorder with a live per-session diff, and 1 of 16
sessions agree. Every disagreement is the transcript being larger, 2–5×, and
on the session checked per field *output* tokens are 2× — which cache
re-reads cannot explain. The recorder writes one usage row per Noctis turn
from `result.usage`, and that is not the whole turn; it has undercounted since
it was written. So the migration's gate was misnamed: it is not "the diff is
boring", it is "every delta is understood", and this one is. The transcript
is the more complete source and Stats should read from it — step 4, not yet
done, pending pinning what `result.usage` actually contains.

**Step 1 shipped 2026-09-13.** A Terminal rail view hosts an interactive
`claude` in a pseudo-terminal beside the `stream-json` transcript: `pty.rs`
(the PTY host), `interactive.py` (the argv), `Terminal.tsx` (xterm.js themed
from `tokens.css`), `scripts/statusline.sh` + `/v2/sessions/statusline` (the
status bar's second source, which survives a reload where the stream never
did), and `orchestrator/jsonl.py` (history read from the CLI's own
transcripts). Steps 4–5 — switch the default, delete the orchestrator — are
**not started** and are gated on the two paths running side by side without
disagreeing. `DOCUMENTATION.md` §24.

What remains is one decision: which keystrokes stay reserved to the shell
versus passing through to the CLI. The IPC batching is in and had one real
bug on first use — it flushed only when the next read arrived, so a prompt
that blocked for input rendered to mid-sentence; a quiet frame now flushes,
via a batcher thread separate from the blocking reader. Sequence in `PTY-MIGRATION.md` §7, and steps 2–3 (statusLine
receiver, JSONL indexer running beside the recorder) are worth doing either
way.

Full impact review, capability by capability: `PTY-MIGRATION.md`. Not decided,
and deliberately not started — the spike code is throwaway.

6. ~~**Should a session outlive its window?**~~ **Closed 2026-09-14: yes, and done** (`6ec10dc`, `617ffd5`). The PTY registry belongs to the Rust process; slots keep their ids; a reload reattaches with a replay of what the session printed; and the web view no longer suspends while the window is hidden. The question as it stood: VS Code's model: the pty host owns long-running work, so a window reload reattaches rather than losing it. Noctis binds a session's lifetime to the HTTP request, so closing a tab kills the turn. Detaching would fix that and creates eight problems worth naming before it is built — unwatched budget burn, no stop control once the window is gone, orphans counting invisibly against the cap, who owns the stream on reattach, an unbounded or lossy replay buffer, nothing ending an abandoned session, **unwatched writes with no reachable permission dialog**, and the fact that sessions are subprocesses of uvicorn so it would not survive a backend restart anyway.

8. **Could a second CLI be a guest?** *Opened 2026-09-14, after Shayne asked
whether Codex or Gemini's CLI could run in Noctis "while having the interface
orchestrating statuses."* First, what Noctis does with Claude today, stated
without flattery: it does **not** orchestrate the CLI's work. It *hosts* the
process (a PTY the shell owns), *injects* identity into its argv
(`--append-system-prompt`, `--agents`, `--mcp-config`, `--settings`, `--add-dir`,
the env for the hooks), and *reads its edges* — the `statusLine` payload
(windows, context, model), the transcript it writes under `~/.claude/projects/`
(history, stats, search), and the hooks it fires (the action feed). The CLI
runs the loop; Noctis is the room it runs in and the instruments on the wall.

The PTY host is CLI-agnostic — `pty_spawn` takes a binary and an argv, and
`codex` or `gemini` would paint into the same pane tomorrow. What would *not*
come with them is every instrument: no `statusLine` means a blank bar (no
5h/7d, no context, no model); a different transcript format and location means
no history until an indexer reads it (Codex keeps `~/.codex/sessions/`, Gemini
its own); no PostToolUse hook means no action feed; and identity travels in
flags the other CLI does not have (`--append-system-prompt`, `--agents`), so
the mode overlay would arrive by the MCP `prompts/list` route the Harness
Portability decision already built for exactly this, or by a project file the
guest reads (`AGENTS.md`, `GEMINI.md`). `Harness Portability.md` deferred the
multi-harness adapter as YAGNI when the coupling was three files including a
stream parser; the PTY made the surface smaller — one argv builder and three
edge readers — so the adapter is cheaper than it was, and the first guest
would define its shape. **Unresolved, and not to be hand-waved:** the wiki's
"Model routing: Claude-family only in v1" rests on the Confusion Protocol
depending on a model that surfaces ambiguity rather than resolving it; a
second CLI is a second model, and that argument has to be re-made per model,
not per CLI. Build it when there is a guest worth hosting; the answer to "can
it" is yes, the answer to "what does it cost" is the four instruments above.

9. **The GitHub workflow.** *Opened 2026-09-14.* Shayne wants work on GitHub
and wants to use it the conventional way — branches, pull requests, issues —
without it becoming a second job tracker beside the vault. The state at
opening, read from the machine: two repos with remotes, `noctis-os` 201
commits ahead of a **public** remote and `second-brain` 17 ahead of a private
one, zero issues, zero pull requests, zero projects, ever; `gh` signed in as
`shaynesss`. The Repo view (`/v2/repo`, shipped the same day) is the
visualiser: local truth — branch, ahead/behind, dirty files, the last twenty
commits with the unpushed ones marked — beside GitHub's open PRs with their
checks and open issues, and one sentence saying what to do next. Read-only:
the one thing it asks for, push, it asks for in words.

**Recommendation, not yet decided:** the smallest conventional loop that
fits `dev.md` as written. *(a)* `main` is what is on GitHub and green; a
session never commits to it directly on a job — it works on `job/<slug>`
(a worktree when two run at once, per 3.2). *(b)* A finished piece becomes a
pull request, even solo: the PR body is what/why/verify, the review gates
already in 3.3 (critic, code-review plugin) run against the branch, and the
merge — squash, so `main` reads one commit per piece and the PR keeps the
detail — is Shayne's click on GitHub. *(c)* One issue per piece of work,
opened at Plan, named in the branch (`job/12-…`), closed by the PR
(`Closes #12`); this is 3.1's "spec milestones → GitHub Issues" actually
done. *(d)* **No Projects board**: the vault's jobs are the tracker, and a
board would be the job list again under a second name — the same reasoning
that settled the worklist. *(e)* The push rule stays exactly as it is: a
session never pushes. The branch reaches GitHub when Shayne pushes it — from
a terminal today, from a button in the Repo view if he wants one, because
the button is his hand. A crashed session still cannot have half-shipped
anything, which is what the rule is for.

**Before the next push of `noctis-os`, a decision that cannot wait for the
rest:** the 201 local commits carry `backend/data/history.db` and its WAL
(added in `2856b5a`, untracked since `02e5425`) — real transcripts, in the
history of a public repository. All 201 are local, so rewriting them to drop
`backend/data/` touches nothing on GitHub and needs no force-push; it is a
`git filter-repo --path backend/data --invert-paths` (not installed; `brew
install git-filter-repo`) on a tree that is otherwise clean. Do that, or
make the repo private, before the push. The STATUS note of 09-13 called this
"a rebase today"; it is now a filter and still today.

---

## Where this file is behind the build

Recorded rather than silently reconciled, because the vault spec still says the first two and a reader deserves to know which is current.

| Vault spec says | Build does | Since |
|---|---|---|
| Per-mode `CLAUDE_CONFIG_DIR`, `CLAUDE.md` rewritten per launch, separate dirs "required" | No redirect; identity in the argv; sessions inherit the real `~/.claude` | 2026-09-11/12 |
| Modes: 3 | Five session configurations | build |
| Rail: Brief · Stats · Inbox · Settings | Brief · **Chat** · Stats · Inbox · Settings | build |
| Per-mode tool policy (`--disallowedTools`) as a mode differentiator | Identical tool surface for every mode | 2026-09-12 |

Build state, non-aspirational: [`STATUS.md`](STATUS.md). Chronology: [`CHANGELOG.md`](CHANGELOG.md).
