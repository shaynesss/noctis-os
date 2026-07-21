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

Starts the same two dev servers `make dev` does (backend uvicorn, frontend
Vite), waits for both to answer, then opens a frameless native window
pointed at the frontend. Hot reload works exactly like a browser tab, since
it's the same Vite dev server underneath — this is a native window, not a
snapshot. Quit with **Cmd+Q** (there's no visible close button by design —
frameless means no OS chrome at all, matching "fully my interface").

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

## Custom icon — not done yet, needs a bundler

pywebview's `icon` parameter only works on Linux/GTK. On macOS, a Dock icon
comes from packaging into a real `.app` bundle with an `.icns` file, via
`py2app` or `PyInstaller` — that's the next step, not done in this pass.
Right now `make app` runs from source (shows up as "python" in the menu
bar), which is correct for daily personal use but not yet a
double-click-able bundled app.
