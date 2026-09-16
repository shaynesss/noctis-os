# Noctis OS — Documentation

The reference. Every subsystem, what it does, and why it behaves the way it does.

| If you want | Read |
|---|---|
| What Noctis is, and how to run it | [`README.md`](README.md) |
| **How each part works** | this file |
| What the architecture *is*, as a spec | `second-brain/wiki/Noctis OS/SPEC.md` (the vault; the build's own record) |
| **Why** a decision was made — evidence, risks, what failed | `second-brain/wiki/Noctis OS/noctis-v2-SPEC.md` |
| What works today | [`STATUS.md`](STATUS.md) |
| What changed when | [`CHANGELOG.md`](CHANGELOG.md) |

---

## 1. The shape

Two halves that age differently.

**The brain** — a markdown vault plus an MCP server that makes it queryable. Ranked retrieval over years of decisions, every job's working context, each mode's methodology. Stdio JSON-RPC, no Noctis-specific dependencies. Any MCP client can use it.

**The body** — whatever runs sessions. Today: a Tauri shell hosting the Claude Code CLI in a pseudo-terminal, and a FastAPI backend behind it.

The body is replaceable and built to be. The brain is meant to outlive it. Everything below is organised around that split — §2–§5 are the body, §6–§9 the brain, §10–§17 the surfaces and cross-cutting concerns, and §18–§21 are for operating it.

---

## 2. Anatomy of a session

A session is a real interactive `claude` in a pseudo-terminal. The shell's Rust side (`frontend/src-tauri/src/pty.rs`) opens the PTY and spawns:

```
claude
  --model <mode's model>
  --append-system-prompt "<system.md + overlay + job brief>"
  --agents '<the mode's subagents, JSON>'
  --mcp-config '<Noctis MCP server, JSON>'
  --settings '<permissions.json + statusLine + crossSessionInbound, JSON>'
  --add-dir <vault>
  [--resume <engine session id>]
  ["<first message>"]
```

Built by `backend/interactive.py`, served by `GET /v2/sessions/interactive-args?mode&cwd&slot[&resume_id][&prompt]`. The Rust side knows nothing about modes; the Python side knows nothing about terminals.

| Flag | Why |
|---|---|
| `--append-system-prompt` | The mode's identity, as text in the argv. Nothing per-mode is written to disk, so two sessions of one mode cannot race, and an edited methodology reaches a resumed session. |
| `--settings` | The tracked policy plus a `statusLine` command that POSTs the CLI's own report — windows, context, model, session id, transcript path — to `/v2/sessions/statusline` every five seconds. |
| `--add-dir <vault>` | The engine sandboxes file access to the working directory; a Faber session in a repo could not read its own methodology without this. |
| `--` + positional prompt | A handoff's carried summary, submitted as the session's first message. Behind the terminator, because a summary that opens with a bullet is an argument that opens with a dash, and the option parser exited on one. |

**Four things the PTY host has to get right**, each found by testing rather than reasoning: size the PTY *before* spawning (at 0×0 the TUI exits instantly with no output); coalesce output into ~16ms frames *and flush on silence* (a flush that only runs on the next read strands the tail of a prompt that then blocks for input); kill the session, not the immediate child; keep sessions across a page reload and reattach to them (§22). Bytes cross Tauri's IPC base64-encoded, because a read can split a multi-byte character and xterm.js decodes UTF-8 itself. Measured 2026-09-14 with the batcher isolated under `seq` as the program: 7MB byte-exact and in order in 820ms (51 frames), and a program that prints then goes quiet gets its last frame **20ms** after its last byte rather than when it exits.

**Finding the binary.** PATH first, then `/opt/homebrew/bin`, `/usr/local/bin`, `~/.local/bin`, `~/.claude/local`, in both `engine.py` and `pty.rs`; `NOCTIS_CLAUDE_BIN` overrides. `launchd` starts processes with a bare `PATH` containing no Homebrew.

**`one_shot` is the one place `-p` remains** (`engine.py`): the session recap calls it, on the cheap tier, with every tool refused and `--output-format json`. A scripting mode used for a script — and a script leaves nothing behind: `--no-session-persistence`, so no transcript lands under `~/.claude/projects/` for the indexer to file as a conversation (twenty-seven recaps had been filed as `general` sessions before this was noticed), and `--setting-sources user`, so the repo's own `.claude/settings.local.json` hooks — baked `--mode dev` — do not fire a `dev` SessionEnd for every recap. `--bare` would do both and more, but it refuses OAuth, so it cannot run on the subscription.

---


## 3. System prompt vs system config

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

**Prompt is instruction; config is capability.** Telling a session to run `/impeccable` when the config root has no plugins is handing someone a recipe for a kitchen they do not have — which is exactly what happened: `dev.md` mandates seven tools and a Noctis-launched Faber session could reach none of them, for months, silently. §15 is the fix.

**`CLAUDE.md` straddles both** — it lives in the config root and becomes part of the prompt. That is where this went wrong: to give each mode a different `CLAUDE.md` (a text problem) the code redirected the entire config root (a capability decision), and paid the whole surface to solve it.

**The hierarchy now:**

| File | Holds |
|---|---|
| `~/.claude/CLAUDE.md` → `prompts/system.md` | Universal rules. **Not a mode** — pointing it at `dev.md` made the machine itself Faber and leaked the build process into every session. |
| `<project>/CLAUDE.md` | The project's conventions. Read because cwd is the project. **Describes the project, not the session's identity** — a General session in a Faber-ish repo opened with "Faber here" and had to correct itself. |
| `--append-system-prompt` | The mode. |

**Snapshotting.** `--system-prompt-snapshot` defaults to on, recording the system prompt once per conversation and reusing it verbatim across resumes. `--append-system-prompt` turns it off, so an edited methodology reaches a session already running. Before that, a resumed session kept answering to the prompt it was born with.

---

## 4. Modes

Five session configurations. They differ by **methodology and model, never by capability**.

| Mode | Model | Methodology | Vault folder | Subagents |
|---|---|---|---|---|
| General | Opus 5 | none, by design | — | built-ins only |
| Faber | Opus 5 | `modes/dev/dev.md` | `modes/dev` | `critic` |
| Noctua | Opus 5 | `modes/learn/learn.md` | `modes/learn` | `gap-finder`, `quizmaster` |
| Vesper | Opus 5 | `modes/research/research.md` | `modes/research` | `credibility-checker`, `synthesizer` |
| Maintenance | Haiku 4.5 | `maintenance/audit.md` | `maintenance` | — |

**Two different paths per mode.** `jobs_dir()` and `methodology_path()` are separate functions because maintenance genuinely diverges: it is not under `modes/` at all — methodology, state, jobs, inbox and archive all sit at root-level `maintenance/` since the 2026-09-12 cutover (the methodology moved 09-07, the state followed). One mapping lives in `jobs.py` — it was previously restated in three files, two of which disagreed.

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

## 5. Permissions

**Every mode gets the same tool surface.** `orchestrator/permissions.json` pre-approves `Read Grep Glob WebSearch WebFetch Edit Write Bash NotebookEdit TodoWrite Task` and Noctis's own retrieval tools for every mode. Anything outside the list the CLI asks about in its own terminal — which is where a person is looking — the way it does anywhere. **`git push` is denied outright.**

**Bash is allowed whole.** A curated list can only be as complete as the last time someone extended it, and a session blocked on an unlisted command looks exactly like one that had nothing to say.

**Permission mode and effort are the CLI's own controls.** Shift+Tab cycles the permission mode inside the terminal; effort is set at spawn. `bypassPermissions` is a real flag and deliberately not one you can land on by tapping a key.

**`crossSessionInbound: accept`.** A peer session's message is delivered rather than held and expired; bounded by the socket, which is user-only. Checked against the installed engine: an unrecognised value degrades to holding and cannot take the deny rule down with it.

---

## 6. The Noctis MCP server

`backend/mcp/server.py`. Stdio JSON-RPC, dependency-free — `python3 server.py` and nothing to install. **This is the half that travels.**

**It solves one thing: ranked retrieval from inside a running session.** Sessions already have Read/Grep/Glob, fine for most vault work. Two things they cannot do: **rank** (grep cannot answer "what did I decide about X" when the wording is forgotten) and **reach history** (SQLite, not files).

**A component, not the product.** No UI, no initiative; it cannot spawn sessions or render chat.

### Tools

| Tool | Does |
|---|---|
| `vault_search` | Ranked BM25 over the vault |
| `history_search` | The same over conversation history |
| `job_context` | A job's full record |
| `worklist` | What is in flight across every mode, from each mode's `state.md` (the name predates the brief's retirement; it never read a worklist file) |
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

