# Noctis OS — Documentation

The reference. Every subsystem, what it does, and why it behaves the way it does.

| If you want | Read |
|---|---|
| What Noctis is, and how to run it | [`README.md`](README.md) |
| **How each part works** | this file |
| What the architecture *is*, as a spec | [`SPEC.md`](SPEC.md) |
| **Why** a decision was made — evidence, risks, what failed | `second-brain/wiki/Noctis OS/noctis-v2-SPEC.md` |
| What works today | [`STATUS.md`](STATUS.md) |
| What changed when | [`CHANGELOG.md`](CHANGELOG.md) |

---

## 1. The shape

Two halves that age differently.

**The brain** — a markdown vault plus an MCP server that makes it queryable. Ranked retrieval over years of decisions, every job's working context, each mode's methodology. Stdio JSON-RPC, no Noctis-specific dependencies. Any MCP client can use it.

**The body** — whatever runs sessions. Today: a Tauri shell and a FastAPI backend driving the Claude Code CLI as a subprocess.

The body is replaceable and built to be. The brain is meant to outlive it. Everything below is organised around that split — §2–§7 are the body, §8–§11 the brain, §12–§19 the surfaces and cross-cutting concerns, and §20–§23 are for operating it.

---

## 2. Anatomy of a spawn

Every turn is its own process. `build_command()` is pure, so the argv can be asserted on directly.

```
claude -p "<prompt>"
  --model claude-opus-5
  --output-format stream-json --verbose
  --permission-mode manual
  --permission-prompts host
  --permission-prompt-tool mcp__noctis__permission_prompt
  --mcp-config {"mcpServers":{"noctis":{...}}}
  --settings {"permissions":{...},"hooks":{...}}
  --effort high
  --append-system-prompt "<system.md + overlay + job context + vault root>"
  --agents {"critic":{...}}
  --allowedTools "Read Grep Glob WebSearch WebFetch Edit Write Bash NotebookEdit TodoWrite Task mcp__noctis__*"
  --add-dir <vault>
  [--resume <session_id>]
```

| Flag | Why |
|---|---|
| `-p` | Print mode. One invocation is one turn. |
| `--output-format stream-json --verbose` | `--verbose` is required or the stream emits nothing useful. Easy to lose in a refactor; the failure looks like an empty session. |
| `--permission-prompts host` | Names *who answers* a permission request. Defaults to `host` — a promise the driver must keep. See §6. |
| `--mcp-config` | Inline JSON, not a file: keeps the spawn self-describing with nothing on disk to drift. |
| `--settings` | Also inline, because the telemetry hooks need absolute machine paths that cannot be committed. |
| `--append-system-prompt` | The mode. Appending also turns off system-prompt snapshotting, so an edited methodology reaches a *resumed* session. |
| `--agents` | The mode's subagent roster, as inline JSON. |
| `--add-dir` | The vault, as a second readable root. Without it a session cannot read its own methodology. |

**No `CLAUDE_CONFIG_DIR`.** `build_env()` strips it even if the environment sets one. The config root is where plugins, skills, subagents, slash commands, MCP servers, accumulated permissions and memory all live — redirecting it does not override some settings, it replaces the whole surface. Every session uses the real `~/.claude`.

**`NOCTIS_MODE`** is set for the telemetry hooks. That is the only variable added.

**Finding the binary.** PATH first, then `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin`, `~/.claude/local`. `NOCTIS_CLAUDE_BIN` overrides everything. This matters because `launchd` starts processes with a bare `/usr/bin:/bin:/usr/sbin:/sbin` containing no Homebrew, so a scheduler-started backend cannot find an engine that works fine from a terminal. A failed lookup returns the bare name so the caller can report a proper error rather than crashing.

---

## 3. The event stream

`stream-json` emits one JSON object per line. `parser.py` has the shape knowledge and no I/O; `driver.py` has the I/O and no shape knowledge. Keeping them apart is what makes either testable — the streaming path is exercised end to end with `cat fixture.jsonl`.

| Event | Carries |
|---|---|
| `SessionStart` | `session_id` (what `--resume` takes), model, cwd, tools |
| `TextDelta` | assistant prose |
| `ThinkingDelta` | a reasoning block. **`text` is usually empty and that is not a bug** — models default to `display: "omitted"`, so reasoning is billed and never returned. The block's *presence* is the signal. |
| `ThinkingProgress` | live token estimate, climbing during a pause — the one honest signal that work is happening |
| `ToolCall` | id, name, args, and a one-line `summary` of the target |
| `ToolResult` | id, content, `is_error` |
| `ContextSnapshot` | how full the window is *at one moment* |
| `Limits` | 5h and 7d utilisation, reset times, overage flag |
| `TurnEnd` | usage, duration, stop reason, and the turn-integrity fields (§7) |
| `EngineError` | a failure to surface rather than swallow |

