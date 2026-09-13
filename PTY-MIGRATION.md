# Running the real CLI: a PTY instead of `stream-json`

> **Status: steps 1–3 shipped 2026-09-13. Steps 4–5 deliberately not started.**
> The Terminal runs beside the `stream-json` transcript; nothing was deleted,
> and switching the default is gated on the two agreeing over real use.
> `DOCUMENTATION.md` §24 is the reference for what exists; this file is the
> reasoning and the sequence. `SPEC.md` Open questions 7 is the decision record.
>
> **Every assumption this rests on has now been tested against the installed
> CLI (2.1.263) rather than argued.** §3 is the evidence. §8 is what remains
> unproven, and it is wiring rather than architecture.

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

**Transcripts survive every failure shape.** The named blocker, run against
three real sessions:

| shape | result |
|---|---|
| short session, one turn, clean exit | transcript written, usage records, CLI's own `aiTitle` |
| **SIGKILL mid-generation** | partial output `'1\n2\n3…27'` already on disk, plus usage and title |
| resumed with `--resume` | appends to the same file — 2 user turns, 4 usage records, no fork |

The middle row is the one that matters: the transcript is written
**incrementally, not flushed at exit**, so a crash keeps its history. That is
the property the whole "history is read, not recorded" premise needs.

*(A fourth check reported a spurious fork. It was the test, not the CLI —
the mtime filter caught the transcript of the session running the test.)*

**`portable-pty` builds and runs.** Not just "the crate exists" — a Rust
binary on this project's toolchain (cargo 1.98.1, edition 2021, same
`rust-version = "1.77.2"` as the Tauri crate):

```
1. TUI painted: 2839 bytes, esc=144
2. injected /status: 1601 bytes back, recognised ["Version","Model","Session"]
3. resize: redrew 1763 bytes
4. exited: ExitStatus { signal: Some("Killed: 9") }     orphans: none
```

`portable-pty 0.9` pulls **20 transitive dependencies** and the
size-optimised release binary is **773 KB** including the Rust runtime — well
inside the "don't ship 40MB to host a webview" line in `Cargo.toml`'s release
profile.

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

### Lifetime tokens: one raw number

**Decided 2026-09-13. Stats shows a single lifetime token count. No split, no
tiers, no footnote.** It is a fun stat, and it should read like one.

What the jargon meant, once, so it can stop appearing: alongside your
conversation the CLI makes its own small background calls on a cheaper model —
naming a session, checking quota. Today's parser separates those into
`aux_input_tokens`/`aux_output_tokens`. The JSONL does not record them, so
sourcing lifetime tokens from disk drops them.

Measured, that is nothing:

```
lifetime conversation   82,174,586
background calls           146,327
                             0.178%
```

An earlier draft of this document made that the deciding question, quoting
`141,195` as though a large-looking absolute meant something without dividing
it by anything. A fifth of one percent does not change a fun stat.
`CLAUDE_CODE_ENABLE_TELEMETRY` would recover it exactly and costs an OTel
collector in a single-user local app — not a trade worth making.

**So: `aux_input_tokens` and `aux_output_tokens` are deleted with the
migration**, the Stats page shows one number sourced from the JSONL, and the
word "aux" leaves the codebase.

*Method note, because the trap is reusable: the obvious per-session
reconciliation is confounded. A session Noctis streamed that later continued
in VS Code shows a JSONL total 3× the store's, because the store only ever saw
the turns it hosted — which looks like the JSONL over-counting when it is
really the store under-covering.*

### Transcript coverage — was the real risk, now cleared

History moves from something Noctis *records* to something it *reads*, which
only holds if the file is always there. Tested against three real sessions on
2026-09-13, and all three pass — see §3. The one that mattered was a session
SIGKILLed mid-generation: its partial output was already on disk, so
transcripts are written incrementally rather than flushed at exit.

23 of 73 stored sessions lack a JSONL, which looks alarming and is not: all 50
missing are `-p` spawns, the mode being left behind.

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

---

## 8. What the terminal looks like, and what is still unproven

### It has no taste of its own

xterm.js is a renderer, not a designer — it ships no look you have to accept.
Two layers, both yours.

