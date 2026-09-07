# Session lifecycle hooks

Claude Code hooks are how Noctis learns what a session did. They are registered per config dir in `settings.json` (written by `bootstrap/`, never tracked — the commands need absolute interpreter paths).

**Verified firing end to end on 2026-09-07** with the real hook commands: a `Read` produced an action line and a clean exit produced the sentinel, in the expected runtime file.

## The enumeration

| Hook | Event | Writes | Path |
|---|---|---|---|
| `log_action.py` | `PostToolUse` — once per tool call | One line: `<iso8601> <Tool> <target>` | `backend/runtime/<mode>__<job>.log` |
| `mark_session_end.py` | `SessionEnd` — once, when the CLI process exits | `SESSION_END` sentinel, and clears the mode's `busy` marker | same runtime log, plus `busy_marker` |

**Job identity** resolves from `NOCTIS_MODE` / `NOCTIS_JOB_ID` environment variables (Terminal.app launches inherit them) or from `--mode` / `--job-id` baked into the hook command at registration time (VS Code's URI handler carries no shell env, so Dev launches register a per-project hook with the args pre-filled).

**Runtime, not vault.** These logs are high-churn and ephemeral. They live in a gitignored `backend/runtime/` directory and never touch `second-brain/` — a locked v1 decision that v2 keeps.

## Why `SessionEnd` and not `Stop`

`Stop` fires after *every agent turn* — Claude finishes a response and waits for the next prompt. That is not session termination. Registering on `Stop` shipped briefly and was caught live when busy expressions flipped to idle mid-session, long before the terminal actually closed. `SessionEnd` fires exactly once, when the process exits.

The `SESSION_END` sentinel is also half of the staleness mechanism: a job whose log ends in it was closed *on purpose*, so `staleness.py` must never flag it however old it gets. Without the sentinel, every completed job would eventually look abandoned.

## What changes under v2 — and what doesn't

Hooks were originally scoped as **transitional scaffolding**, on the assumption that a custom agent loop would supersede them. There is no custom agent loop: Claude Code *is* the engine, so hooks are permanent architecture. But their role narrows, and the split is worth being explicit about:

| Session type | Telemetry source |
|---|---|
| Hosted by the orchestrator (general chat, Noctua, Vesper) | **The `stream-json` stream itself.** The orchestrator already parses every `ToolCall`, `ToolResult` and `TurnEnd`. Hooks would duplicate what it can see directly. |
| Launched externally (**Faber → VS Code**) | **Hooks, and only hooks.** Noctis does not own that process and never sees its stream. This is the case that keeps them essential. |

So hooks stop being the primary telemetry path and become the path for sessions Noctis doesn't host. That is a smaller job than they had in v1, but not a removable one — and it means the runtime-log format stays a real interface rather than an implementation detail the orchestrator could quietly change.

## Adding a hook

1. Write it in this directory; read the payload from stdin as JSON.
2. Register it for every mode in `bootstrap/bootstrap.sh`'s hook-wiring step — not by hand in a single `settings.json`, which drifts.
3. Re-run `./bootstrap/bootstrap.sh` (idempotent; it rewires all config dirs).
4. Verify it actually fires. `--settings` accepts inline JSON, so a hook can be exercised against a real session without touching any config dir:

```bash
claude -p "…" --settings '{"hooks":{"PostToolUse":[{"matcher":"","hooks":[{"type":"command","command":"…"}]}]}}'
```
