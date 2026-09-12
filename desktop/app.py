"""Native desktop wrapper -- pywebview (not Tauri; SPEC.md's "Tauri desktop
wrap" out-of-scope line covered the general idea, superseded 2026-07-21 by
this lighter pywebview-based approach, chosen specifically to avoid adding
a Rust toolchain to a single-user local tool with no distribution need).

Manages the same two dev-server processes `make dev` starts (backend
uvicorn, frontend Vite), then opens a frameless native window pointed at
the frontend -- same hot-reload dev workflow as a browser tab, just without
browser chrome. Sets a placeholder Dock icon at runtime via AppKit (Faber's
sprite, standing in for real app art) -- kept even now that desktop/NoctisOS.app
carries a real bundled .icns (from the same sprite), since this script also
runs bare via `make app`, without the bundle, during from-source dev work.

desktop/NoctisOS.app is a thin wrapper around this script, not a py2app/
PyInstaller freeze -- its launcher just execs this file from the live repo,
so double-clicking it in Finder/Dock always runs current source, never a
stale snapshot. A Refresh command (Cmd+R, or the "Noctis OS" menu this
module registers) reloads the window in place -- the intended way to pick
up a code change without quitting and relaunching the whole app.
"""

import atexit
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import webview
from webview.menu import Menu, MenuAction

REPO_ROOT = Path(__file__).parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
BACKEND_URL = "http://localhost:8000/health"
FRONTEND_URL = "http://localhost:5180/"  # pinned in frontend/vite.config.ts (strictPort) -- 5173 is Vite's default and collides with other projects' dev servers on this machine
# Faber-building (the tree expression), matching desktop/NoctisOS.app's
# bundled AppIcon.icns -- Shayne's pick over the plain idle sprite. Both
# create_window and start()'s own `icon` params are documented GTK/QT-only,
# so on macOS this needs to go through AppKit directly instead -- see
# _set_dock_icon.
ICON_PATH = REPO_ROOT / "assets" / "characters" / "expressions" / "faber-building.png"


def _resolve_npm() -> str:
    """Bare "npm" resolves via PATH -- fine for `make app`/`make dev` from
    a terminal (full shell PATH, Homebrew's bin dir included), but
    desktop/NoctisOS.app is launched through LaunchServices (double-click,
    Spotlight), which hands the process a minimal launchd PATH that does
    NOT include Homebrew. Same root cause class as launch_surfaces.py's
    PYTHON_BIN fix -- a bare command name silently resolving differently
    depending on how the process was launched. Found live: two failed
    Spotlight launches both logged `FileNotFoundError: 'npm'` in
    backend/runtime/desktop.log, while a terminal-launched `make app`
    worked fine right before that.
    """
    found = shutil.which("npm")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/npm", "/usr/local/bin/npm"):
        if Path(candidate).exists():
            return candidate
    return "npm"  # last resort -- fails the same way as before if truly absent


NPM_BIN = _resolve_npm()


def _npm_env() -> dict[str, str]:
    """Resolving NPM_BIN's own absolute path isn't enough on its own: npm's
    shebang is `#!/usr/bin/env node`, so *running* it does its own PATH
    lookup for `node` in the child's environment -- under the same
    impoverished LaunchServices PATH that made bare "npm" fail to resolve
    in the first place, that lookup fails too. Prepend NPM_BIN's own
    directory (where `node` lives alongside it in a Homebrew/nvm install)
    to a copy of the current environment's PATH.
    """
    env = os.environ.copy()
    npm_dir = str(Path(NPM_BIN).parent)
    env["PATH"] = f"{npm_dir}{os.pathsep}{env.get('PATH', '')}"
    return env


_procs: list[subprocess.Popen] = []
_cleaned_up = False


def _wait_for(url: str, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.3)
    return False