**The box it lives in is an ordinary DOM element.** Tailwind, `tokens.css`,
cards, borders, radius, padding, a header strip above it, the composer below
— all of it is the same React and the same design system as every other panel.
Nothing about embedding a terminal makes that part different.

**The character grid is themed through an object**, and the surface is
complete. `ITheme` takes `foreground`, `background`, `cursor`, `cursorAccent`,
all 16 ANSI colours plus their bright variants, `extendedAnsi` for 16–255,
three selection colours, three scrollbar colours and `overviewRulerBorder`.
`ITerminalOptions` takes `fontFamily`, `fontSize`, `fontWeight`,
`fontWeightBold`, `letterSpacing`, `lineHeight`, `cursorStyle`
(block/underline/bar), `cursorInactiveStyle`, `cursorWidth`, `cursorBlink`,
`scrollback`, `smoothScrollDuration`, `minimumContrastRatio`,
`allowTransparency`, `drawBoldTextInBrightColors` and `customGlyphs`.

So the theme is generated from `tokens.css` rather than written twice —
ground `#0f0f0f`, ink `#cccccc`, dim `#8a8a8a`, line `#2a2a2a`, Cascadia Code
at the shell's own size and leading, one source of truth. It will not look
like Terminal.app.

**What stays the CLI's** is which slot it prints in and where it draws its own
boxes. You decide what `yellow` *is*; Claude Code decides that this line is
yellow. That is inherent to running the real thing, and it is the point.

Two things this gains over today. The palette is per-instance, so **a tab's
terminal can carry its mode's accent** — Faber red, Noctua amber, Vesper
purple — which is more control over the CLI's appearance than VS Code offers.
And `customGlyphs` means box-drawing characters are drawn rather than taken
from the font, so the CLI's rules and frames stay sharp at any size.

### The renderer question, answered

xterm.js offers three renderers: DOM, canvas, and **WebGL2**
(`@xterm/addon-webgl`, currently 0.19.0). The worry was that the famous
xterm.js hosts — VS Code, Cursor, Hyper — are all Electron, i.e. Chromium,
while Tauri gives you **WKWebView** on macOS. Different engine, unproven path.

It is not unproven. [Termic](https://termic.dev/docs/terminal/) runs xterm.js
with the WebGL addon inside a Tauri/Rust app with the PTY on the Rust side —
the exact architecture proposed here — and DomTerm supports Tauri/Wry
front-ends. Termic's own notes say the WebGL path was the only renderer
without visible row gaps in full-screen TUI apps, and that it holds frame
rates under heavy output.

One concrete finding worth carrying into the design: **WKWebView rasterises
glyphs slightly lighter than Terminal.app**, and a font-weight bump closes the
gap. `fontWeight` is an option, and Cascadia Code is vendored as a variable
font covering 200–700, so the correction costs nothing.

### Still unproven — wiring, not architecture

Two left, and both are measurements rather than unknowns:

1. **Byte throughput over Tauri IPC.** Every chunk the PTY produces has to
   cross from Rust into the web view, and that crossing is a serialised
   message rather than a shared buffer. A session printing fast — a build log,
   a long file — produces hundreds of small reads per second, and emitting one
   IPC event per read is the naive version that stalls. The fix is ordinary:
   coalesce reads on the Rust side into a ~16ms window and send one frame per
   tick. What needs measuring is the window size, not whether it works.
   *Found on first use, 2026-09-13: the batch must also flush on silence. A
   flush that only runs when the next read arrives strands the tail of a
   prompt that then blocks for input — the trust dialog rendered to
   mid-sentence. Fixed with a batcher thread on `recv_timeout`, since a thread
   parked in `read()` cannot notice that nothing is arriving.*
2. **Keystroke routing.** `⌘K`, `⌘T` and `⇧⇥` belong to the shell today, but
   inside a focused terminal almost everything must reach the CLI instead.
   VS Code's answer — a small reserved set, everything else passes through —
   is the starting point, and the reserved set is a design decision to make
   deliberately rather than discover.

Neither can invalidate the architecture. They are step-1 cost.
