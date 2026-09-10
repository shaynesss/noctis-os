# Noctis — how it works

A desktop app that hosts Claude Code sessions and writes what they produce
into a knowledge vault.

This document is for someone reading the repo cold: what it is, what the
pieces are, and how they fit. `SPEC.md` and the vault's
`wiki/Noctis OS/noctis-v2-SPEC.md` carry the full design record and the
reasoning behind individual decisions; this is the shorter version you can
read in one sitting.

---

## The idea in one paragraph

Chat sessions with a model are disposable — you close the window and the
thinking evaporates. Noctis keeps two halves apart: a **body** that runs
sessions, and a **brain** that stores what they concluded. The body is a
desktop app driving the Claude Code CLI as a subprocess. The brain is a
markdown vault plus a small MCP server that makes it queryable. The body is
replaceable; the brain is meant to outlive it.

The practical consequence is that sessions run on an existing Claude
subscription rather than per-token API billing — the app drives the same CLI
you would run in a terminal, so there is no second bill.

---

## The shape

```
  ┌──────────────────────────────────────────────┐
  │  Tauri shell (React)                         │   the body
  │  chat · modes · search · stats · settings    │
  └───────────────────┬──────────────────────────┘
                      │  HTTP + SSE
  ┌───────────────────▼──────────────────────────┐
  │  FastAPI backend                             │
  │                                              │
  │  orchestrator/   spawns `claude -p`,         │
  │                  streams stream-json,        │
  │                  normalises it to events     │
  │                                              │
  │  store           SQLite + FTS5:              │
  │                  transcripts, usage, search  │
  └───────┬──────────────────────────┬───────────┘
          │                          │
   ┌──────▼───────┐          ┌───────▼──────────┐
   │ Claude Code  │          │  second-brain/   │   the brain
   │ (subprocess) │◄─────────┤  markdown vault  │
   └──────────────┘   MCP    └──────────────────┘
```

The arrow from the vault back to the subprocess is the MCP server: a session
can search the vault while it runs, so it starts with context instead of
being told everything again.

---

## The five modes

A mode is not a personality. It is a set of concrete differences applied when
a session spawns:

| Mode | For | Model | Tools |
|---|---|---|---|
| **General** | Questions, comparisons, anything unscoped | Opus 5 | read + web, never edits |
| **Faber** | Build: spec, implement, ship | Opus 5 | full surface |
| **Noctua** | Learn: read closely, explain, retain | Opus 5 | read + web, no shell |
| **Vesper** | Research: gather, weigh, return a verdict | Opus 5 | read + web, no shell |
| **Maintenance** | Audit the vault and propose repairs | Haiku 4.5 | read only, proposes only |

Each mode has its own `CLAUDE_CONFIG_DIR` holding a rendered system prompt
(a shared base plus a mode overlay), its own model, and its own tool policy
passed as `--allowedTools` / `--disallowedTools`.

**Tool policy is enforced at spawn, not by instruction.** A prompt asking a
session not to edit files is a request; a command-line flag is a fact.
Maintenance is the case that matters — it proposes changes to methodology
files and must never apply them, and a regression case caught that guardrail
failing when it was only written in prose.

---

## The session lifecycle

1. You type. The shell POSTs to `/v2/sessions`.
2. The orchestrator builds an argv and spawns
   `claude -p --output-format stream-json --verbose`.
3. The CLI streams newline-delimited JSON. `parser.py` turns it into a small
   event union — text, thinking, tool call, tool result, usage, limits,
   errors — and nothing above that layer sees the CLI's own shapes.
4. Events go two places at once: to the browser over SSE, and into SQLite.
5. The next message resumes the same engine session with `--resume`, so a
   conversation is continuous across separate processes.

Two sessions run concurrently at most. The cap is a budget on the rolling
usage window rather than a resource limit, and a third launch queues instead
of being refused.

**Transport is SSE over POST rather than EventSource**, because every route
requires a bearer token and `EventSource` cannot set headers — the
alternative would put the token in a query string, where it lands in logs.

---

## What the app can do

**Chat** — block-structured transcripts, not a character stream. Tool calls
collapse into one line per run (`Ran 3 shell commands · read 2 files`),
openable, with failures counted on the closed row. Turns end with a line
saying how long they took.

**Mode entry and handoff** — `⌘T` opens a session in any mode and directory.
`⌘⇧H` hands the conversation to a different mode, which **spawns a new
session** rather than switching the current one: a mode is a config dir, a
model and a tool policy, and a running process can change none of them. The
source conversation stays open, and the new one begins with a provenance
block naming where it came from and the summary it was given.

