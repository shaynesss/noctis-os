# Changelog

## Unreleased

- Nightshift infra: `backend/nightshift/{slack_surface,runner}.py` implement Scan (deterministic per-mode slack checks: dev's `flagged` jobs, settings' undistilled-lessons cursor) and Advance/Stage (dev is templated, settings borrows the distiller subagent via a real tool-scoped headless `claude -p` call); `scripts/nightshift_run.sh` + `launchd/com.noctis-os.nightshift.plist` wire it to a nightly launchd run. Closes out the locked Phase 3 build order (2026-07-21)
- Telemetry hooks: PostToolUse hook (`backend/hooks/log_action.py`) appends one action line per tool call to `backend/runtime/<mode>__<job>.log`; `PATCH /mode/{name}/jobs/{slug}` rewrites job-context frontmatter at stage transitions and syncs `state.md`; `GET /mode/{name}/jobs/{slug}/log` is the interface's poll target; ProfileOverlay's Faber job rows show a live last-action line (2026-07-21)
- Spec drafted: Definition, PRD, EDD locked (2026-07-19)
