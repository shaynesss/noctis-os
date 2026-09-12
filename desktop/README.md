# Desktop wrapper

One file, and it is not a shell: `NoctisOS.app` is a double-click wrapper
around `make dev`. The shell itself is Tauri, and it lives in
`frontend/src-tauri/`.

The bundle exists for one reason — a Dock and Finder icon, so starting Noctis
does not mean opening a terminal first. It is a thin wrapper, not a
`py2app`/`PyInstaller` freeze: it runs the live repo, so a code change needs
nothing more than the window's own reload, never a rebuild of this bundle.

```
make open-app     # or double-click desktop/NoctisOS.app
```

Output goes to `backend/runtime/desktop.log`, because a double-clicked app has
no terminal to print into. That log is the first place to look when the icon
bounces and no window appears.

The repo path is resolved from the script's own location rather than
hardcoded, so moving the checkout keeps it working — as long as the bundle
stays inside `desktop/` of that checkout.

## What used to be here

Until 2026-09-12 this directory held `app.py`, a pywebview window that was
v1's shell — chosen in July 2026 specifically to avoid adding a Rust
toolchain. Tauri replaced it: the Rust toolchain became worth paying for once
the shell needed a global hotkey, a tray, launch-at-login, and a packaging
story. `app.py` and its tests are deleted; `SPEC.md`'s "Desktop shell and
supervision" section is the current account.

Two things that pywebview shell taught, both of which survive in the current
code:

- **Cleanup needs process groups.** `npm run dev` spawns a *child* that runs
  the real Vite server, so `Popen.terminate()` on the immediate process left
  the real server and its bound port running invisibly. `backend/supervise.py`
  starts its child with `start_new_session=True` and signals the whole group.
- **Verify by actually closing the window.** That leak looked fine in review
  and only showed up under `lsof` after a real Cmd+Q.
