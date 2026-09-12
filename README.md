<h1 align="center">Noctis OS</h1>

<p align="center">
  A desktop client for Claude Code, shaped around five modes and one compounding vault.
</p>

<p align="center">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-blue.svg" />
  <img alt="status" src="https://img.shields.io/badge/v2-mid--build-orange.svg" />
  <img alt="platform" src="https://img.shields.io/badge/platform-macOS-black.svg" />
  <img alt="tests" src="https://img.shields.io/badge/tests-437%20%2B%2080-brightgreen.svg" />
</p>

---

> [!WARNING]
> **This runs Claude Code with write access to your machine and your vault.** Sessions can edit files, run shell commands, and write markdown into `VAULT_PATH`. Read [Blast radius](#blast-radius) before pointing it at anything you care about.

## What this is

Noctis OS **hosts** Claude Code sessions rather than launching them somewhere else. It drives the CLI as a subprocess, streams its output into its own transcript, and gives each session a **mode** — a methodology, a job context, and a set of subagents, all read from and written back to one markdown vault.

Five modes, differing by *method*, never by capability:

| Mode | For | Model |
|---|---|---|
| **General** | Questions, comparisons, anything unscoped | Opus 5 |
| **Faber** | Build: spec, implement, ship | Opus 5 |
| **Noctua** | Learn: read closely, explain, retain | Opus 5 |
| **Vesper** | Research: gather, weigh, return a verdict | Opus 5 |
| **Maintenance** | Audit the vault and propose repairs | Haiku 4.5 |

It runs on an existing Claude subscription with no API billing — a constraint that shapes the whole architecture. Single-user, single-machine, public as a working example rather than as something to deploy.

<!-- SCREENSHOT WANTED: the v2 shell — transcript mid-turn, a tool-call
     disclosure open, the effort chip visible. Capture with:
       screencapture -iW assets/readme/v2-shell.png
     then replace this comment with the image. The only v1 image left in the
     repo is the world screen, which is the old launcher, not this app. -->

## Why it exists

Before this, a single universal `CLAUDE.md` — a build process — was read by every session, whether the work was building software, reading a paper, or triaging notes. Correct for dev, actively wrong for everything else: a research session loaded an entire spec-and-ship pipeline it had no use for.

**v1** generalised that one process file into five and launched each mode into a separate surface — VS Code for dev, a colour-tinted Terminal window for the rest — then read state back from the vault. Fire-and-forget: the interface could start a session and watch its telemetry, but never see the conversation.

**v2 is the consequence.** Launching *into* other applications meant Claude Desktop stayed the real entry point, and three things were impossible by construction: live session monitoring, cross-mode search, and durable conversation history. So the app hosts sessions itself.

## How it works

```mermaid
flowchart LR
    subgraph Shell[Tauri shell · React]
        UI[Transcript · tabs · palette]
    end

    subgraph Backend[FastAPI]
        Orch[Orchestrator<br/>spawn · stream · resume]
        MCP[Noctis MCP server]
        Store[(SQLite FTS5<br/>history + index)]
    end

    Vault[(Vault<br/>markdown + frontmatter)]
    CC[claude -p<br/>stream-json]

    UI <-->|SSE on POST| Orch
    Orch -->|argv: methodology, agents,<br/>effort, permissions| CC
    CC -->|events| Orch
    CC <-->|tools + prompts| MCP
    MCP <--> Vault
    Orch <--> Store
    Store -.->|promote| Vault
```

**The orchestrator** spawns `claude -p --output-format stream-json`, parses the stream into a normalised event union, and streams that to the shell. Two concurrent sessions, queued rather than refused — the cap is a budget on the 5-hour window, not a resource limit. Sessions resume by engine session id, so a follow-up turn continues the same conversation and closing the window loses nothing.

**A mode is passed in, never inherited.** Its methodology travels in the argv via `--append-system-prompt`, its subagents via `--agents`, its permissions and telemetry hooks via `--settings`. Nothing per-mode is written to disk, so two sessions of one mode cannot race on a config file — and an edited methodology reaches a session that is already running.

**Sessions run against the real `~/.claude`.** They inherit every installed plugin, skill, subagent, MCP server, accumulated permission and memory — the same surface an ordinary Claude Code session has.

**The Noctis MCP server** serves both MCP primitives. `tools/*` gives retrieval — `vault_search`, `history_search`, `job_context`, `worklist`, `propose` — over BM25 via SQLite FTS5, measured at 80% recall@20. `prompts/*` gives *identity*: `enter_faber` and its siblings load a mode's methodology and job context. Dependency-free stdio JSON-RPC, so any MCP client can speak to it.

**The vault is the only database** for anything durable — markdown with YAML frontmatter, one directory per mode. No ORM, no migrations. SQLite holds conversation history and the search index: machine state, deliberately not vault state, with an explicit `promote()` for anything that earns a place in the vault.

**Every working turn closes itself.** Claude Code's `Stop` hook can force a model to keep working, but it does not fire under `--print`, and the Agent SDK that does support hooks requires API-key auth — the metered path this architecture avoids. So the manager does it: any turn that used tools is resumed once and asked for a handback. A turn that already closed properly answers `closed`, which never reaches the transcript.

## What v2 does that v1 could not

- **Live transcripts.** Every turn renders as it streams — text, tool calls with their targets, thinking-token counts during a pause, real usage against the subscription window.
- **Durable history.** Conversations restore on launch. `⌘K` searches across every mode's history.
- **Mode entry and handoff.** `⌘T` opens a session in any mode; `⌘⇧H` hands the current one over, carrying a summary rather than the transcript.
- **Effort as a control.** The composer chip cycles `low`/`medium`/`high`/`xhigh`, applied to the next turn — immediate, since every turn is its own spawn.
- **Permission requests you can answer.** A request surfaces as a dialog and waits.
- **Silence, refusal and truncation are visible.** A turn ending with tool calls and no text renders as *"turn ended mid-work"*; one refused its tools as *"turn ended blocked"* with the refusals named; one cut off at the output ceiling as *"turn hit the output limit"*. A blank transcript used to be indistinguishable from a crash.
- **A capability contract.** Each mode declares what its methodology assumes it can reach, the harness reports what it has, and `make doctor` prints the gap.

## What carries over from v1

- **Two-tier self-improvement.** Sessions append freely to a mode's `lessons.md`, no gate. Periodically, maintenance digests those lessons and drafts a *proposed* diff to the methodology itself, staged for manual accept or reject. No mode silently rewrites its own process.
- **A propose-only overnight worker.** Runs on `launchd`, drafts into a staging inbox, commits nothing.
- **Design Lodge.** A vault-native catalog of design assets, checked before Faber reaches for anything new.
- **Telemetry hooks.** One line per tool call to a per-job runtime log, plus a session-end hook that clears the busy flag.

---

# Operating it

## Requirements

macOS · Python 3.11+ · Node 18+ · [Claude Code CLI](https://claude.com/claude-code) installed and logged in.

```bash
git clone https://github.com/shaynesss/noctis-os.git
cd noctis-os
make setup          # backend + frontend deps, .env.example -> .env
```

## Configuration

Two variables are required. Everything else has a working default.

| Variable | Required | Default | What it does |
|---|---|---|---|
| `VAULT_PATH` | **yes** | — | Absolute path to the vault root. Every durable read and write goes here. |
| `NOCTIS_API_TOKEN` | **yes** | — | Bearer token on every backend route except `/health`. Any local secret; it only has to match `VITE_API_TOKEN`. |
| `VITE_API_TOKEN` | **yes** | — | The same token, for the shell. Vite inlines it into the bundle — acceptable only because this is a local single-user app on localhost. |
| `VITE_API_BASE` | no | `http://localhost:8000` | Where the shell reaches the backend. |
| `PORT` | no | `8000` | Backend listen port. Change `VITE_API_BASE` and `NOCTIS_BACKEND` to match. |
| `NOCTIS_CLAUDE_BIN` | no | PATH, then common install paths | Absolute path to `claude`. Needed for a non-standard install, or to pin a build. |
| `NOCTIS_DATA_DIR` | no | `backend/data/` | Where SQLite history and the search index live. |
| `NOCTIS_HISTORY_DB` | no | derived from `NOCTIS_DATA_DIR` | Explicit DB path for the MCP server, which runs as its own process. |
| `NOCTIS_BACKEND` | no | `http://127.0.0.1:8000` | Where the MCP server reaches the backend. |
| `NOCTIS_RECAP_MODEL` | no | `claude-haiku-4-5` | Model for the one-line recap on a restored conversation. |
| `NIGHTSHIFT_DISTILLER_MODEL` | no | `claude-haiku-4-5` | Model for overnight lessons distillation. |
| `NOCTIS_SCRATCH_ROOT` | no | `~/Developer` | Where Plan-stage scratch directories are created before a project is named. |

`NOCTIS_MODE` and `NOCTIS_JOB_ID` are set *by* the launcher for the telemetry hooks. Don't set them yourself.

See [`SETUP.md`](SETUP.md) for the one-time machine checklist (Claude Code login, the `launchd` job).

## Running

```bash
make dev            # backend :8000 + frontend :5180
make doctor         # what is up, what is down, and any capability gaps
make test           # pytest + tsc -b + vitest
make backend        # restart uvicorn alone, leaving the frontend up
```

## Blast radius

What this software can do to your machine, stated plainly.

**Sessions have full tool access.** Every mode spawns with `Bash`, `Edit`, `Write`, `Read`, `WebSearch` and `WebFetch` pre-approved — no prompt. That is deliberate: a mode handed work it cannot perform ends its turn with nothing done and no way to say so. It also means **a session can run any shell command and edit any file it can reach.**

**One thing is denied outright:** `git push`. Commits happen; pushing is manual, always.

**Sessions can reach two directories:** the project they were launched into, and `VAULT_PATH`. The engine sandboxes file access to those. Reaching outside them fails, and that failure is correct.

**It writes to your vault.** Modes append to `lessons.md`, write job contexts, and — for maintenance — stage proposed diffs to methodology files. The vault should be a git repo so you can see and revert what it did. Nothing is committed on your behalf.

**It writes outside the vault too:**
- `backend/data/` — SQLite conversation history and search index
- `backend/runtime/` — per-job action logs, high-churn, gitignored
- `.vscode/tasks.json` in a launched project — the v1 dev launcher's folderOpen task

**`bootstrap.sh` touches your machine**, not just the repo: it creates config directories, installs a `launchd` job for the overnight worker, and wires telemetry hooks. Run `./bootstrap/bootstrap.sh --dry-run` first to see exactly what it would do.

**Turns cost usage.** Every working turn spawns a second, short session to produce its closing summary — free on a subscription, roughly double the notional list price if you ever move to metered billing.

## Troubleshooting

Start with `make doctor`. It answers most of this in three lines.

| Symptom | Cause | Fix |
|---|---|---|
| App loads, nothing responds | Backend is *absent*, not broken. `make dev` starts both under one trap that only fires when `make` exits, so a dead backend leaves Vite serving a UI pointed at a closed port. | `make backend` — restarts uvicorn alone and keeps the frontend's state |
| `make doctor` says `imports FAIL` | A real code error | `cd backend && .venv/bin/python -c "import main"` and read the traceback |
| `capabilities` shows a `GAP` | A mode's methodology references a tool this machine cannot reach | Install the plugin, or amend the methodology — do not leave it |
| A session asks permission for `vault_search` | The shared allowlist did not reach the spawn | Check `--settings` in the argv: `ps -axo args \| grep -- --settings` |
| Session says the vault is unreadable | It has the directory but not the path | The composed prompt states the absolute root; confirm `VAULT_PATH` is set for the *backend's* process |
| Sessions have no plugins or skills | Something still sets `CLAUDE_CONFIG_DIR` | `ps eww <pid> \| tr ' ' '\n' \| grep CLAUDE_CONFIG_DIR` — it should find nothing |
| `Not logged in` | Claude Code's credentials are Keychain-keyed to the config-dir path | `claude` once in a terminal to log in |
| Engine not found under `launchd` | `launchd` starts processes with a bare `PATH` containing no Homebrew | Set `NOCTIS_CLAUDE_BIN` to the absolute path |
| Typecheck passes but the build is broken | `tsc --noEmit -p tsconfig.json` checks **zero** files — it is a solution-style config with `"files": []` | Always `npm run typecheck` (which is `tsc -b`), never the `-p` form |
| A turn ends with no summary | The closing pass could not resume | Check the transcript for `turn ended mid-work`; a failed close is swallowed by design and leaves the original turn intact |

## Project layout

```
noctis-os/
├── backend/
│   ├── orchestrator/    Spawn, stream, parse, resume — driver, events, parser, manager, store
│   ├── mcp/             Noctis MCP server (stdio JSON-RPC, dependency-free)
│   ├── retrieval/       BM25 index over the vault, measured
│   ├── routers/         REST + SSE endpoints
│   ├── prompts/         Composes system.md + mode overlay + job context
│   ├── capabilities.py  What each mode needs vs. what the harness has
│   └── jobs.py          Mode → vault paths, job lookup
├── frontend/src/shell/  The v2 client — transcript, tabs, palette, panels
├── frontend/src-tauri/  Native shell
├── bootstrap/           One-time machine setup (--dry-run supported)
├── SPEC.md              Definition / PRD / Technical Design / Design Brief
├── STATUS.md            Live build state, non-aspirational
└── CHANGELOG.md         What changed when, and why
```

---

# Design notes

## Portability

"Workflow agnostic" here means something specific: **not that everything survives a move to another harness, but that a move states what it costs.**

- **Portable because it is text** — the methodology, mode overlays, agent definitions, the vault.
- **Portable because MCP is the standard** — retrieval *and* mode-loading travel over `tools/*` and `prompts/*`. Any MCP client gets them.
- **Not portable** — permissions, hooks, spawn flags, event-stream shape. Confined to three files under the `orchestrator/events.py` seam.

`python -m capabilities --migrate` emits a brief describing that third tier as *intent* rather than as settings, for an agent in another harness to act on. A multi-harness adapter is deliberately deferred: there is one harness, and an abstraction with a single implementation encodes guesses about the second rather than knowledge of it.

**On subscriptions.** Noctis is already bring-your-own-subscription — it drives the vendor's own CLI rather than calling an API with a key, so `Usage.list_cost_usd` is notional and `Limits` reports the 5-hour and 7-day windows rather than dollars. Extending the same mechanism to other providers is not blocked by licensing: each ships a CLI that authenticates against its own subscription. It is blocked by N× driver and parser, each drifting independently. Provider terms differ on scale, sharing and resale; personal single-seat use is the intended path.

## What changed

The architecture through mid-2026 differed from what is here now. If you are reading older commits or docs, this is the delta:

| Was | Is |
|---|---|
| Sessions launched into VS Code and Terminal.app, state read back from the vault | The app hosts sessions and streams them into its own transcript |
| Each mode had its own `CLAUDE_CONFIG_DIR` under `backend/launch_config/` | No redirect anywhere. Sessions use the real `~/.claude`, inheriting plugins, skills, subagents, MCP servers, permissions and memory |
| A mode's methodology was written into that dir's `CLAUDE.md` on every launch | Passed per launch via `--append-system-prompt`. Nothing per-mode on disk, so concurrent sessions cannot race |
| `~/.claude/CLAUDE.md` symlinked to `modes/dev/dev.md` | Symlinks to `prompts/system.md`. The config root is infrastructure, never an identity — the old symlink made the machine itself Faber and leaked the build process into every other mode |
| Per-mode tool cages (`--disallowedTools`) restricted research and maintenance | Every mode gets the same tools. `git push` stays denied for all of them |
| Permission prompts were emitted with nothing attached to answer them | Answered by the Noctis MCP server, surfaced as a dialog |
| The composer chip cycled the permission mode | It cycles effort, which `dev.md` had specified since it was written while no code passed `--effort` |
| The MCP server was built but never attached to a spawn | Attached to every spawn |
| A turn could end mid-work with nothing said | Every working turn is asked to close, and says so if it did not |
| Five characters, Custos and Echo among them | Settings and Nightshift collapsed into root-level `maintenance/` — infrastructure rather than a mode — and General was added |
| `make test` ran backend tests only | Runs backend, frontend typecheck and frontend tests |

Reasoning for each is in [`CHANGELOG.md`](CHANGELOG.md) and the commit messages.

## Tech stack

| Layer | Choice |
|---|---|
| Shell | Tauri 2, React 19, TypeScript, Vite, Tailwind CSS 4 |
| Backend | FastAPI, Python 3.11, `python-frontmatter` |
| Session runtime | [Claude Code](https://claude.com/claude-code) CLI, driven as a subprocess |
| Durable state | Flat markdown + YAML frontmatter (the vault) |
| History + search | SQLite FTS5 (BM25), no added dependencies |
| Scheduling | macOS `launchd` |
| Testing | `pytest` + `vitest` + `tsc -b`, all via `make test` |

## Status

**v1.5.2 is shipped and still the working system. v2 is mid-build.**

Stage 1 complete. Stage 2: items 1–5 and 7 done and verified live; item 6 done except its `launchd`-on-wake scheduler; item 8 needs a definition before it can be built; item 9 (maintenance migration) is unblocked and not started.

**The two versions coexist on purpose.** `frontend/src/shell/` is what runs; v1's `World.tsx`, `ProfileOverlay.tsx` and the VS Code / Terminal launch routes are still in the tree, unreferenced, and go at the Stage 2 cutover together with the state that still lives at their paths.

[`docs/noctis-documentation.md`](docs/noctis-documentation.md) is the short read. [`STATUS.md`](STATUS.md) is the detailed, non-aspirational build log.

**Deliberately out of scope:** multi-user support or auth beyond a single bearer token, any hosted deployment, idle character animation, and a full expression-swap library beyond the current busy/idle pair.

## License

[MIT](LICENSE) — see the license file for details.