## 7. Retrieval

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

## 8. The vault

Sole source of truth for **knowledge**. Markdown with YAML frontmatter.

```
second-brain/
├── prompts/            system.md + overlays/<mode>.md
├── modes/<folder>/     <folder>.md · lessons.md · state.md · jobs/<slug>/context.md · agents/*.md
├── maintenance/        audit.md · schedule.md · agents/   (infrastructure, not a mode)
├── wiki/               durable reasoning
├── design-lodge/       design assets + quick-capture inbox
└── log.md · index.md   serialized-writer files
```

**State vs knowledge.** Durable reasoning goes in `wiki/`; volatile state goes in a mode's `state.md`, `lessons.md` and job contexts. The split is what keeps the vault readable as it grows.

**`vault_io.py` is fully native** — no Obsidian dependency, after Obsidian's app-level config hung for reasons unrelated to any vault file. Obsidian is an optional viewer.

**`log.md` and `index.md` go through a single serialized writer.** Per-mode files do not need it — one writer type each.

**Two-tier self-improvement.** Sessions append to `lessons.md` freely, no gate — the automatic, low-stakes tier. Periodically maintenance digests those lessons and drafts a *proposed* diff to the methodology itself, staged for manual accept or reject. **No mode ever rewrites its own or another mode's methodology.**

---

## 9. History and storage

**History is read from the CLI's own transcripts.** Claude Code writes `~/.claude/projects/<slugged-cwd>/<session-id>.jsonl` incrementally for every session it runs — a SIGKILL mid-generation keeps its partial output — and `orchestrator/jsonl.py` indexes those into the `sessions`/`messages`/`usage` tables the history routes, search and Stats read. `POST /v2/sessions/index` files anything new and re-reads anything that has grown — a row remembers how many bytes of its transcript it was read from (`indexed_bytes`), so a session filed while still running catches up on the next pass, in place, keeping its id; the shell calls it when a terminal session ends, Stats on each visit. The mode a session was launched in comes from its status-line report, since the transcript records only the CLI's permission mode. It counts every session on this machine, not only the ones Noctis hosted.

**SQLite, not the vault.** Transcripts are application data; the vault is for knowledge. Markdown transcripts would make every message a git diff.

- One row per session and per turn: tokens in/out, cache read, cache write, model, mode.
- FTS5 index over both vault and history — **one mechanism, zero added dependencies.**
- The index is a **derived cache.** Rebuildable; deleting it loses nothing.
- `promote()` moves worth-keeping material into the vault as a note, mirroring `raw/` → `wiki/`.

Default location `backend/data/`, overridable with `NOCTIS_DATA_DIR`.

