# Changelog

## Unreleased

- Telemetry hooks: PostToolUse hook (`backend/hooks/log_action.py`) appends one action line per tool call to `backend/runtime/<mode>__<job>.log`; `PATCH /mode/{name}/jobs/{slug}` rewrites job-context frontmatter at stage transitions and syncs `state.md`; `GET /mode/{name}/jobs/{slug}/log` is the interface's poll target; ProfileOverlay's Faber job rows show a live last-action line (2026-07-21)
- Spec drafted: Definition, PRD, EDD locked (2026-07-19)