**Why normalize at all**, given one engine ships: the frontend needs a stable shape, and `stream-json` is a supported flag rather than a versioned API. A schema change upstream becomes a patch to `parser.py` and nothing else. This is the surviving half of the Engine seam — the normalization earned its keep; the multi-adapter abstraction around it did not.

**`ContextSnapshot` exists because occupancy cannot be read off `TurnEnd`.** That event's usage is cumulative across every API call the turn made, and a turn running fifteen tools makes fifteen calls, each re-sending the conversation. Summing them measures traffic, not occupancy: one real turn recorded 2,599,073 cache-read tokens against a 1M window, and the status bar faithfully reported 470% full. An assistant message carries the usage of the single call that produced it, so its prompt size *is* the occupancy at that instant.

**Line limit.** asyncio's `StreamReader` defaults to 64KB and `stream-json` puts a whole tool result on one line. A `Read` of any sizeable file overran it and killed the session mid-turn. The limit is 32MB — the ceiling is a line the CLI already chose to emit, and refusing to read what it sent is not a limit worth enforcing here.

---

## 4. Turn lifecycle

```
spawn ──► SessionStart ──► [ThinkingDelta │ TextDelta │ ToolCall/Result]* ──► TurnEnd
                                                                                │
                                                    needs_closing? ──► resume once ──► handback
```

**Resume.** `session_id` from the first event, `--resume` on the next spawn. Stored per session, not per app: a turn without one starts fresh rather than continuing.

**Concurrency: 4 by default**, settable with `NOCTIS_MAX_CONCURRENT`. Queued, not refused — a handle stays visibly `queued` rather than disappearing. The cap is a budget on the 5-hour window, not a resource limit; orchestrated sessions burn quota faster than chatting.

**Failure containment.** A crashed run must not look like a clean one: the manager marks a handle `failed` when any fatal event appeared, `done` otherwise, in a `finally` so an abort cannot strand it. The shell clears `busy` in a `finally` too, so a throw cannot lock a composer with no way back.

---

## 5. System prompt vs system config

These are different things and conflating them caused most of this project's worst bugs.

**The system prompt is what a session is *told*.** Text. Portable. Travels in the argv.

**The config root is what a session *can do*.** Not a settings file — the whole capability surface:

| In `~/.claude` | Gives a session |
|---|---|
| `plugins/`, `skills/` | `/impeccable`, `/code-review`, `/security-review`, `refero-design` |
| `agents/` | registered subagents |
| `commands/` | slash commands |
| `settings.json` | permissions, hooks, model, effort |
| `.claude.json` | MCP servers, credentials |
| `projects/*/memory/` | accumulated memory |
| `projects/*/` | conversation history |

**Prompt is instruction; config is capability.** Telling a session to run `/impeccable` when the config root has no plugins is handing someone a recipe for a kitchen they do not have — which is exactly what happened: `dev.md` mandates seven tools and a Noctis-launched Faber session could reach none of them, for months, silently. §17 is the fix.

**`CLAUDE.md` straddles both** — it lives in the config root and becomes part of the prompt. That is where this went wrong: to give each mode a different `CLAUDE.md` (a text problem) the code redirected the entire config root (a capability decision), and paid the whole surface to solve it.

**The hierarchy now:**

| File | Holds |
|---|---|
| `~/.claude/CLAUDE.md` → `prompts/system.md` | Universal rules. **Not a mode** — pointing it at `dev.md` made the machine itself Faber and leaked the build process into every session. |
| `<project>/CLAUDE.md` | The project's conventions. Read because cwd is the project. **Describes the project, not the session's identity** — a General session in a Faber-ish repo opened with "Faber here" and had to correct itself. |
| `--append-system-prompt` | The mode. |

**Snapshotting.** `--system-prompt-snapshot` defaults to on, recording the system prompt once per conversation and reusing it verbatim across resumes. `--append-system-prompt` turns it off, so an edited methodology reaches a session already running. Before that, a resumed session kept answering to the prompt it was born with.

---

## 6. Modes

Five session configurations. They differ by **methodology and model, never by capability**.

