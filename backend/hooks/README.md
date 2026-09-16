# Session lifecycle hooks

Claude Code hooks are how Noctis learns what a session did, whoever hosts it. Two scripts, both non-blocking, both told the mode by `NOCTIS_MODE` (and the job by `NOCTIS_JOB_ID`).

| Hook | Event | Writes | Path |
|---|---|---|---|
| `log_action.py` | `PostToolUse` — once per tool call | one line, `<iso8601> <Tool> <target>`, and sets the mode's `busy` marker | `backend/runtime/<mode>__<job>.log` |
| `mark_session_end.py` | `SessionEnd` — once, when the CLI process exits | the `SESSION_END` sentinel; clears the `busy` marker | the same log, plus `busy_marker` |

**How they reach a session.** A hosted session gets them in its argv: `engine.py` names them in the settings block (`PostToolUse`, `SessionEnd`, with absolute interpreter and script paths, which is why they cannot be a committed settings file) and `interactive.py` composes that into `--settings`; `pty_spawn` applies `NOCTIS_MODE` and `NOCTIS_JOB_ID` to the child, because a PTY child would otherwise inherit whatever the shell process carried. A session Noctis did not launch — VS Code, a terminal — fires them only if the project's own `.claude/settings.local.json` registers them, with `--mode` and `--job-id` baked into the command; the environment wins when both are present. `make doctor` reports swallowed hook failures, because a hook that stops firing looks exactly like a session that used no tools.

**Runtime, not vault.** The logs are high-churn and ephemeral: gitignored `backend/runtime/`, never `second-brain/`.

## Why `SessionEnd` and not `Stop`

`Stop` fires after *every agent turn* — a response finishes and the CLI waits for the next prompt. Registering on it shipped briefly and was caught live when busy expressions flipped to idle mid-session. `SessionEnd` fires once, when the process exits. The `SESSION_END` sentinel is also the other half of `staleness.py`: a log that ends in it was closed on purpose and must never be flagged, however old it gets.

## What they are for

A hosted session's own telemetry — the 5h/7d windows, context, model, session id, transcript path — comes from its `statusLine` report (`backend/scripts/statusline.sh` → `POST /v2/sessions/statusline`), and its history from the transcript the CLI writes to disk. The hooks are what fires on every tool call regardless of who hosts the session. That is what keeps the runtime-log format a real interface rather than an implementation detail.

## Adding one

1. Write it here. Read the payload from stdin as JSON; never block, never raise — end in a swallow and let `failure_log` record the fault, which is where `make doctor` reads it.
2. Add it beside `PostToolUse` and `SessionEnd` in `engine.py`'s hook block, which `interactive.py` composes into `--settings`. A test asserts the scripts exist on disk.
3. Prove it fires against a real session without touching any config file — `--settings` accepts inline JSON:

```bash
claude -p "…" --settings '{"hooks":{"PostToolUse":[{"matcher":"","hooks":[{"type":"command","command":"…"}]}]}}'
```
