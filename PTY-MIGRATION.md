# Running the real CLI: a PTY instead of `stream-json`

> **Status: proposed, undecided.** Written 2026-09-13 for review. Nothing here
> is built. `SPEC.md`'s Open questions item 7 is the decision; this is the
> impact review behind it. If the answer is no, this file gets deleted and
> item 7 records why.

---

## 1. What is actually being proposed

Noctis spawns `claude -p`. The CLI's own help calls that *"print response and
exit"*, and says interactive is the default. So today's architecture is: run
the **scripting** mode once per turn, parse its JSON, and rebuild the
interactive experience — the turn loop, the closing pass, the permission
prompt, the transcript — on top of it.

The proposal is to run the CLI the way a terminal does: in a pseudo-terminal,
interactive, rendering itself, with Noctis's interface wrapped around it.

**This is not "embed a terminal app".** The terminal is one component inside
the existing layout. Every panel, the rail, the vault, the design system stay
exactly as they are.

---

## 2. Why this never surfaced before, and why it does now

It surfaced twice and was rejected both times, correctly.

| where | what it said |
|---|---|
| `Modes.md`, 2026-07-19 | live display "resolved honestly with a tiered mechanism that avoids **the original trap (PTY capture)**" — hooks for v1, "full terminal mirroring **if ever wanted**" for v2 |
| v2 spec deferrals | "Career mode, **PTY mirroring**, idle roaming … stay dropped" |
| v2 spec §Ghostty | "**Not** the reference for turn *structure*: Ghostty is an xterm-style character stream, while `stream-json` hands us discrete events, so the transcript is block-shaped underneath" |

Every one of those is right **under the premise in force at the time**:
*fire-and-forget*. The interface launched sessions into Terminal.app and VS
Code and read their state back from hook-written files — it never owned a
session. Under that design a PTY means **mirroring**: scraping and echoing a
terminal belonging to someone else. That genuinely is a trap.

**v2 deleted that premise.** `CLAUDE.md`, current: *"v2 hosts sessions; it does
not launch them elsewhere."* Once Noctis owns the process, a PTY is not
mirroring — it is the ordinary way to run an interactive program.

The decision was never re-derived when its foundation was removed. It carried
forward as inherited scope. That is precisely the failure mode `dev.md`'s
completeness check exists to catch, and worth recording as a lesson
independent of whether this migration happens.

The third row above is the subtlest and the most instructive: *"the transcript
is block-shaped underneath"* is offered as a fact about Noctis, but it is a
consequence of choosing `stream-json`, which was itself downstream of
fire-and-forget. A reason two steps removed from a premise that no longer
holds still reads like a reason.

---

## 3. What was tested, not argued

All four on 2026-09-13, against the installed CLI (2.1.263).

**Chrome can drive the terminal.** A PTY spawned `claude`; `/status` was
written into it from outside, exactly as a Noctis button would:

```
1. TUI painted        3253 bytes, alive
2. injected /status   1601 bytes back — Status, Model, Account, Version
3. resize mid-session redrew 1970 bytes, alive
4. clean exit         exit=-9, orphans=none
```

So mode chips, effort cycling and `/model` survive as writes into the PTY.
*Implementation note that would otherwise cost hours: the window size must be
set on the PTY **before** spawning. At 0×0 the TUI exits instantly with no
error, which reads exactly like "PTY doesn't work here".*

**`statusLine` delivers the status bar.** With an inline `--settings` (no
global config touched), the command received:

```json
{"rate_limits": {"five_hour":  {"used_percentage": 3, "resets_at": 1789338000},
                 "seven_day":  {"used_percentage": 9, "resets_at": 1789383600}},
 "context_window": {"used_percentage": 20, "context_window_size": 1000000},
 "effort": {"level": "medium"}, "model": {"id": "claude-opus-5"},
 "cost": {"total_cost_usd": 0.0327822, "total_api_duration_ms": 2987},
 "session_id": "...", "transcript_path": "/Users/.../<session_id>.jsonl"}
```

