"""Directories the backend writes to while running.

This exists because of a bug that has now happened twice.

`uvicorn --reload` watches the working directory, so anything the backend
writes during normal operation restarts it — dropping whatever request was
in flight. In WKWebView that surfaces as "cannot reach backend: Load failed",
which looks like a network problem and is not.

2026-07-27: the telemetry hooks wrote to `runtime/` on every tool call.
Fixed with `--reload-exclude 'runtime/*'`, plus a test asserting that flag.

2026-09-09: the conversation store began writing `data/history.db` on every
message, and WAL mode made it churn harder still. The test did not catch it,
because it asserted the literal string `runtime/*` rather than the property
that mattered — that *every* directory the backend writes to is excluded.

So the list lives here, the test is driven by it, and adding a new
runtime-written directory without excluding it fails loudly.
"""

RUNTIME_WRITE_DIRS = (
    "runtime",        # hook-written action logs and busy markers
    "data",           # conversation store: history.db and its WAL/shm sidecars
    "launch_config",  # each mode's rendered CLAUDE.md, rewritten on launch
)

RELOAD_EXCLUDES = tuple(f"{d}/*" for d in RUNTIME_WRITE_DIRS)