| Mode | Model | Methodology | Vault folder | Subagents |
|---|---|---|---|---|
| General | Opus 5 | none, by design | — | built-ins only |
| Faber | Opus 5 | `modes/dev/dev.md` | `modes/dev` | `critic` |
| Noctua | Opus 5 | `modes/learn/learn.md` | `modes/learn` | `gap-finder`, `quizmaster` |
| Vesper | Opus 5 | `modes/research/research.md` | `modes/research` | `credibility-checker`, `synthesizer` |
| Maintenance | Haiku 4.5 | `maintenance/audit.md` | `modes/settings` | — |

**Two different paths per mode.** `jobs_dir()` and `methodology_path()` are separate functions because maintenance genuinely diverges: its methodology moved to `maintenance/audit.md` while its state stayed at `modes/settings/`, since v1 still reads those paths. One mapping lives in `jobs.py` — it was previously restated in three files, two of which disagreed.

**Composition.** `prompts/render.py` builds `system.md` + `overlays/<mode>.md` + the job context. `orchestrator/modes.py` appends the vault's absolute root, because `system.md` says "Vault root: `second-brain/`" — a *relative* path that resolves against the project, and a live session duly reported the vault unreadable while reading it through MCP.

**A mode's overlay is a pointer, not the methodology.** Faber's is 672 bytes and says so; `dev.md` is 22KB and is read on demand. That read only started working once the absolute path was stated.

**Subagents** come from `modes/<folder>/agents/*.md`, front matter parsed for `description` only — the body is the prompt. Deliberately not a YAML parse: these are hand-written, and one bad header must cost its own description rather than the whole roster.

**Context loading is tiered**, and the tiers are a policy rather than an accident — this is what Stage 2's "tiered loading policy" turned out to describe, once someone looked.

| Tier | What | Why |
|---|---|---|
| **Always** | universal prompt · mode overlay · job-context tail (capped at 2,600 chars) | Small, and needed before the session does anything. |
| **By reference** | the full methodology, `lessons.md`, wiki pages | Named in the overlay, read on demand. Faber's overlay is 672 bytes pointing at 22KB. |
| **On demand** | ranked retrieval over vault and history | Opt-in, and the reason a when-to-search rule sits in every mode's prompt. |

The budget matters because an orchestrated workload re-sends its context every turn: measured spawn cost was ~1.9s, **~26K tokens of it configuration**. The regression signal is the cache-read ratio in Stats — a *drop* is the earliest warning that context structure has started thrashing.

**Failures are non-fatal.** A session with the base prompt and no overlay is worse; a session that fails to spawn is nothing at all. The flags are omitted rather than passed empty.

---

## 7. Permissions and turn integrity

### Permissions

**Every mode gets the same tools.** `--disallowedTools` is not passed for any mode. Capability was the wrong axis to vary on: a mode handed work it cannot perform ends its turn with nothing done and no way to say so.

Pre-approved, no prompt: `Edit`, `Write`, `Bash`, `NotebookEdit`, `WebSearch`, `WebFetch`, and the four read-only `mcp__noctis__*` tools. **Denied outright:** `Bash(git push*)`.

`mcp__noctis__propose` is deliberately *not* pre-approved — it writes, and it is maintenance's.

**Bash is allowed whole**, not command by command. The curated list — `make`, `pytest`, a dozen `git` subcommands — meant anything outside it (`sed`, `find`, `mkdir`, `gh`) hit a prompt, and the list could only ever be as complete as the last time someone extended it.

**Someone answers.** `--permission-prompts` decides *who*, and defaults to `host` — the SDK host or `--permission-prompt-tool`. A plain subprocess is not a host, so under the default every request went out and died unanswered, and the chip's labels were fiction. The Noctis MCP server is the prompt tool now: a request reaches a dialog and waits.

**Sandbox:** the launched project plus the vault. Reaching outside them fails, and that failure is correct.

**Effort** is the composer chip: `low` / `medium` / `high` / `xhigh`, default `high`. Applies to the next turn, which is immediate — every turn is its own spawn. `max` is settable but outside the cycle, the same treatment `bypassPermissions` gets.

### Turn integrity

A turn can legally end with tool calls and no text. The shell renders the transcript, so such a turn drew *nothing* — pixel-identical to a dead backend, a session still thinking, and a finished job. Four states, one picture.

`TurnEnd` now carries what the turn produced:

| Property | Means | Renders as |
|---|---|---|
| `silent` | no text at all | *turn ended with no reply* |
| `unclosed` | ended on a tool call, nothing said after | *turn ended mid-work* |
| `truncated` | `stop_reason == max_tokens` | *turn hit the output limit* |
| `blocked` | silent **and** tools were refused | *turn ended blocked*, refusals named |

