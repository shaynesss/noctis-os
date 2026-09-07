# SETUP.md

Manual, machine-level checklist only. Everything else is scripted by `make setup` (see `scripts/setup.sh`, `Makefile`).

## Noctis OS runtime

- **Claude Code login** — `claude` CLI installed and logged in (`claude auth login` or equivalent), since the session launcher shells out to it.
- **`VAULT_PATH`** — set in `.env` (copied from `.env.example` by `make setup`) to the absolute path of `second-brain/` on this machine.
- **VS Code global setting: `workbench.browser.openLocalhostLinks`** — one-time, set globally (not per-repo) so any localhost link, including ones Claude Code prints in chat, opens in VS Code's Integrated Browser instead of a system browser tab. Needed for Dev mode's launch surface.
- **Nightshift launchd job** — one-time, renders and loads `launchd/com.noctis-os.nightshift.plist.template` (nightly 03:00 run of `scripts/nightshift_run.sh`, see `backend/nightshift/runner.py` for what it actually does):
  ```
  sed "s|__REPO_ROOT__|$PWD|g" launchd/com.noctis-os.nightshift.plist.template \
    > ~/Library/LaunchAgents/com.noctis-os.nightshift.plist
  launchctl load ~/Library/LaunchAgents/com.noctis-os.nightshift.plist
  ```
  Trigger a run manually to test without waiting for 03:00: `launchctl start com.noctis-os.nightshift`. Logs land in `backend/runtime/nightshift.log` (gitignored, same runtime-scratch area as the telemetry hooks). Unload with `launchctl unload ~/Library/LaunchAgents/com.noctis-os.nightshift.plist`. The rendered plist holds an absolute repo path — launchd expands neither `~` nor environment variables — so re-render it if the repo ever moves. The tracked file is a template with `__REPO_ROOT__` placeholders and is never loaded directly.

## Vault access

The backend reads and writes `second-brain/` directly off disk. **No Obsidian, no istefox, no MCP dependency.** Obsidian is an optional viewer — useful for browsing the vault by hand, required by nothing.

*(Removed 2026-09-07, Noctis v2 Stage 1 item 1. Obsidian's app-level config hung on 2026-08-29 for reasons unrelated to any vault file and cost most of an afternoon; it is demoted from prerequisite to convenience.)*

Nothing else. Repo scaffolding, dependency installs, and env file creation are all handled by `make setup`.

## Native desktop window (optional, replaces the browser-tab workflow)

`make app` opens Noctis OS as a frameless native window (pywebview, not Tauri — see `desktop/README.md` for why) instead of a browser tab or VS Code's Integrated Browser. `pywebview` is already in `backend/requirements.txt`, so `make setup` covers the dependency — nothing extra to install. Quit with Cmd+Q (no visible close button, by design). No custom app icon yet — that needs a bundler pass (`py2app`/`PyInstaller`), a deliberate follow-up, not done yet.
