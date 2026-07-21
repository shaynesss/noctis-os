# Desktop wrapper

Native window via [pywebview](https://pywebview.flowrl.com/), not Tauri —
`SPEC.md`'s original "Tauri desktop wrap" out-of-scope line covered the
general idea; superseded 2026-07-21 in favor of this lighter approach.
Chosen specifically to avoid adding a Rust toolchain to a single-user local
tool with no distribution need — pywebview stays 100% Python, reusing the
backend's own venv.

## Running it

```
make app
```

Starts the same two dev servers `make dev` does (backend `uvicorn --reload`,
frontend Vite), waits for both to answer, then opens a frameless native
window pointed at the frontend. Both backend and frontend hot-reload
live — same as a browser tab, this is a native window, not a snapshot.
Quit with **Cmd+Q** (there's no visible close button by design — frameless
means no OS chrome at all, matching "fully my interface").

## Frameless, and why cleanup needed real fixing

The window has zero OS chrome (`frameless=True`) — genuinely just the app's
own UI, no titlebar, no traffic-light buttons. Verified live, not assumed:
first pass used a plain `try/finally` around `webview.start()` plus
`Popen.terminate()`, which looked fine until actually closing the window
and checking `lsof` — `npm run dev` spawns a *child* process that runs the
real Vite server, and `terminate()` only signals the immediate child, so
the real server (and its bound port) kept running invisibly after the
window closed. Fixed by starting each process in its own group
(`start_new_session=True`) and killing the whole group on cleanup
(`os.killpg`), registered three ways (`window.events.closed`, `atexit`,
`SIGTERM`) for defense in depth. Verified again with a real simulated
Cmd+Q keystroke (not just `.terminate()` from the launching script) — zero
leftover processes, zero leftover bound ports.

## Custom icon — placeholder now, real art and a bundle later

pywebview's `icon` parameter (on both `create_window` and `start`) is
documented GTK/QT-only — doesn't do anything on macOS. Worked around by
setting the Dock icon directly via AppKit (`NSApplication.setApplicationIconImage_`,
called once the GUI loop is live via `webview.start(func=_set_dock_icon)`)
using Faber's sprite as a placeholder — real per Shayne's request ("can be
random for now, actual art down the line"), not final branding. Ran clean
with no exception using the standard documented API; couldn't get a clean
screenshot confirming it in this environment (auto-hiding Dock, synthetic
mouse events didn't reliably trigger the reveal), so this one's worth a
glance at the real Dock next run.

Still not done: a proper double-click-able `.app` bundle with a bundled
`.icns` (`py2app` or `PyInstaller`). Right now `make app` runs from source
(shows up as "python" in the menu bar), correct for daily personal use but
not yet something you'd hand to someone else or launch without the
terminal.