**`denials` and `terminal_reason` were always in the stream and read by nothing.** That is why a caged session looked like a quiet one, and why `system.md`'s "never end a turn without user-visible text" kept failing: the rule was not ignored, it was **unsatisfiable** — a session refused every tool it needed has nothing to report but the refusal.

**Every working turn is asked to close.** `Stop` is the hook that can refuse a stop, but it does not fire under `--print`, and the Agent SDK that supports hooks requires API-key auth — the metered path this architecture exists to avoid. So the manager resumes once with a prompt carrying `system.md`'s rules: what was done, what it fixed, what is next.

- Asked when the turn **used tools**, or was silent, or truncated. Not asked for plain conversation, which closes itself by existing.
- A turn that already closed answers `closed`, buffered and dropped so it never reaches the transcript.
- `continuation=True` is the loop guard, and the recursion is not hypothetical: a continuation is itself a turn.
- A failing close is swallowed. It is a courtesy on top of a turn that already happened.

**Why not detect a missing summary from the text?** Because whether prose amounts to a handback is a judgement. Grepping for "Summary" would be the same fragile inference this replaced, so the question is asked of the model rather than of the text.

**Cost:** roughly doubles notional list price on working turns; below the resolution of the 5-hour window on a subscription.

---

## 8. The Noctis MCP server

`backend/mcp/server.py`. Stdio JSON-RPC, dependency-free — `python3 server.py` and nothing to install. **This is the half that travels.**

**It solves one thing: ranked retrieval from inside a running session.** Sessions already have Read/Grep/Glob, fine for most vault work. Two things they cannot do: **rank** (grep cannot answer "what did I decide about X" when the wording is forgotten) and **reach history** (SQLite, not files).

**A component, not the product.** No UI, no initiative; it cannot spawn sessions or render chat.

### Tools

| Tool | Does |
|---|---|
| `vault_search` | Ranked BM25 over the vault |
| `history_search` | The same over conversation history |
| `job_context` | A job's full record |
| `worklist` | The hand-kept worklist |
| `propose` | Stage a proposal into the maintenance inbox — **not pre-approved** |
| `permission_prompt` | Internal. Named by `--permission-prompt-tool`; surfaces a request in the app. |

### Prompts — the part that is easy to miss

`prompts/list` and `prompts/get` expose `enter_faber`, `enter_noctua`, `enter_vesper`, `enter_maintenance`. Each loads that mode's methodology and job context.

**This is how identity ports.** MCP prompts are a standard primitive, supported by Cursor, Claude Desktop, Zed and others — so mode entry works in clients Noctis did not write, not just retrieval.

### Resources

`resources/list` exposes vault documents, currently `noctis://worklist`.

### Using it from another client

Same block everywhere; only the file differs:

```json
{"mcpServers": {"noctis": {
  "command": "python3",
  "args": ["/path/to/noctis-os/backend/mcp/server.py"],
  "env": {"VAULT_PATH": "/Users/you/my-vault"}}}}
```

**Be honest about what that shares.** `server.py` is small; the value is the structure it assumes — that jobs carry stage and status, that proposals go to an inbox, that modes have methodology files. Against a flat folder of markdown it degrades to `vault_search` alone. Adoption means adopting the methodology, not installing a tool.

**The design risk, mitigated twice.** An MCP tool only helps if the model calls it, and this is opt-in where Desktop's retrieval is automatic. Without a when-to-search rule the session answers from context and skips the tool — experienced as "retrieval is broken" when it was never invoked. Both mitigations are required: an explicit rule in every mode's prompt, and first-pass retrieval on entry.

---

## 9. Retrieval

BM25 over SQLite FTS5. No added dependencies — FTS5 and `bm25()` are in system Python.

| Setting | Value | Why |
|---|---|---|
| Chunking | headings, min 400 chars | BM25 normalises for length; whole documents drown short precise sections |
| Column weights | `1 / 8 / 4 / 1` | path / title / heading / body |
| `k` | 20 | the session reranks — free, because the model is already in the loop |

**Measured: 80% recall@20.** The eval harness imports the same constants the server ships, so a ranking change surfaces as a regression rather than as a number in a doc.

```bash
.venv/bin/python eval/run_retrieval_eval.py
```

40 cases across six categories. Lexical, vague-recall, temporal and multi-hop all at 100%. **Paraphrase plateaus at 73–82%** — lexical search's real ceiling, and the only thing embeddings would buy. **Negatives stay at 0%**, deliberately: a BM25 score is not a confidence signal, so saying "nothing here" is the session's job, not a threshold's.

