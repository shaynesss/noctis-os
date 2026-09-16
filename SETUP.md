# SETUP.md

The one-time, machine-level checklist. Two scripts do almost all of it; this file is what they cannot do for you, and where to look when something is off.

## The two scripts

| | Does | Re-run |
|---|---|---|
| `make setup` (`scripts/setup.sh`) | this checkout's dependencies: the backend venv, `npm install`, and `.env` from `.env.example` if absent | after a dependency change |
| `make bootstrap` (`bootstrap/bootstrap.sh`) | the machine: checks the tooling (`python3`, `node`, `claude`, `git` required; `cargo`, `jq` optional; SQLite with FTS5 and `bm25()`), confirms the vault is a git repository with a remote, symlinks `~/.claude/CLAUDE.md` → `second-brain/prompts/system.md`, writes `.env` with a generated token and the resolved vault path, and renders and loads the nightshift `launchd` plist | any time — idempotent, reports and skips what is already right, never overwrites without `--force` |

`./bootstrap/bootstrap.sh --dry-run` prints what it would do and changes nothing. Step by step in [`bootstrap/README.md`](bootstrap/README.md).

## By hand

- **Claude Code, logged in.** `claude` on `PATH` and authenticated once in a terminal — credentials are Keychain entries, and sessions, nightshift and the regression suite all shell out to it.
- **`VITE_API_TOKEN`** in `.env`, the same value as `NOCTIS_API_TOKEN`. Bootstrap generates the latter and leaves the frontend's copy to you: Vite inlines it into the bundle, which `.env.example` explains is acceptable here and nowhere else.
- **Rust**, for the window. `make dev` is the Tauri shell and needs `cargo`; bootstrap says so if it is missing, and the Makefile adds `~/.cargo/bin` to `PATH` so a non-login shell finds it. Without it, `make browser` runs the same backend and frontend in a browser tab.
- **A vault remote.** Bootstrap warns rather than creates one; the `gh repo create` line it prints is the one-liner.

## Nightshift under launchd

Bootstrap's step 5 renders `launchd/com.noctis-os.nightshift.plist.template` — launchd expands neither `~` nor variables in its paths, so the tracked file is a template with `__REPO_ROOT__` placeholders and is never loaded directly — into `~/Library/LaunchAgents/` and loads it. Nightly at 03:00 it runs `scripts/nightshift_run.sh` → `backend/nightshift/runner.py`. The script exports a `PATH` with Homebrew's bin on it, because launchd's own has none and from 2026-08-05 to 09-15 every night failed to find `claude`. Every run is recorded in `backend/data/nightshift.json`, and Settings → Maintenance says how the last one ended.

- Run it now rather than at 03:00: `launchctl start com.noctis-os.nightshift`
- Log: `backend/runtime/nightshift.log` (gitignored, like every runtime file)
- Unload: `launchctl unload ~/Library/LaunchAgents/com.noctis-os.nightshift.plist`
- The rendered plist holds an absolute repo path: re-run `make bootstrap` if the checkout moves.

## Running it

`make dev` opens the native window — Opt+Space summon, tray, launch-at-login; closing hides it, the tray and the hotkey are the ways back — with the backend under `backend/supervise.py`, which restarts it if it stops answering. `make browser` is the fallback for backend-only work: a browser tab at `:5180` and `uvicorn --reload` in place of the window and the supervisor. `make open-app` is the double-clickable wrapper around `make dev`. `make doctor` says what is up. The two paths side by side: `DOCUMENTATION.md` §14.

Nothing else. The backend reads and writes `second-brain/` off disk — no Obsidian (an optional viewer, demoted from prerequisite on 2026-09-07), no MCP dependency of its own.
