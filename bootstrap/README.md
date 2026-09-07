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
| 1 | **Tooling** | Checks `python3`, `node`, `claude`, `git` (required); `cargo`, `jq`, `pyinstaller` (optional, needed at Stage 2). Also probes SQLite for **FTS5 + `bm25()`** — not optional, and a compile-time flag rather than something installable later, so it is checked here rather than discovered at build time. |
| 2 | **Vault** | Confirms it exists, is a git repo, and has a remote. A vault with no remote is the only copy on the machine — that was the live state on 2026-09-06. |
| 3 | **Symlink** | `~/.claude/CLAUDE.md` → `second-brain/modes/dev/dev.md`. This one line is what makes every Claude Code session in every project read the methodology. Nothing else wires it up. |
| 4 | **`.env`** | Generated from `.env.example` with a fresh 32-byte token and the resolved vault path, `chmod 600`. An existing `.env` is never touched — it holds a real secret. |
| 5 | **launchd** | Renders `launchd/*.plist.template`, validates with `plutil`, loads it. launchd expands neither `~` nor environment variables in its paths, which is exactly why the tracked file is a template. |
| 6 | **Mode config dirs** | One `CLAUDE_CONFIG_DIR` per mode under `backend/launch_config/`. |
| 7 | **Telemetry hooks** | Wires `PostToolUse` and `SessionEnd` into each config dir with absolute interpreter paths — which is why generated `settings.json` is machine state and never tracked. |

## The one thing it cannot do for you

**Each config dir needs its own interactive `claude` login, once.**

Claude Code stores credentials as a macOS Keychain entry **keyed to the config-dir path** (`Claude Code-credentials-<hash>`). Verified 2026-09-07: a freshly created dir *and* a byte-for-byte copy of an already-working one both report `Not logged in`, while the original path authenticates fine. There is no file to copy and no environment variable to set.

The script detects which dirs are unauthenticated and prints the exact command per dir. Expect to do this once, ever.

**Why separate dirs at all**, given the orchestrator rewrites each dir's `CLAUDE.md` on every launch: two concurrent sessions in different modes would otherwise race on the same file, and the concurrency cap is 2. Sharing one dir would make the cap unsafe rather than merely wasteful.

## What it deliberately leaves alone

- `backend/launch_config/nondev/` — v1's config dir, still live until the Stage 2 cutover.
- An existing `.env`, an existing `~/.claude/CLAUDE.md` pointing somewhere else, an existing `settings.json` with different hooks. All reported, none clobbered without `--force`.