It got there from 52% by two purely lexical fixes: weighting the title and heading columns (+5), and raising `k` from 5 to 20 (+20, plateauing flat to k=40). **The original top-5 was the defect** — five results is a human-reading budget, and no human reads these.

A hosted embeddings API over vault content is ruled out: nothing vault-touching routes through third-party providers. A *local* embedding model is an evidence-backed option for the paraphrase residual, not a scheduled requirement.

---

## 10. The vault

Sole source of truth for **knowledge**. Markdown with YAML frontmatter.

```
second-brain/
├── prompts/            system.md + overlays/<mode>.md
├── modes/<folder>/     <folder>.md · lessons.md · state.md · jobs/<slug>/context.md · agents/*.md
├── maintenance/        audit.md · schedule.md · agents/   (infrastructure, not a mode)
├── wiki/               durable reasoning
├── design-lodge/       design assets + quick-capture inbox
├── brief/today.md      day-scoped, replaced each morning
├── worklist.md         durable, hand-kept
└── log.md · index.md   serialized-writer files
```

**State vs knowledge.** Durable reasoning goes in `wiki/`; volatile state goes in a mode's `state.md`, `lessons.md` and job contexts. The split is what keeps the vault readable as it grows.

**`vault_io.py` is fully native** — no Obsidian dependency, after Obsidian's app-level config hung for reasons unrelated to any vault file. Obsidian is an optional viewer.

**`log.md` and `index.md` go through a single serialized writer.** Per-mode files do not need it — one writer type each.

**Two-tier self-improvement.** Sessions append to `lessons.md` freely, no gate — the automatic, low-stakes tier. Periodically maintenance digests those lessons and drafts a *proposed* diff to the methodology itself, staged for manual accept or reject. **No mode ever rewrites its own or another mode's methodology.**

---

## 11. History and storage

**SQLite, not the vault.** Transcripts are application data; the vault is for knowledge. Markdown transcripts would make every message a git diff.

- One row per session and per turn: tokens in/out, cache read, cache write, model, mode.
- FTS5 index over both vault and history — **one mechanism, zero added dependencies.**
- The index is a **derived cache.** Rebuildable; deleting it loses nothing.
- `promote()` moves worth-keeping material into the vault as a note, mirroring `raw/` → `wiki/`.

Default location `backend/data/`, overridable with `NOCTIS_DATA_DIR`.

---

## 12. The interface

React + Tailwind 4 in a Tauri shell. `frontend/src/shell/` is the v2 client; `main.tsx` imports it and nothing else.

**Rail:** Brief · Chat · Stats · Inbox · Settings.

**Transcript blocks** — the turn is block-shaped underneath because `stream-json` gives discrete events, not a character stream:

| Kind | Shows |
|---|---|
| `user` / `text` | the conversation |
| `thinking` | a token count and duration, not prose |
| `tool` | a disclosure row, matched to its result **by id** — results interleave with text and can arrive out of order |
| `error` | in the transcript, not a toast: a failed turn is exactly the thing you scroll back to find |
| `silent` | the turn-integrity states from §7 |
| `handoff` | provenance, so a tab you return to says where it came from |

**Shortcuts:** `⌘K` search · `⌘T` mode entry · `⌘⇧H` handoff · `⇧⇥` cycle effort · `⌘V` paste image.

**SSE on POST**, not `EventSource` — the latter cannot carry the mandatory auth header.

**Status block, four rows:** cwd · branch · model · clock; context % · 5h/7d windows · live/max sessions; mode state; artifact chips.

**No cost is shown as spend.** Under a subscription the figure is notional. Limits are the real currency. Settings shows a lifetime list-price total stated as not charged, and two rules keep it honest: the column is named `list_cost_usd`, with a test enforcing that any cost column names itself list price, and `/v2/billing` returns `charged: false`. **Overage is the one exception that can mean money** and the only thing that raises a banner — alerting on anything else trains the alarm to be dismissed.

**Design tokens** (`shell/tokens.css`): ground `#0f0f0f` · surface `#161616` · elevated `#1c1c1c` · line `#2a2a2a` · ink `#cccccc` / dim `#8a8a8a` / faint `#6a6a6a`. Accents, one `--accent` per context: Faber `#e53311` · Noctua `#eca207` · Vesper `#953ead` · Maintenance `#da5b00`. Mono is Cascadia Code, sans is `system-ui`. Press Start 2P and the indigo world ramp are retired.

---