---

## 10. The interface

React + Tailwind 4 in a Tauri shell. `frontend/src/shell/` is the v2 client; `main.tsx` imports it and nothing else.

**Rail:** Terminal · Repo · Stats · Settings, and the app opens on Repo. **The commit log is the memory** (2026-09-15): a commit's body is the record of where a piece of work was left, every session's commits close with *where this leaves things* and *what comes next* (a rule in `prompts/system.md`'s Git section, enforced by the push for commits dated after 2026-09-17), and a click on any commit opens its body under it, another closes it — so opening a project is reading where you stopped. The newest opened on its own for one evening and pushed Record and GitHub off the bottom of the module; nothing opens on its own now. A body arrives hard-wrapped at seventy-two columns and the module wraps at its own width, so `reflow` joins the lines inside a paragraph and keeps the blank lines between them, leaving a list's lines alone. Two summaries of the same thing preceded this on the same day — a morning brief (a vault file a scheduler never wrote) and then an Inbox digest (counts composed into sentences, with a presence heartbeat to know "since when") — and both went, because a summary of what the commits say is worth less than the commits. What *arrives* — nightshift's run, its proposals — moved to Settings. **Repo** is the repositories the open terminals are in, one group per repository, the showing terminal's first — `GET /v2/repos?cwd=…&cwd=…`, one `cwd` per terminal, grouped by `git rev-parse --show-toplevel` so two Faber sessions on one project are one group naming both terminals (`faber · 1`, `faber · 3`, the strip's own labels) and a session on another project is a second; directories in no repository come back under `outside`, which the view no longer renders — every mode starts in a repository, and a "not in a repository" section told the reader nothing they could act on there (2026-09-16). With more than one repository the modules lay out like the terminals — a row up to three, a grid after — and each module's commits start folded; alone, a repository's are open. Ten commits show and the rest scroll; subjects wrap rather than truncate. Each repository is one bordered module: a **lid** (name, the branch it is on, the terminals in it as sprite chips on one line; the GitHub link under the title) and then one anatomy, used twice (2026-09-16). A **block** is three cells: the full path of what it is about with the **figures** under it (not on GitHub, behind, uncommitted; a non-zero figure is ink, zero is faint), the **uncommitted files**, and a **Commits fold** whose right edge stacks the push button over the legend so the title stays on one line. The project's block is the repository's path. For a dev job's project a second block follows for the record's path (`<vault>/<notes_path>`, shown in full; the vault has no link there — its GitHub is one click from the vault's own module): its figures are **the record's own** — `ahead` counts the record's unpushed commits, `dirty` the files under the notes paths — because the vault's whole count beside a fold listing three read as a contradiction. A push is still the repository's, so the button carries the vault's count (`vault_ahead`) in its title when it differs. The record's Commits fold shows the record by file, each with the commit that last touched it. GitHub is the last fold. Uncommitted files are a figure and, whenever there are any, the row under it — count and files both in ink, like every other non-zero figure, so the eye ties them together; a module with none lists nothing. The sentence that used to sit there ("N files changed and not committed — a session commits as it goes…") is gone, and the push button, in the signature colour, sits on the fold it pushes (2026-09-16). A fold reading "Uncommitted · 0" was a row that said nothing on most modules (removed 2026-09-16), as was a disabled "Record · not a job's project" row on the vault module. The GitHub half is its own read — `GET /v2/repos/github?slug=owner/name`, three `gh` calls run at once, cached a minute per slug, failures not cached — so the local half is on screen before the network answers. Links leave the app through the shell's `open_url` command (macOS `open`, http(s) only), because the webview ignores `target="_blank"`. Each commit carries the mark of whose work it is, never a trailer, and by evidence first (2026-09-15): the history store indexes every transcript's tool calls with their arguments, so `store.session_for_commit(subject)` finds the session that ran `git commit` with that subject, and that session is the author — whatever tab was open at the time. A session Noctis did not launch (VS Code, a terminal) is filed by its directory: inside a dev job's `project_path`, or a subdirectory of it, it is Faber's (`jsonl.mode_for_cwd`), applied both when a transcript is indexed and when an already-filed General session is read back. Only a commit no transcript claims falls to the old rules: a dev job's project is Faber's; elsewhere the session live in that directory at the time, else any live session, most recently started winning; none, no mark. Before this, a Noctua tab open in the vault all afternoon was credited with thirty commits a VS Code session in the project had made. Each commit also carries its **body** — the record — and, on a Record commit, `via`: `path` when it touches the job's notes, `session` when its author was inside the project. Per group: branch, upstream, ahead/behind, dirty files, the last twenty commits with the unpushed ones marked, and, through `gh` when signed in and the remote is on GitHub, open pull requests with a one-word check state and open issues; GitHub failing leaves the local half intact with a reason. For a repository that is a dev job's project, a **Record** section shows the vault side. Which commits count is defined two ways united (2026-09-15): vault commits touching the job's `notes_path` (`wiki/<Project>/`) and job folder, whoever made them, and vault commits whose author session was inside the project — the log entry, the lesson, the job context a build session writes as it goes, which touch shared files and were invisible under the path rule alone. In git's own order, twenty at most, in the payload. **What the fold shows is the record by file** (2026-09-15, night): one row per record file — every tracked file under the notes paths, every file a session-attributed commit touched, every uncommitted file under the notes paths — with the commit that last touched it (sprite, subject, when, pushed or not), a file never committed first and marked as such, and a click opening that commit's body. Above the rows, one sentence says how far the record trails the code: the newest project commit against the newest record commit (`trails.behind`, seconds; under an hour reads as current, because a session commits code and then its log entry). A second chronological commit list under the project was the vault module's twenty rows twice; the file rows answer the question only this fold can — is the writing about this project current — and they degrade to one row for a one-page project rather than failing. The fold carries the same figures and the same push block as the project (`↑ not on GitHub · ↓ behind · uncommitted`, `push N`), pointed at the vault: a repository pushes as one, so the vault's push is the whole vault's. A session never pushes; the view has the push button instead — `POST /v2/repos/push` runs `git push` as the machine's git identity (yours), reads every outgoing message first and refuses on an attribution line (`Co-Authored-By`, `Claude-Session`, "Generated with Claude Code"), and asks for `force` as a second click when origin holds commits the branch does not, running it as `--force-with-lease`.

**Transcript blocks** are how a *history* transcript renders (read-only, from the store); a live session is the CLI's own TUI in a terminal. The block kinds:

| Kind | Shows |
|---|---|
| `user` / `text` | the conversation |
| `thinking` | a token count and duration, not prose |
| `tool` | a disclosure row, matched to its result **by id** — results interleave with text and can arrive out of order |

**Shortcuts:** `⌘K` search · `⌘T` mode entry · `⌘⇧H` handoff · `⇧⇥` cycle effort · `⌘V` paste image.

**SSE on POST**, not `EventSource` — the latter cannot carry the mandatory auth header.

**Status block, four rows:** cwd · branch · model · clock; context % · 5h/7d windows · live/max sessions; mode state; artifact chips.

**No cost is shown as spend.** Under a subscription the figure is notional. Limits are the real currency. Stats shows a lifetime list-price total stated as not charged, and two rules keep it honest: every name that carries it says `list` (`list_cost`, `list_cost_usd`, `orchestrator/pricing.py`), and `/v2/billing` returns `charged: false`. The figure is priced from tokens — per-model list rates in `pricing.py`, cache writes at the 1-hour TTL the CLI uses — over the same transcripts the token counts are summed from, so cost and counts are one population; `priced_turns` says how many turns the figure covers, short only by models the table does not know. (Summed from the engine's own per-turn figures it covered 120 turns of 8,000 and read 20x low against its own tokens.) **Overage is the one exception that can mean money** and the only thing that raises a banner — alerting on anything else trains the alarm to be dismissed.

**Design tokens** (`shell/tokens.css`): ground `rgba(15,15,15,.62)` · surface `rgba(22,22,22,.72)` · elevated `rgba(28,28,28,.84)` · line `#2a2a2a` · ink `#cccccc` / dim `#8a8a8a` / faint `#6a6a6a`. The three ground tokens are translucent because the window is a macOS vibrancy material (`hudWindow`, `transparent: true`, `macOSPrivateApi: true` in `tauri.conf.json`) — the desktop shows through, blurred. The body must keep painting `--color-ground`; a transparent body shows the raw material with no tint, which reads as a bug rather than glass. The terminal paints with `allowTransparency` so it is not the one solid slab. Accents, one `--accent` per context: Faber `#e53311` · Noctua `#eca207` · Vesper `#953ead` · Maintenance `#da5b00`. **The signature** (`--color-sig`, `#9c3f53`, six steps `--color-sig-1…6` from `#2a0b12` to `#de778a`) is the one hue the interface's own readings are drawn in — usage bars and percentages, the activity ramp, the token bar's shares, the status meters — so a reading is never mistaken for a character's colour; `--color-good` stays for outcomes (diff additions, pushed commits). The body paints the ground once across the window and nothing else paints it — the rail, title strip and status bar carry no background of their own, because a second coat at 0.62 made the chrome a dark frame round a clear pane. Mono is Cascadia Code, sans is `system-ui`. Press Start 2P and the indigo world ramp are retired. **Corners** are three tokens: `rounded-card` (8px) on any panel of content — cards, modules, code blocks, each terminal — `rounded-sheet` (12px) on the launcher, palette and reader, `rounded-control` (6px) on anything pressed or typed into; marks keep tiny radii. **Sheets** paint `--color-sheet` (`#181818`, opaque): they float over the page, not the desktop, and on `surface` the page's text read through them. The terminals are not cards — a terminal is the work surface, not a panel on it — and keep their rules between panes. **Every view centres itself** when shorter than the window. **Border beam** (`Beam` in `Panels.tsx` over `Pools.tsx`): border-beam's "pulse outside · mono" rebuilt (MIT) — thirteen pools at even intervals on the edge at the library's own size, each a distinct spot of light with dark edge between it and the next, painted three times (a 1px stroke masked to the border, a glow centred on the edge, a wide faint bloom) and each with its own periods, drift, swing and phase from its own seed. Cheap by construction: every pool is its own element painted once and moved by `transform` and `opacity` only, the softness in its gradient rather than a filter, so the loop never repaints — the library's stacked-gradient-plus-blur approach re-rasterised the whole card thirty times a second and stalled the interface at this width. On the Stats cards only, in silver; the Repo modules wore it for an afternoon and it looked wrong against the folds. The vibrancy is pinned to its active appearance (`windowEffects.state: "active"` in `tauri.conf.json`) so the window does not wash to grey when another app is in front. **Lifetime tokens** is one stacked bar (`Stacked` in `App.tsx`): the four kinds as shares of one total, greys darkest to lightest, a 2px floor per segment, a dot-and-figure legend beneath.

---

## 11. Telemetry and hooks

Two, both non-blocking, both given the mode via `NOCTIS_MODE`. **A terminal session gets it from `interactive-args`**, which returns an `env` map beside the argv (`NOCTIS_MODE`, and `NOCTIS_JOB_ID` when a job owns the working directory) and `pty_spawn` applies to the child — a PTY child otherwise inherits the shell process's environment, and a vesper session was found logging under whatever mode the shell happened to carry. The env wins over the `--mode` baked into a project's own `.claude/settings.local.json` hooks; those baked values are only a fallback for sessions nothing launched.

- **`PostToolUse`** → `hooks/log_action.py`, one line per tool call to a per-job runtime log
- **`SessionEnd`** → `hooks/mark_session_end.py`, clears the busy flag

**Not `Stop`.** `Stop` fires after *every agent turn*, not at session termination. Registering on it shipped briefly and was caught when busy expressions flipped to idle mid-session.

**Hooks are composed into `--settings` as inline JSON**, because they need absolute interpreter and script paths that cannot be committed. They used to live in a per-mode `settings.json` that is no longer read — a silent break, since a hook that stops firing reports nothing. A test asserts the scripts exist on disk.

**Their role.** A terminal session's telemetry comes from its own `statusLine` report and its transcript on disk; the hooks are what fires on every tool call regardless of who hosts the session, and they write the action feed. That makes the runtime-log format a real interface rather than an implementation detail.

Runtime logs live in `backend/runtime/` — high-churn, ephemeral, gitignored. **Not vault content.**

---

## 12. Maintenance

**One thing runs on a schedule: nightshift, nightly at 03:00.** `bootstrap.sh` step 5 installs `launchd/com.noctis-os.nightshift.plist` (rendered from the template, since launchd expands neither `~` nor variables), which runs `scripts/nightshift_run.sh` → `nightshift/runner.py`, logging to `backend/runtime/nightshift.log`. **It failed every night from its first run (2026-08-05) to 2026-09-15**: launchd's PATH has no Homebrew bin, so every advance step died with `No such file or directory: 'claude'` and the run logged a quiet night — 47 failures over 41 nights, only the flagged-job items (which need no model) ever staged, and no lessons distillation ever ran. Found while checking whether anything was scheduled at all; the script now exports the PATH it needs. The rest of the `launchd`-on-wake job the spec once listed — a morning brief and a vault auto-push — never existed: the commit log is the record (§10), and a vault auto-push is against the push rule. Settings has no Schedule section; running maintenance by hand is `python -m nightshift.runner`.

**Every run is on record** (`nightshift/report.py` → `backend/data/nightshift.json`): when it ran, what staged, what failed and why, sixty nights kept. `summary()` names the newest run's outcome — `staged`, `quiet`, `partial`, or `broken` when every item failed with one error — and how many nights in a row have ended the same way; Settings' Maintenance section prints it as one sentence (`GET /v2/nightshift`), in Faber's red when the night was broken. The runner itself exits non-zero and says "FAILED — every advance failed: …" when the machine is broken, rather than "quiet night". This is the monitoring the six silent weeks lacked: a log that says "quiet" every night is unverified, not fine.

**The prompt regression suite** (`prompts/regression.py`; `prompts/run_regression.py` is its command line; the Settings card is its face). `second-brain/prompts/regression.jsonl` holds one case per line — a mode, a prompt, a deterministic string assertion (`absent` strings must not appear; `contains` is any-of) and a `rule` naming the behaviour it guards: attribution, confusion-protocol, plan-before-code, drift-detection, propose-never-apply, verdict-reasoning, depth-over-breadth, commit-first-log-second, no-fabricated-decisions, state-vs-knowledge, mode-identity. A case runs as one `claude -p` session with the mode's composed prompt in `--append-system-prompt`, exactly as a hosted session receives it, in a neutral working directory so no project `CLAUDE.md` competes. **Scope follows composition:** `cases_for("faber")` is Faber's cases because the overlay is composed into one mode; `cases_for("system")` is every case because `system.md` is composed into all; `rule:<name>` crosses modes. **A failing case reruns once** before it counts. **Three run at a time.** **Each result is recorded** in `backend/data/regression.json` with the hash of the composed prompt it ran against; `status()` marks a result `stale` when the prompt has since changed, so the card's tally — pass · fail · stale · never run — is a true state of the record, not of the last ceremony. Routes: `GET /v2/regression` (cases with last results, scope costs; never runs anything), `POST /v2/regression/run {scope}` (one run at a time, in a thread; 409 while one is going), `GET /v2/regression/status` (progress and results as they land; the card polls it every two seconds).

**Audit → Propose → Apply, propose-never-commit.** Every proposal is accepted or rejected by hand, from Settings' Maintenance section (the Inbox tab until 2026-09-15; the routes keep the name). `POST /v2/inbox/{id}/accept` applies the diff *before* archiving — all hunks or none — then honours the proposal's markers (a lessons cursor to advance, a job to close), drops the entry from `maintenance/state.md`'s index and commits the vault; a diff that no longer applies is a 409 with the reason and the item stays, visibly stale. `reject` archives, drops the entry and commits. The listing joins each file with its index entry (description, rationale, confidence) and derives from the diff what accepting does — which file, how many places — so the row states the consequence before the argument; `full` carries rationale, diff, evidence and confidence for the read.

**Per-item fault isolation:** each item's advance step is wrapped, so one failing call logs and continues rather than aborting the run and dropping every other independent item.

---

## 13. Design Lodge

A vault-native catalog of design assets — components, layouts, palettes, typography, icons, motion. Cross-project, seeded from what has already shipped, checked before Faber reaches for anything new during Plan or Build.

A **quick-capture inbox** takes a link plus a note; the next dev session sorts it opportunistically, so filing something properly costs no context switch. Vault-only in v2 — no UI tab.

---

## 14. Running it: two paths

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
process table, because a process can be alive and wedged. A probe that fails
is confirmed with a longer one (2s, then 10s) before anything is killed,
because a server busy with a slow request answers late, not never. It backs
off 1s→30s and then keeps trying every minute, forever, each attempt logged
with its count — it used to give up after the ladder, and on 2026-09-16 that
turned a two-second stall into an hour with nothing on the port. A permanent
fault is still visible: it is the line that keeps repeating in
`runtime/dev.log`. It reaps before respawning, because the probe fires for a
wedged process too and spawning beside one leaves it holding the port.
`make reload` covers both states: supervisor running, it kills uvicorn and
lets it come back; supervisor gone, it starts one detached.

**The supervisor and `--reload` cannot coexist**, which is why each path has
exactly one: a reload is indistinguishable from a death to a health probe, so
the supervisor would reap the process the reloader just started. Observed
live — writing `supervise.py` triggered a reload and a probe failed during
the window.

**What it does not buy.** Sessions are subprocesses of uvicorn, so a backend
restart still kills a turn in flight. Supervision shortens downtime; it does
not prevent loss. See §16.

---

## 15. What v1 left behind

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

## 16. Capability contract

`backend/capabilities.py`. Each mode declares what its methodology assumes it can reach; the harness reports what it has; the gap is printed.

```bash
make doctor                      # per-mode gaps, alongside up/down state
python -m capabilities           # exits non-zero on a gap
python -m capabilities --migrate # the harness-migration brief
```

Built because `dev.md` mandates Impeccable, the code-review plugin, a Critic subagent, Playwright, shadcn/Magic MCP and CodeRabbit — and a Noctis-launched Faber session could reach none of them, for months. **A requirement written in prose and a capability installed in a config root never meet on their own.**

Requirements live in code, not the vault: they are claims about *infrastructure*, not method, and a harness requirement in a mode file would make the methodology depend on which machine reads it.

---

## 17. Portability

**"Workflow agnostic" means a move states what it costs, not that everything survives it.**

| Tier | What | Portable |
|---|---|---|
| Text | methodology, overlays, agent definitions, the vault | inherently |
| MCP | retrieval **and** identity (`tools/*` + `prompts/*`) | by standard |
| Harness config | permissions, hooks, spawn flags, the `statusLine` payload shape | **no** |

Tier 3 is confined to `engine.py` and `interactive.py` (argv), `jsonl.py` (transcript shape), `permissions.json` (policy), and `pty.rs` (the terminal).

**`--migrate`** emits a brief describing Tier 3 as *intent* rather than as settings — nine sections covering MCP wiring, per-session identity, permissions, effort, prompt answering, hooks, the turn events the interface needs, working directories, and how to check yourself. Deliberately not a config file: a settings file in one harness's schema is worthless to another, but a statement of what the configuration is *for* is not.

**No multi-harness adapter, deliberately.** One harness, and an abstraction with a single implementation encodes guesses about the second rather than knowledge of it. Build it against a real second harness.

**Bring-your-own-subscription is already in place.** Noctis drives the vendor's own CLI rather than calling an API with a key — `list_cost_usd` is notional and `Limits` reports windows, not dollars. Extending to other providers is N× driver and parser, each drifting independently, not a licensing wall. Provider terms differ on scale, sharing and resale; personal single-seat use is the intended path.

**Licensing is load-bearing.** Anthropic's Agent SDK terms forbid third-party developers offering claude.ai login or subscription rate limits *in distributed products*. Running the CLI on your own machine under your own subscription is using Claude Code, not redistributing it. **The permanent multi-user/hosting exclusion is what keeps this onside.**

---

## 18. Configuration

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
| `NOCTIS_RECAP_MODEL` | no | `claude-haiku-4-5` | Model for `one_shot` — the session recap. |
| `NIGHTSHIFT_DISTILLER_MODEL` | no | `claude-haiku-4-5` | Model for overnight lessons distillation. |
| `NOCTIS_SCRATCH_ROOT` | no | `~/Developer` | Where Plan-stage scratch directories go before a project is named. |

`NOCTIS_MODE` and `NOCTIS_JOB_ID` are set **by** the launcher for the telemetry hooks. Do not set them yourself.

`ALLOWED_ORIGIN` is a constant in `auth.py` (`http://localhost:5180`), not an environment variable — the port is pinned with `strictPort` so it does not collide with other projects' dev servers.

---

## 19. Troubleshooting

Start with `make doctor`. It answers most of this in three lines.

| Symptom | Cause | Fix |
|---|---|---|
| App loads, nothing responds | Backend is *absent*, not broken. Under `make dev` the supervisor should have caught it; under `make browser` there is no supervisor, so a dead backend leaves Vite serving a UI pointed at a closed port. | `make reload` — kills uvicorn so the supervisor restarts it on current code, keeping the frontend's state; if the supervisor itself is gone, starts one |
| `make doctor` says `imports FAIL` | A real code error | `cd backend && .venv/bin/python -c "import main"` and read the traceback |
| `capabilities` shows a `GAP` | A methodology references a tool this machine cannot reach | Install it, or amend the methodology — do not leave it |
| A session asks permission for `vault_search` | The shared allowlist did not reach the spawn | `ps -axo args \| grep -- --settings` |
| Session says the vault is unreadable | It has the directory but not the path | `VAULT_PATH` must be set for the **backend's** process; the composed prompt states the absolute root |
| No plugins or skills in a session | Something still sets `CLAUDE_CONFIG_DIR` | `ps eww <pid> \| tr ' ' '\n' \| grep CLAUDE_CONFIG_DIR` — should find nothing |
| `Not logged in` | Credentials are Keychain-keyed to the config-dir path | Run `claude` once in a terminal |
| Engine not found under `launchd` | `launchd` gives a bare `PATH` with no Homebrew | Set `NOCTIS_CLAUDE_BIN` to the absolute path |
| Typecheck passes, build broken | `tsc --noEmit -p tsconfig.json` checks **zero** files | Always `npm run typecheck` (`tsc -b`) |
| Terminal opens and the prompt is cut mid-sentence | An old shell build; the PTY host flushed only on the next read | Restart `make dev` — the batcher flushes on silence now |

---

## 20. Testing

```bash
make test        # pytest + tsc -b + vitest
```

438 backend, 80 frontend.

**Two traps worth knowing**, both of which shipped as bugs:

- **`tsc --noEmit -p tsconfig.json` checks zero files.** It is a solution-style config with `"files": []`, so the natural invocation exits 0 on a broken tree — it reported a clean typecheck on a genuinely broken one. Always `npm run typecheck`, which is `tsc -b`.
- **`conftest` repoints `VAULT_PATH` at a tmp dir for every test.** A test describing *this machine* must pin the real vault explicitly, or it passes alone and fails in the suite — worse than either.

**`oxlint` is not the safety net for undefined identifiers.** It has no `no-undef` and stays silent; `tsc` catches them.

---

## 21. Known gaps

**Outstanding:**
- Nothing in the build order. The `launchd` scheduler that was its last item is no longer needed: the commit log is the record and needs no writer, a vault auto-push is against the push rule, and maintenance runs nightly on its own plist.

**Known and accepted:**
- Effort is not yet passed at spawn (`interactive-args` does not take it); the CLI's default applies until it is.
- Commit attribution by transcript matches on the subject line: two commits with one subject (a repeated "wip") both credit the first session that ran it, and a subject under twelve characters is not searched at all and falls to the by-clock rules.
- Whitespace-only text counts as speech — judging quality would be the guesswork §5 replaced.
- `seven_day_opus` is in the CLI binary and absent from an observed Haiku run. Unverified.

**Permanently out of scope:** multi-user or hosting · code editing / custom IDE · any deployment story.


---

## 22. The Terminal — the real CLI, hosted

**Shipped 2026-09-13 beside the `stream-json` transcript; the transcript and the orchestrator behind it were deleted 2026-09-14.** The terminal is the conversation surface. The migration record (`PTY-MIGRATION.md`, in the vault's `wiki/Noctis OS/` since 2026-09-15) has the full reasoning; this section is what exists, and §2 is the spawn.

**Why.** Noctis drives `claude -p` — "print response and exit" in the CLI's own
help — once per turn, and much of the orchestrator exists to rebuild the
interactive loop on top of a scripting mode: the closing pass, the permission
host, per-turn respawn, `TurnEnd` bookkeeping. Run interactively, the loop is
the CLI's own.

**The split.** `frontend/src-tauri/src/pty.rs` owns the terminal and knows
nothing about modes. `backend/interactive.py` owns the mode and knows nothing
about terminals. The shell asks `GET /v2/sessions/interactive-args` for an
argv and hands it to `pty_spawn`.

**Four things the Rust side has to get right**, each found by testing:

| | |
|---|---|
| Size the PTY **before** spawning | at 0×0 the TUI exits instantly, no error, no output |
| Coalesce reads into ~16ms frames, **and flush on silence** | every chunk is serialised across Tauri's IPC; one event per read stalls a fast-printing session. But a flush that only runs on the *next* read strands the last frame of a prompt that then blocks for input — the trust dialog rendered to mid-sentence until a keystroke made the CLI repaint. A quiet frame sends what it holds; that needs a batcher thread separate from the blocking reader |
| Kill the session, not the process | the immediate child is not the only thing holding the terminal |
| Keep the page running while the window is hidden | closing hides to the tray, and WebKit suspends a web view that is not in a window — the status bar froze, the arrangement stopped being remembered. `backgroundThrottling: disabled` in the window config (`WKInactiveSchedulingPolicy::None`); the sessions never stopped either way |
| Keep the session across a page reload, and let the shell **reattach** | the registry outlives the web view. Each session keeps a capped 2MB scrollback with its frames numbered; `pty_attach` returns the replay, the last frame it contains, and whether the process has since exited. The shell holds frames while replaying and writes only those numbered past the snapshot. Two things on the shell side follow: ending a session is an intent (⌘W, `r`), never an unmount's side effect — StrictMode's mount → cleanup → mount killed the session the first attempt came back to attach to; and nothing in the mount path may wait on `requestAnimationFrame` alone, which WebKit suspends while the window is occluded |

Bytes cross the IPC **base64-encoded**. A read can split a multi-byte
character, and xterm.js has its own UTF-8 decoder that holds the seam.

**Spawns queue; attaches do not.** A restored arrangement of six tabs used to
boot six `claude` processes (270–310 MB each, plus the MCP servers each one
inherits from `~/.claude.json`) in the same second, and the machine shed the
stack for memory. `Terminal.tsx` serialises real spawns 700 ms apart; a tab
reattaching to a session the PTY registry kept skips the queue.

**The status bar has a second source.** `statusLine` is a command the CLI runs
on every render, handed a JSON payload on stdin: `rate_limits.five_hour` and
`seven_day`, `context_window`, `effort`, `cost`, `session_id`,
`transcript_path`. `backend/scripts/statusline.sh` POSTs it to
`/v2/sessions/statusline`. Unlike the stream this **survives a page reload**,
because the numbers live in the backend rather than in React state.

**History becomes something read, not recorded.** `orchestrator/jsonl.py`
reconstructs a conversation from `~/.claude/projects/**/*.jsonl` — messages,
tool calls with their ids, thinking blocks, per-turn usage, and the CLI's own
`aiTitle`. Verified against three failure shapes: a clean short session, one
SIGKILLed mid-generation (its partial output was **already on disk** — the file
is appended live, not flushed at exit), and a resumed one (appends, no fork).

**Thinking blocks are kept even with no text.** Models default to
`display: "omitted"`, so reasoning is billed and never returned; all 34 blocks
in the first real transcript were empty. The transcript renders thinking as a
counter, so the block's existence is the signal — guarding on its text dropped
every one.

**Lifetime tokens: one raw number.** No split, no tiers. The CLI's own
background calls are absent from the JSONL, which is 0.178% of the total.

**The indexer runs beside the recorder, and the comparison is live.**
`POST /v2/sessions/index` files every transcript history has not seen and
re-reads every one that has grown since it was filed — the shell calls it when
a terminal session ends, Stats calls it on each visit. Rows
carry `source` (`recorder` | `transcript`) so the comparison only tests
sessions the recorder itself wrote. `GET /v2/sessions/stats` returns
`transcripts` (the lifetime figure read from disk) and `diff` (per-session
recorded vs transcript) beside `lifetime`.

**First honest run, 2026-09-13: 1 of 16 agree, and the recorder is the one
that is wrong.** Every disagreement runs the same way — transcript 2–5×
larger — and on the session checked field by field, *output* tokens are 2×
too (6,486 recorded, 13,252 on disk; 4 usage rows for 29 API calls). Cache
reads can be inflated by per-call re-reads; generated output cannot. So
`result.usage` is not the whole turn, and the recorder has undercounted since
it was written — the 09-08 fix corrected the model's *name*, not its number.
The transcript is the more complete source. What `result.usage` actually
contains is the open question; switching Stats to `transcripts.tokens` is
step 4 and has not been done.

**Several terminals, kept alive.** `Terminals.tsx` holds a strip of them and
stays mounted whichever rail item is showing — the first version unmounted on
Stats, and unmounting a terminal kills its session. Slots are their own strip
rather than a fourth kind of Chat tab, because a Chat tab is a conversation
the orchestrator owns and a terminal owns itself.

**Keys inside a terminal belong to the CLI.** The shell's key handler runs in
the capture phase, before xterm, and binds Shift+Tab, Escape and the arrows —
all of which Claude Code's TUI uses. Every ⌘-chord (⌘K/T/W/⇧H/1–9) stays with
the shell; everything without ⌘ passes through. VS Code's split.

**The status bar is live, and reads the terminal on screen.** `/v2/sessions/limits`
is polled on the same four-second cadence as the live counter. With a terminal
showing, the bar's cwd, model and context come from that terminal's own
`statusLine` report — keyed by the slot name the strip gave it, which rides
out in the status-line command and comes back with each report — rather than
from the Chat tab behind it. `refreshInterval: 5` keeps an idle terminal
reporting, so `/model` inside it reaches the bar without a redraw.

**A reading has an age.** A hosted session only learns the 5h/7d windows from
its own API responses, so an idle terminal repeats one figure while other
sessions move the account on — 33% in the bar beside 36% in the CLI. Nothing
can make that fresher without an API call, so the bar says "· 4m ago" once a
reading is a minute old. `reported_at` is stamped by identity on the backend,
so it is right whichever door the reading came through and does not advance
just because the bar polled.

The Chat composer is not rendered under a terminal — it sends to General, and
beneath a terminal with its own prompt it read as a second place to type.
Terminal labels are positional (1, 2, 3 for whatever is open), and tabs reorder by dragging — the order on screen is the order under ⌘1–9; the strip's empty space drags the window. The first
version showed lifetime ordinals from a counter that StrictMode double-ran.
Each tab carries its mode's mark — the character's sprite from
`assets/characters/`, the Noctis star for General — and the Repo view names
terminals with the same mark, so a terminal is one picture in both places.

**Split screen.** Slots sharing a `group` are shown together as equal cells
— a row up to three, a grid from four (2×2, 3×2, 3×3) — each terminal
fitting its own cell, the focused one under a rule in the mode's accent.
Tabs drag to reorder; inside Tauri that needs `dragDropEnabled: false` on
the window, or the native drop handler swallows the HTML5 drag. A group's
bracket drags as one module and its tabs do not drag on their own; a drop
onto a grouped tab lands before the whole bracket. `⌘⇧-number` splits the showing terminal with that tab or
unsplits it; each tab has `⊞`/`⊟` on hover. The strip brackets a split's tabs
as one run — joining moves the tab beside its group — so the tab bar says
which terminals share the screen. Selecting a grouped tab shows the group
with that one focused; selecting an ungrouped tab shows it alone. A group of
one is cleared. Groups are part of the remembered arrangement.

**No session opens empty.** A fresh terminal (not a resume) is spawned with an
opening prompt asking it to say which mode it is, what the session is for and
where it is: a bare prompt looks the same whether the methodology loaded or
not. **Where a mode starts** (`GET /v2/mode-dirs`): General and the vault-native
modes at the vault; Faber in the projects directory (`PROJECTS_DIR`, else
`~/Developer/projects` — the 2026-08-29 layout — else `~/Developer`, else the
parent of the last project used) — which project a
build session is for is the session's to establish, so the launcher does not
pre-decide it with the last repo used. The directory follows the mode in the
launcher until you type one.

**Styling is the shell's.** xterm.js ships no look of its own: the theme is
generated from `tokens.css`, so ground, ink and the character accents are the
same values the cards use, and a tab's terminal can carry its mode's accent.
`fontWeight: 450` is deliberate — WKWebView rasterises glyphs lighter than
Terminal.app, and Cascadia Code is vendored as a 200–700 variable font.
WebGL2 where available, DOM renderer where not.
