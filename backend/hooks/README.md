# Session lifecycle hooks

Claude Code hooks are how Noctis learns what a session did, and the one place it can refuse something, whoever hosts it. Three scripts. Two are telemetry, non-blocking, told the mode by `NOCTIS_MODE` (and the job by `NOCTIS_JOB_ID`); the third is a guard and is the only one that can stop a tool call.

| Hook | Event | Does | Path |
|---|---|---|---|
| `log_action.py` | `PostToolUse` — once per tool call | one line, `<iso8601> <Tool> <target>`, and sets the mode's `busy` marker | `backend/runtime/<mode>__<job>.log` |
| `mark_session_end.py` | `SessionEnd` — once, when the CLI process exits | the `SESSION_END` sentinel; clears the `busy` marker | the same log, plus `busy_marker` |
| `guard_shared_tree.py` | `PreToolUse`, matcher `Bash` | refuses whole-tree git commands while another live session is in the same repository | blocks with exit 2; writes nothing |

**How they reach a session, and it is two different routes.** The two telemetry hooks are registered per project, in `.claude/settings.local.json`, with `--mode` and `--job-id` baked into the command; the environment wins over those baked args when both are present, and `pty_spawn` applies `NOCTIS_MODE`/`NOCTIS_JOB_ID` to the child because a PTY child would otherwise inherit whatever the shell process carried. The guard is registered in the **argv** instead, by `interactive.py`'s `statusline_settings`, so it reaches every hosted session in every project, including one with no Noctis files in it at all. Absolute interpreter and script paths in both cases, which is why neither can be a committed settings file.

> Until 2026-09-17 this section said `engine.py` named the telemetry hooks and `interactive.py` composed them into `--settings`. That described the deleted `-p` orchestrator: `engine.py`'s `settings_config()` still builds such a block, and no interactive session has ever read it.

`make doctor` reports swallowed hook failures, because a hook that stops firing looks exactly like a session that used no tools.

## The guard, and why it is a hook

Sessions run in parallel on one repository by design ("two sessions on one job split the work by file"). On 2026-09-17 two Faber sessions worked on `noctis-os` at once and, twice, one ran `git add -A` and committed the other's uncommitted edits under its own message. Nothing was lost; two commit bodies in the Repo tab describe work they do not contain, which matters because that log is the memory.

**The session that loses its work is not the session running the command**, so a rule in a prompt cannot help: it binds the reader, not the actor. A hook binds whoever runs the command. That asymmetry is the entire argument for putting it here rather than in a methodology file.

It refuses only commands that act on the whole working tree (`add -A|--all|-u|.`, `commit -a`, `stash` with no pathspec, `reset --hard`, `checkout/restore .`, `clean -f`), and only while another live session reports the same **repository**, resolved through `git rev-parse --show-toplevel`, not the raw cwd, since `backend/` and `frontend/` are one tree. Alone, everything is allowed. With company, `git add <paths>` is still allowed, which is what splitting by file means in practice.

It **fails open** at every step: no backend, no token, a slow reply, an unparseable payload, a directory in no repository, all allow. The condition is usually false, and a session broken by a down backend is a worse outcome than a collision that can be undone.

Liveness comes from `GET /v2/sessions`, whose `live` array is every terminal whose status line reported in the last thirty seconds.

**Runtime, not vault.** The logs are high-churn and ephemeral: gitignored `backend/runtime/`, never `second-brain/`.

## Why `SessionEnd` and not `Stop`

`Stop` fires after *every agent turn* — a response finishes and the CLI waits for the next prompt. Registering on it shipped briefly and was caught live when busy expressions flipped to idle mid-session. `SessionEnd` fires once, when the process exits. The `SESSION_END` sentinel is also the other half of `staleness.py`: a log that ends in it was closed on purpose and must never be flagged, however old it gets.

## What they are for

A hosted session's own telemetry — the 5h/7d windows, context, model, session id, transcript path — comes from its `statusLine` report (`backend/scripts/statusline.sh` → `POST /v2/sessions/statusline`), and its history from the transcript the CLI writes to disk. The hooks are what fires on every tool call regardless of who hosts the session. That is what keeps the runtime-log format a real interface rather than an implementation detail.

## Adding one

1. Write it here. Read the payload from stdin as JSON; never block, never raise — end in a swallow and let `failure_log` record the fault, which is where `make doctor` reads it.
2. Register it. Telemetry that only needs to fire in a real project goes in that project's `.claude/settings.local.json`; anything that must hold everywhere goes in `interactive.py`'s `statusline_settings`, which every hosted session gets in its argv. A test asserts the script exists on disk, because a registered path that does not resolve fails silently.
3. Prove it fires against a real session without touching any config file — `--settings` accepts inline JSON:

```bash
claude -p "…" --settings '{"hooks":{"PostToolUse":[{"matcher":"","hooks":[{"type":"command","command":"…"}]}]}}'
```