## 13. Telemetry and hooks

Two, both non-blocking, both given the mode via `NOCTIS_MODE`:

- **`PostToolUse`** → `hooks/log_action.py`, one line per tool call to a per-job runtime log
- **`SessionEnd`** → `hooks/mark_session_end.py`, clears the busy flag

**Not `Stop`.** `Stop` fires after *every agent turn*, not at session termination. Registering on it shipped briefly and was caught when busy expressions flipped to idle mid-session.

**Hooks are composed into `--settings` as inline JSON**, because they need absolute interpreter and script paths that cannot be committed. They used to live in a per-mode `settings.json` that is no longer read — a silent break, since a hook that stops firing reports nothing. A test asserts the scripts exist on disk.

**Their role narrowed rather than ended.** Sessions the orchestrator hosts get telemetry from the `stream-json` it already parses, so hooks are the path for sessions Noctis does *not* host. That makes the runtime-log format a real interface rather than an implementation detail.

Runtime logs live in `backend/runtime/` — high-churn, ephemeral, gitignored. **Not vault content.**

---

## 14. Maintenance and the scheduler

**`launchd`, fires on wake.** Morning brief · vault auto-commit and push (secret-scan first) · maintenance. Exits if already run today.

**Audit → Propose → Apply, propose-never-commit.** Every proposal is accepted or rejected by hand. `POST /nightshift/inbox/{id}/accept` applies *before* removing from the inbox, so a failed apply leaves the item pending rather than losing it.

**The brief is generated in two halves.** Facts are counted in Python — open jobs, ages, inbox, where the last session got to. The prose is written by a cheap-tier session from those facts and nothing else, which is what makes it read like a person rather than assembled fields. One paragraph, three sentences at most. **If the prose call fails the brief still renders**, because the rows are the part that must not be missing.

**The worklist is hand-kept**, not generated. A generated worklist is the job list under a second name, and the two would disagree the moment one drifted. It is also the only thing here that is *yours* rather than derived. Editable in place through `PUT /worklist`.

**Per-item fault isolation:** each item's advance step is wrapped, so one failing call logs and continues rather than aborting the run and dropping every other independent item.

---

## 15. Design Lodge

A vault-native catalog of design assets — components, layouts, palettes, typography, icons, motion. Cross-project, seeded from what has already shipped, checked before Faber reaches for anything new during Plan or Build.

A **quick-capture inbox** takes a link plus a note; the next dev session sorts it opportunistically, so filing something properly costs no context switch. Vault-only in v2 — no UI tab.

---

## 16. Running it: two paths

| | `make dev` | `make browser` |
|---|---|---|
| Window | native Tauri window | browser tab at `:5180` |
| Backend | supervised by `backend/supervise.py` | `uvicorn --reload` |
| Typecheck | `[tsc]` stream | `[tsc]` stream |
| Vite | started by `tauri dev` | started directly |

**You develop in the window you use.** `make dev` is the app; `make browser`
is the fallback for backend-only work where a Rust build is not worth paying
for. **Product capabilities are identical** — everything else is backend or frontend code.
`make open-app` is a double-clickable bundle around `make dev`. `make reload`
kills the backend so the supervisor restarts it on new code — a deliberate
restart takes the same path as a crash, which is the point of crash-only
design rather than a special case beside it.

**Why the shell is Tauri.** A Rust window around the OS's WebView. VS Code
uses the same architecture — Electron is Chromium plus Node — and Tauri is
that minus the bundled Chromium. It buys global hotkey summon, tray and
launch-at-login, which are load-bearing for an app whose whole premise is
being one keystroke away. Closing hides rather than quits.

**Supervision.** `backend/supervise.py` polls `/health` rather than the
process table, because a process can be alive and wedged. It backs off 1s→30s
and then gives up with a reason, because a supervisor that never quits makes a
permanent fault invisible. It reaps before respawning, because the probe fires
for a wedged process too and spawning beside one leaves it holding the port.

**The supervisor and `--reload` cannot coexist**, which is why each path has
exactly one: a reload is indistinguishable from a death to a health probe, so
the supervisor would reap the process the reloader just started. Observed
live — writing `supervise.py` triggered a reload and a probe failed during
the window.

**What it does not buy.** Sessions are subprocesses of uvicorn, so a backend
restart still kills a turn in flight. Supervision shortens downtime; it does
not prevent loss. See §18.

---

## 17. What v1 left behind