`rate_limits` appears only after the first API response, as its schema states.
`transcript_path` is the direct link to §4 below.

**The CLI writes its own transcripts.** `~/.claude/projects/**/*.jsonl`, 128
of them present. One 369-record file yielded: `sessionId` matching the
filename, per-record `cwd`, first/last timestamps, an `aiTitle` the CLI
generated itself, 64 tool calls with results, 34 thinking blocks, and 105
`usage` records with input / cache-read / cache-creation / output / thinking
tokens.

**The subscription premise is unchanged.** `/status` from the interactive
session: `Login method: Claude Pro account`.

---

## 4. Capability audit

Every capability in `DOCUMENTATION.md` and the interface spec.

### Untouched — never spoke to the engine

Brief · Stats page shell · Inbox · Settings · Design Lodge · worklist ·
vault document reader · **vault search / BM25 / FTS5 retrieval** · the Noctis
MCP server (`tools/*`, `prompts/*`) · maintenance · the scheduler · capability
contract · every design token, colour and shortcut.

Measured rather than assumed: of four routers, `health.py` imports nothing
from the orchestrator, `search.py` imports only `ConversationStore`, and
`panels.py` imports `ConversationStore` plus four driver *constants*
(`EFFORT_CYCLE`, `MODEL_CATALOG`, `MODE_MODELS`, `MODE_TOOLS`) which are plain
config. **`sessions_v2.py` is the only file with a real dependency** — driver,
events, manager, store and wire.

### Same data, new source — SQLite tables stay, the filler changes

| capability | today | under a PTY |
|---|---|---|
| history, transcripts | stream events → `store.record` | JSONL indexer → same tables |
| `⌘K` search over conversations | FTS5 on `messages` | unchanged; indexer fills `messages` |
| recap | Noctis generates, caches | unchanged |
| session titles | Noctis derives from the prompt | **CLI's `aiTitle`** — one less engine call |
| lifetime tokens, Stats | `usage` table from `result` events | `usage` table from JSONL records |
| `state` (running/done/…) | inferred from the event stream | **process liveness and exit code** — more direct |
| `mode` (faber/noctua/…) | on the spawn | Noctis's own `session_id → mode` map; the JSONL's `mode` is the CLI's permission mode |
| status bar: ctx %, 5h, 7d, model, effort | `rate_limit_event` in the stream | `statusLine` POST |
| live/max sessions | manager's semaphore | count of open PTYs |
| cwd, git branch | `/v2/git` + spawn arg | `statusLine` + per-record `cwd` |

### Genuinely changes

**The transcript rendering.** Today it is block-shaped — tool disclosures
matched by id, thinking as a token count, `error`/`silent`/`handoff` block
kinds. Under a PTY the live conversation is the CLI drawing itself. A
block view can still be built from the JSONL for *history*, but the live pane
looks like Claude Code, because it is. **This is the stated goal, not a
casualty** — but it is the single biggest visible change and the thing to be
sure about.

**The permission prompt.** The CLI renders its own in the terminal. Noctis's
clickable dialog, `permissions.py`'s 180-second timeout and the pending-poll
all go. Given the goal is VS Code's shape, this is arguably correct rather
than lost.

**Turn-integrity states (§7).** `silent` / `unclosed` / `truncated` /
`blocked` are computed from `TurnEnd`. The interactive CLI closes its own
turns, so the *condition* largely stops arising — but the explicit `silent`
block kind and the closing pass would go with it. Removal of a workaround,
not of a feature.

### The background tier — measured, and not decision-relevant

**Resolved 2026-09-13. Decision: lifetime tokens come from the JSONL, the
`aux_*` columns go, and Stats shows one honest total with no split.**

`modelUsage` is absent from the JSONL, so the CLI's own background calls —
titles, quota checks — would not be counted. The first draft of this document
called that "the one measurable regression" and put the whole decision on it,
quoting `aux_input_tokens = 141,195` as if the absolute number meant something.
Measured against the total it does not:

```
lifetime primary   82,174,586
lifetime aux          146,327
aux as % of total       0.178%      (1,230 tokens/turn over 119 turns)
```

**A fifth of one percent.** `CLAUDE_CODE_ENABLE_TELEMETRY` with
`claude_code.token.usage` would recover it exactly and costs an OTel collector
in a single-user local app — not a trade worth making for 0.178%. Nor is a
caveat in the UI: an asterisk on a number this accurate makes it read as less
trustworthy than it is.

What the JSONL measures is *conversation* tokens, which is what the Stats page
is asked about. One number, no split, no footnote.

*Method note, because it is the reason the first draft was wrong: a large
absolute figure was compared against nothing. The per-session reconciliation
that would have caught it earlier is also confounded — a session Noctis
streamed and that later continued in VS Code shows a JSONL total 3× the
store's, because the store only ever saw the turns it hosted.*

### The real risk, and the spike must settle it

**Not every session writes a transcript.** Of 73 sessions in the store with an
engine id, **23 have a JSONL on disk**. The missing 50 are `-p` spawns, which
is the mode being left behind, and interactive sessions demonstrably do write
them — 128 files, the current one at 14MB. But history would move from
something Noctis records itself to something it *reads*, and that only works if
the file is always there.

The spike must confirm: does every PTY session write a transcript, including a
very short one, one killed mid-turn, and one resumed? If the answer is no,
history needs a fallback and this gets much less attractive.

---

## 5. What it costs to build

Replaced: `orchestrator/driver.py`, `manager.py`, `parser.py`, `wire.py`,
`permissions.py`, and the streaming half of `routers/sessions_v2.py`.
`store.py` stops recording and starts indexing. `frontend/src/shell/engine.ts`
loses `runSession`/`readSSE`/`fold`; `App.tsx`'s turn loop goes.

Added: a Rust PTY host (`portable-pty` — Tauri has no `node-pty`), xterm.js
themed from `tokens.css`, byte piping over Tauri IPC, resize handling,
keystroke routing between terminal and app, a `statusLine` receiver endpoint,
and a JSONL indexer with a file watcher.

Honestly: the largest change since the v1 cutover. The spike is a day. The
migration is weeks of evenings, and it must be sequenced so Noctis keeps
working throughout — the terminal alongside the existing transcript, behind a
setting, until it is clearly better. A hard cutover here would repeat the
2026-09-12 mistake of deleting the old path while something still depended on
it.

---

## 6. What this buys

Not just parity. These stop existing:

- the closing pass and `CLOSING_PROMPT` — the CLI closes its own turns
- respawning per turn, and its ~1.9s cost
- the permission host and its timeout
- `TurnEnd` bookkeeping, and today's "no result reported" fix
- the dropped-SSE-stream class of bug entirely — there is no HTTP stream

Every one of those was a real bug fixed on 2026-09-11/12/13. They are the
running cost of using a scripting mode as an app backend.

And two things get *better*: session state becomes process liveness rather
than inference, and titles come free.

---

## 7. Recommendation

With the token question settled at 0.178%, nothing measured so far argues
against this. The open risk is transcript coverage (§4), and it is a spike
question rather than a design question.

Sequence, and never a cutover:

1. **PTY host behind a setting**, alongside the existing transcript. Both paths
   work; you switch per tab.
2. **`statusLine` receiver** — one endpoint, and the status bar stops depending
   on the stream even before the migration lands.
3. **JSONL indexer** writing the same SQLite tables, so search, Stats and
   history keep their queries. Run it beside the current recorder and diff the
   two for a week.
4. **Switch the default** once the diff is boring.
5. **Delete the orchestrator** only when nothing reads it — the 2026-09-12
   cutover removed `launch_config/` while a guard still required it and broke
   every spawn, which is the mistake this ordering exists to avoid.

Steps 2 and 3 are worth doing **regardless of the decision**: the status bar
should survive a reload today, and an indexer that agrees with the recorder is
the cheapest possible proof that step 4 is safe.
