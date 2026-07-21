# SETUP.md

Manual, machine-level checklist only. Everything else is scripted by `make setup` (see `scripts/setup.sh`, `Makefile`).

## Noctis OS runtime

- **Claude Code login** — `claude` CLI installed and logged in (`claude auth login` or equivalent), since the session launcher shells out to it.
- **`VAULT_PATH`** — set in `.env` (copied from `.env.example` by `make setup`) to the absolute path of `second-brain/` on this machine.
- **VS Code global setting: `workbench.browser.openLocalhostLinks`** — one-time, set globally (not per-repo) so any localhost link, including ones Claude Code prints in chat, opens in VS Code's Integrated Browser instead of a system browser tab. Needed for Dev mode's launch surface.
- **Nightshift launchd job** — one-time, loads `launchd/com.noctis-os.nightshift.plist` (nightly 03:00 run of `scripts/nightshift_run.sh`, see `backend/nightshift/runner.py` for what it actually does):
  ```
  cp launchd/com.noctis-os.nightshift.plist ~/Library/LaunchAgents/
  launchctl load ~/Library/LaunchAgents/com.noctis-os.nightshift.plist
  ```
  Trigger a run manually to test without waiting for 03:00: `launchctl start com.noctis-os.nightshift`. Logs land in `backend/runtime/nightshift.log` (gitignored, same runtime-scratch area as the telemetry hooks). Unload with `launchctl unload ~/Library/LaunchAgents/com.noctis-os.nightshift.plist`. The plist hardcodes this machine's absolute repo path — update it (both the copy in `launchd/` and the one in `~/Library/LaunchAgents/`) if the repo ever moves.

## Desktop workflow

- **Obsidian** — installed, `second-brain/` opened as a vault.
- **istefox plugin** — installed and running in Obsidian. Required for the Claude Desktop / claude.ai workflow to read the vault (Desktop can't speak HTTP directly and bridges through `mcp-remote`). Not a dependency of the Noctis OS backend itself — the backend reads the vault directly off disk.

Nothing else. Repo scaffolding, dependency installs, and env file creation are all handled by `make setup`.