Removed at the 2026-09-12 cutover: `desktop/app.py` (the pywebview shell,
which `make app` still pointed at for five days after Tauri shipped),
`World.tsx`, `ProfileOverlay.tsx`,
`DesignLodge.tsx`, `modes.ts`, `api.ts`, v1's `index.css` and `App.tsx`; the
`mode`, `session`, `nightshift` and `design_lodge` routers; `launch_surfaces.py`
and every mode config directory. The VS Code and Terminal.app launch paths
went with them — v2 hosts sessions rather than launching them elsewhere.

What survived, and is load-bearing: `vault_io.py`, `backend/hooks/`, the
`nightshift/` package (the scheduler's logic, distinct from its deleted
router), `assets/characters/`, and the vault itself. `assets/world/` retired
with the pixel scene; the sprites keep sole-source-of-truth status, because
with the world gone they are the only carrier of Noctis's visual identity.

## 18. Capability contract

`backend/capabilities.py`. Each mode declares what its methodology assumes it can reach; the harness reports what it has; the gap is printed.

```bash
make doctor                      # per-mode gaps, alongside up/down state
python -m capabilities           # exits non-zero on a gap
python -m capabilities --migrate # the harness-migration brief
```

Built because `dev.md` mandates Impeccable, the code-review plugin, a Critic subagent, Playwright, shadcn/Magic MCP and CodeRabbit — and a Noctis-launched Faber session could reach none of them, for months. **A requirement written in prose and a capability installed in a config root never meet on their own.**

Requirements live in code, not the vault: they are claims about *infrastructure*, not method, and a harness requirement in a mode file would make the methodology depend on which machine reads it.

---

## 19. Portability

**"Workflow agnostic" means a move states what it costs, not that everything survives it.**

| Tier | What | Portable |
|---|---|---|
| Text | methodology, overlays, agent definitions, the vault | inherently |
| MCP | retrieval **and** identity (`tools/*` + `prompts/*`) | by standard |
| Harness config | permissions, hooks, spawn flags, `stream-json` shape | **no** |

Tier 3 is confined to three files under the `events.py` seam: `driver.py` (argv), `parser.py` (stream shape), `permissions.json` (policy).

**`--migrate`** emits a brief describing Tier 3 as *intent* rather than as settings — nine sections covering MCP wiring, per-session identity, permissions, effort, prompt answering, hooks, the turn events the interface needs, working directories, and how to check yourself. Deliberately not a config file: a settings file in one harness's schema is worthless to another, but a statement of what the configuration is *for* is not.

**No multi-harness adapter, deliberately.** One harness, and an abstraction with a single implementation encodes guesses about the second rather than knowledge of it. Build it against a real second harness.

**Bring-your-own-subscription is already in place.** Noctis drives the vendor's own CLI rather than calling an API with a key — `list_cost_usd` is notional and `Limits` reports windows, not dollars. Extending to other providers is N× driver and parser, each drifting independently, not a licensing wall. Provider terms differ on scale, sharing and resale; personal single-seat use is the intended path.

**Licensing is load-bearing.** Anthropic's Agent SDK terms forbid third-party developers offering claude.ai login or subscription rate limits *in distributed products*. Running the CLI on your own machine under your own subscription is using Claude Code, not redistributing it. **The permanent multi-user/hosting exclusion is what keeps this onside.**

---

## 20. Configuration

Two variables are required. Everything else has a working default.

| Variable | Required | Default | Does |
|---|---|---|---|
| `VAULT_PATH` | **yes** | — | Vault root, absolute. Every durable read and write goes here. |
| `NOCTIS_API_TOKEN` | **yes** | — | Bearer token on every route except `/health`. |
| `VITE_API_TOKEN` | **yes** | — | The same token, for the shell. Vite inlines it into the bundle — acceptable only because this is a local single-user app on localhost. |
| `VITE_API_BASE` | no | `http://localhost:8000` | Where the shell reaches the backend. |
| `PORT` | no | `8000` | Backend listen port. Change `VITE_API_BASE` and `NOCTIS_BACKEND` to match. |
| `NOCTIS_MAX_CONCURRENT` | no | `4`, max `9` | Sessions that may run at once. A budget on the 5-hour window, not a machine limit. Above 9 is clamped, with a log line naming `MAX_CONCURRENT_CEILING` — raise it there if you need more. |
| `NOCTIS_CLAUDE_BIN` | no | PATH, then common install paths | Absolute path to `claude`. Needed for a non-standard install, or to pin a build. |
| `NOCTIS_DATA_DIR` | no | `backend/data/` | SQLite history and the search index. |
| `NOCTIS_HISTORY_DB` | no | derived | Explicit DB path for the MCP server, which runs as its own process. |
| `NOCTIS_BACKEND` | no | `http://127.0.0.1:8000` | Where the MCP server reaches the backend. |
| `NOCTIS_RECAP_MODEL` | no | `claude-haiku-4-5` | Model for the one-line recap on a restored conversation. |
| `NIGHTSHIFT_DISTILLER_MODEL` | no | `claude-haiku-4-5` | Model for overnight lessons distillation. |
| `NOCTIS_SCRATCH_ROOT` | no | `~/Developer` | Where Plan-stage scratch directories go before a project is named. |

