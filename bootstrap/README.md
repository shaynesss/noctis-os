# bootstrap/

Makes a *machine* able to run Noctis. Not to be confused with `make setup`, which installs this *repo's* dependencies — the split is deliberate and the two are not interchangeable.

```bash
./bootstrap/bootstrap.sh --dry-run   # report only, change nothing
./bootstrap/bootstrap.sh             # do it
./bootstrap/bootstrap.sh --force     # also replace things that exist but differ
```

Idempotent. Re-running reports what is already correct and skips it. Nothing is silently overwritten: anything present-but-different is reported and left alone unless `--force` is passed.

## What it does

| # | Step | Notes |
|---|---|---|
| 1 | **Tooling** | Checks `python3`, `node`, `claude`, `git` (required); `cargo`, `jq` (optional). Also probes SQLite for **FTS5 + `bm25()`** — not optional, and a compile-time flag rather than something installable later; all retrieval depends on it. |
| 2 | **Vault** | Confirms `second-brain/` exists, is a git repo, and has a remote. A vault with no remote is the only copy on the machine — that was the live state on 2026-09-06. |
| 3 | **Symlink** | `~/.claude/CLAUDE.md` → `second-brain/prompts/system.md`, the *universal* prompt. This is what every Claude Code session on the machine reads; a mode's overlay travels in the argv at launch (`interactive.py`). Until 2026-09-11 the link pointed at `modes/dev/dev.md`, which made the machine itself Faber — and this script still said so until 2026-09-15, when a re-run would have undone the cutover. |
| 4 | **`.env`** | Generated from `.env.example` with a fresh 32-byte token and the resolved vault path, `chmod 600`. An existing `.env` is never touched — it holds a real secret. |
| 5 | **launchd** | Renders `launchd/com.noctis-os.nightshift.plist.template` (launchd expands neither `~` nor environment variables in its paths, which is why the tracked file is a template), validates it with `plutil`, and loads it: **nightshift runs nightly at 03:00** via `scripts/nightshift_run.sh`, logging to `backend/runtime/nightshift.log`. That script exports a PATH with Homebrew's bin on it — launchd's own has none, and from 2026-08-05 to 2026-09-15 every night failed to find `claude` and logged a quiet night. |

## What is no longer here

Per-mode `CLAUDE_CONFIG_DIR`s under `backend/launch_config/`, their one-time interactive logins, and the telemetry hooks wired into each — all of it went with the 2026-09-12 cutover. A session is the real `claude` in a PTY with its identity in the argv; it inherits the machine's own `~/.claude`, so there is nothing per mode to create, log into, or hook.

## What it deliberately leaves alone

An existing `.env`, an existing `~/.claude/CLAUDE.md` pointing somewhere else, an existing nightshift plist that differs. All reported, none clobbered without `--force`.