def _start(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen:
    # start_new_session=True (setsid) puts each process in its own group --
    # `npm run dev` doesn't run the Vite server itself, it spawns a *child*
    # process that does, and Popen.terminate() only signals the immediate
    # child. Without this, closing the window left the real Vite process
    # (and its bound port) running invisibly in the background forever --
    # found by actually closing the window and checking `lsof`, not assumed.
    proc = subprocess.Popen(cmd, cwd=cwd, start_new_session=True, env=env)
    _procs.append(proc)
    return proc


# ---------------------------------------------------------------- watchdog
#
# How anything stays up: something outside the process is responsible for
# noticing it died and starting it again. `launchd` does this for system
# daemons (KeepAlive), systemd does it on Linux (Restart=always), a container
# runtime does it for pods. Noctis had none of it -- `_start` spawned uvicorn
# and never looked at it again, so a backend that died stayed dead and the
# window just stopped answering.
#
# Three things a supervisor needs, and the second is the one people skip:
#
#   1. Notice. Poll the child, and poll a health endpoint -- a process can be
#      alive and wedged, and "running" is not "working".
#   2. Back off. Restarting instantly forever turns one fault into a storm
#      that hides the cause. Delay grows, and after enough failures it stops
#      and says so rather than thrashing quietly.
#   3. Be safe to kill. The state has to live outside the process, so a
#      restart costs nothing -- which is already true here: the vault is
#      files and the history is SQLite.

WATCHDOG_POLL_S = 3.0
WATCHDOG_BACKOFF_S = (1, 2, 5, 10, 30)      # then give up and report
_watchdog_stop = threading.Event()


def _is_backend(proc: subprocess.Popen) -> bool:
    """The uvicorn child, told apart from the frontend one by its argv."""
    return any("uvicorn" in str(a) for a in (proc.args or []))


def _healthy(port: int = 8000, timeout: float = 2.0) -> bool:
    """Answering, not merely running. A wedged process passes `poll()`."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout):
            return True
    except Exception:                       # noqa: BLE001 - any failure is unhealthy
        return False


def _supervise(spawn, *, port: int = 8000) -> None:
    """Restart the backend when it stops answering, with backoff.

    `spawn` returns a fresh Popen. Kept as a callable rather than a command
    list so the caller owns how the backend is started and this owns only
    when.
    """
    failures = 0
    while not _watchdog_stop.wait(WATCHDOG_POLL_S):
        if _healthy(port):
            failures = 0
            continue
        if failures >= len(WATCHDOG_BACKOFF_S):
            print("[watchdog] backend will not stay up; giving up. "
                  "Run `make doctor` — if imports FAIL the fault is in the code, "
                  "not the supervisor.", flush=True)
            return
        delay = WATCHDOG_BACKOFF_S[failures]
        failures += 1
        print(f"[watchdog] backend not answering; restart {failures} in {delay}s",
              flush=True)
        if _watchdog_stop.wait(delay):
            return

        # Reap before respawning. The probe is a *health* check, so it fires
        # for a process that is alive and wedged as well as for one that is
        # gone -- and spawning beside a wedged instance leaves it holding the
        # port, so the replacement dies on "Address already in use" and the
        # supervisor exhausts its attempts without ever having had a chance.
        # Found by killing a real process under the watchdog and watching
        # four restarts fail to bind.
        for proc in list(_procs):
            if proc.poll() is None and _is_backend(proc):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    proc.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass
            if proc.poll() is not None:
                try:
                    _procs.remove(proc)
                except ValueError:
                    pass
        try:
            spawn()
        except Exception as e:              # noqa: BLE001
            print(f"[watchdog] restart failed: {type(e).__name__}: {e}", flush=True)


def _cleanup() -> None:
    global _cleaned_up
    if _cleaned_up:
        return
    _cleaned_up = True
    # Before killing anything, or the watchdog sees its own teardown as a
    # crash and races to restart what is being shut down.
    _watchdog_stop.set()
    for proc in _procs:
        if proc.poll() is not None:
            continue
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            continue
    for proc in _procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass


def _set_dock_icon() -> None:
    """pywebview's own `icon` params (create_window and start) are both
    GTK/QT-only per their docstrings -- macOS needs AppKit directly.
    Runs via webview.start(func=...), which fires once the GUI loop is
    live, since NSApplication doesn't exist yet at import time.
    """
    if not ICON_PATH.exists():
        return
    try:
        import AppKit

        image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(ICON_PATH))
        if image:
            AppKit.NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception as exc:
        print(f"desktop/app.py: couldn't set dock icon: {exc}", file=sys.stderr)


def _refresh() -> None:
    """The frontend's own Cmd+R listener (App.tsx) is the reliable path --
    this menu item exists so Refresh shows up as a real, discoverable native
    command (App menu, macOS convention) rather than a shortcut you have to
    already know. evaluate_js over load_url: reloads in place, no flash of
    the window's background_color while the page re-fetches.
    """
    for window in webview.windows:
        window.evaluate_js('window.location.reload()')


def main() -> None:
    # Registered three ways on purpose: webview's own closed event (the
    # normal path -- Cmd+Q/Cmd+W on a real Cocoa window), atexit (covers
    # webview.start() returning through any other path), and SIGTERM (covers
    # the process being killed directly). Verified live that a plain
    # try/finally around webview.start() was NOT enough on its own.
    atexit.register(_cleanup)
    signal.signal(signal.SIGTERM, lambda *_: (_cleanup(), sys.exit(0)))

    # **No --reload.** This is the daily driver, not a dev loop, and the
    # difference matters more here than in most apps: Noctis's own primary
    # job is editing this repository. A Faber session that touches any
    # backend/*.py would restart the very backend hosting it, killing its own
    # in-flight stream and every other live session's along with it. The bug
    # would look like the model going silent mid-turn, which is the failure
    # this codebase has spent two days learning to tell apart from a crash.
    #
    # `make dev` keeps --reload, because that is the loop where a backend
    # edit *should* take effect immediately and no session is being hosted.
    # Here, a backend change needs the app restarted -- the same contract any
    # application has. (The frontend is unaffected: it is served live and the
    # app's own Refresh command reloads it.)
    #
    # Kept for the record, since it is why the excludes below existed: the
    # hooks write into backend/runtime/ on every tool call of every live
    # session, and with --reload on, ordinary hook activity was restarting
    # the backend mid-request and dropping in-flight fetches. WKWebView
    # surfaces that as "Load failed", which is why a browser-tab repro missed
    # it. With reload off the whole class is gone rather than excluded.
    def _spawn_backend() -> subprocess.Popen:
        return _start(
            [
                str(BACKEND_DIR / ".venv" / "bin" / "uvicorn"),
                "main:app",
                "--port",
                "8000",
            ],
            BACKEND_DIR,
        )

    _spawn_backend()
    _start([NPM_BIN, "run", "dev"], FRONTEND_DIR, env=_npm_env())

    if not _wait_for(BACKEND_URL):
        print("desktop/app.py: backend never became ready, exiting", file=sys.stderr)
        _cleanup()
        return
    if not _wait_for(FRONTEND_URL):
        print("desktop/app.py: frontend never became ready, exiting", file=sys.stderr)
        _cleanup()
        return

    # Only once both are up, so a slow first start is not mistaken for a
    # crash and restarted underneath itself. Daemon, so it never holds the
    # process open on quit.
    threading.Thread(target=_supervise, args=(_spawn_backend,), daemon=True,
                     name="backend-watchdog").start()

    window = webview.create_window(
        "Noctis OS",
        FRONTEND_URL,
        frameless=True,
        easy_drag=True,
        width=1440,
        height=900,
        min_size=(800, 600),
        background_color="#100b24",
    )
    window.events.closed += _cleanup
    app_menu = [Menu("Noctis OS", [MenuAction("Refresh", _refresh)])]
    webview.start(func=_set_dock_icon, menu=app_menu)
    _cleanup()


if __name__ == "__main__":
    main()