`NOCTIS_MODE` and `NOCTIS_JOB_ID` are set **by** the launcher for the telemetry hooks. Do not set them yourself.

`ALLOWED_ORIGIN` is a constant in `auth.py` (`http://localhost:5180`), not an environment variable — the port is pinned with `strictPort` so it does not collide with other projects' dev servers.

---

## 21. Troubleshooting

Start with `make doctor`. It answers most of this in three lines.

| Symptom | Cause | Fix |
|---|---|---|
| App loads, nothing responds | Backend is *absent*, not broken. Under `make dev` the supervisor should have caught it; under `make browser` there is no supervisor, so a dead backend leaves Vite serving a UI pointed at a closed port. | `make reload` — kills uvicorn so the supervisor restarts it on current code, keeping the frontend's state |
| `make doctor` says `imports FAIL` | A real code error | `cd backend && .venv/bin/python -c "import main"` and read the traceback |
| `capabilities` shows a `GAP` | A methodology references a tool this machine cannot reach | Install it, or amend the methodology — do not leave it |
| A session asks permission for `vault_search` | The shared allowlist did not reach the spawn | `ps -axo args \| grep -- --settings` |
| Session says the vault is unreadable | It has the directory but not the path | `VAULT_PATH` must be set for the **backend's** process; the composed prompt states the absolute root |
| No plugins or skills in a session | Something still sets `CLAUDE_CONFIG_DIR` | `ps eww <pid> \| tr ' ' '\n' \| grep CLAUDE_CONFIG_DIR` — should find nothing |
| `Not logged in` | Credentials are Keychain-keyed to the config-dir path | Run `claude` once in a terminal |
| Engine not found under `launchd` | `launchd` gives a bare `PATH` with no Homebrew | Set `NOCTIS_CLAUDE_BIN` to the absolute path |
| Typecheck passes, build broken | `tsc --noEmit -p tsconfig.json` checks **zero** files | Always `npm run typecheck` (`tsc -b`) |
| A turn ends with no summary | The closing pass could not resume | A failed close is swallowed by design; the original turn is intact |
| Transcript blank after tool calls | An older build without the turn-integrity fields | Restart the backend — the wire fields are new |

---

## 22. Testing

```bash
make test        # pytest + tsc -b + vitest
```

438 backend, 80 frontend.

**Two traps worth knowing**, both of which shipped as bugs:

- **`tsc --noEmit -p tsconfig.json` checks zero files.** It is a solution-style config with `"files": []`, so the natural invocation exits 0 on a broken tree — it reported a clean typecheck on a genuinely broken one. Always `npm run typecheck`, which is `tsc -b`.
- **`conftest` repoints `VAULT_PATH` at a tmp dir for every test.** A test describing *this machine* must pin the real vault explicitly, or it passes alone and fails in the suite — worse than either.

**`oxlint` is not the safety net for undefined identifiers.** It has no `no-undef` and stays silent; `tsc` catches them.

---

## 23. Known gaps

**Outstanding:**
- The `launchd`-on-wake scheduler — the only feature left in the build order. `brief/generate.py` writes the brief; nothing fires it, and the vault auto-commit/push job does not exist.

**Known and accepted:**
- `--effort` and `--agents` reach in-app sessions only, not the Terminal or VS Code surfaces.
- The brief page renders whatever `brief/today.md` last held, with no staleness indicator. `POST /v2/brief/generate` exists and nothing in the shell calls it, so a brief only refreshes when something asks — which today is nothing. The scheduler is the fix; until it lands, a stale brief looks exactly like a current one.
- Whitespace-only text counts as speech — judging quality would be the guesswork §7 replaced.
- `seven_day_opus` is in the CLI binary and absent from an observed Haiku run. Unverified.
- `--input-format stream-json` as a persistent bidirectional session is untested; it would address ~1.9s spawn-per-turn latency.

**Permanently out of scope:** multi-user or hosting · code editing / custom IDE · any deployment story.