**History** — every conversation and turn is in SQLite. Closing the window
loses nothing; the shell reopens the last General conversation on launch and
shows a one-line recap of where it left off.

**Search** (`⌘K`) — one query across conversations (FTS5) and the vault
(BM25). Two lists, not one ranking: the scores come from different corpora
and merging them would produce an order that looks meaningful and is not.

**Promotion** (`/promote`) — writes a conversation into the vault as a
curated note. Nothing is automatic: the store is a cache of what was said,
the vault is what was decided, and only a person can tell those apart.

**Stats** — token counts by category, a contribution grid, and the rolling
5-hour and 7-day usage windows with reset countdowns. Those windows are the
only numbers that govern a decision, so they are never estimated — when the
engine has not reported them, the UI shows a dash rather than a zero.

**Also**: pasted images (sent inline, not written to disk), artifacts (files
a conversation changed), desktop notifications when a turn finishes while
the window is hidden, slash commands, per-session model override, a vault
document reader, and an editor for the prompts themselves that re-renders
the config dirs on save.

---

## The MCP server

`mcp/server.py` is the portable half. It speaks JSON-RPC over stdio and
exposes five tools:

| Tool | Answers |
|---|---|
| `vault_search` | What does the vault say about X? |
| `history_search` | What did I say about X? |
| `job_context` | What is the state of this piece of work? |
| `worklist` | What is outstanding? |
| `propose` | Stage a change for review — never applies it |

Plus MCP *prompts* (mode entry points) and *resources* (vault documents), so
a client that has never heard of Noctis can discover the whole surface.

It implements the protocol's core method set — `initialize`, `tools/list`,
`tools/call`, `prompts/list`, `prompts/get`, `resources/list`,
`resources/read` — as JSON-RPC 2.0 over stdio, negotiating a protocol
version at handshake and staying silent on notifications, which have no id
to answer.

It needs no package manager — `python3 server.py` and nothing to install.
It is not a single file, though: it imports `retrieval/` and `orchestrator/`
alongside it, so adopting it means copying three directories. A conformance
test drives it from a JSON-RPC client that imports nothing from this
codebase, which is what substantiates the claim that any MCP client can use
it.

Retrieval is BM25 over heading-level chunks, with title and heading columns
weighted above body text, returning the top 20. Measured at **80% recall**
on a 40-case evaluation set spanning six query categories.

---

## The vault

```
second-brain/
  wiki/            durable reasoning — the part that compounds
  modes/<name>/    methodology, lessons, state, jobs/<slug>/context.md
  prompts/         system prompt + per-mode overlays + regression cases
  eval/            the retrieval evaluation set
  brief/           generated daily (not built yet)
```

The split that matters is **state versus knowledge**: durable reasoning goes
in `wiki/`, volatile state stays in each mode's own files. It is what keeps
the vault readable as it grows.

Markdown files, no database, no lock-in. Any editor opens it; Obsidian is
convenient but nothing depends on it.

---

## Stack

- **Frontend** — React + Vite in a Tauri v2 shell (~5,800 lines). Global
  Opt+Space summon, tray icon, launch at login, and closing hides rather
  than quits, so the window is always one keystroke away.
- **Backend** — FastAPI, no ORM and no migrations (~3,600 lines across the
  orchestrator, routers, MCP server and retrieval index). SQLite holds
  transcripts and usage; the vault holds knowledge.
- **Auth** — bearer token plus Origin checking on every route. Binding to
  localhost alone is not sufficient against the DNS-rebinding class of
  attack, and the packaged app is a different origin from the dev server, so
  both are on the allowlist.
- **Tests** — 343 backend, 57 frontend.

---

## What is not built

- The **morning brief** and its scheduler — the design is settled apart from
  whether it reads email, which is an open decision.
- **Running the regression suite from the UI** — the cases are listed with
  what a run would cost; firing them needs the orchestrator to host and
  report thirteen sessions.
- The **v1 surface** still ships alongside v2, unreferenced, pending a
  cutover.

---

## Reading further

- `SPEC.md` — this project's own constraints and build order.
- `second-brain/wiki/Noctis OS/noctis-v2-SPEC.md` — the full design record:
  definition, product requirements, technical design, design brief, risks.
- `STATUS.md` — what actually works today, and what is outstanding.
- `CHANGELOG.md` — what changed and when, including the bugs worth
  remembering.
