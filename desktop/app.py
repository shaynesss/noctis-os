"""Native desktop wrapper -- pywebview (not Tauri; SPEC.md's "Tauri desktop
wrap" out-of-scope line covered the general idea, superseded 2026-07-21 by
this lighter pywebview-based approach, chosen specifically to avoid adding
a Rust toolchain to a single-user local tool with no distribution need).

Manages the same two dev-server processes `make dev` starts (backend
uvicorn, frontend Vite), then opens a frameless native window pointed at
the frontend -- same hot-reload dev workflow as a browser tab, just without
browser chrome. Sets a placeholder Dock icon at runtime via AppKit (Faber's
sprite, standing in for real app art). A proper double-click-able .app
bundle with a bundled .icns (py2app or PyInstaller) is still a deliberate
follow-up, not done here -- this covers window/process lifecycle plus a
real-but-placeholder icon for `make app`'s from-source workflow.
"""

import atexit
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import webview

REPO_ROOT = Path(__file__).parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
BACKEND_URL = "http://localhost:8000/health"
FRONTEND_URL = "http://localhost:5173/"
# Faber, standing in for real app art -- a placeholder, not a final icon
# (Shayne's call: something real now, actual art later). Both create_window
# and start()'s own `icon` params are documented GTK/QT-only, so on macOS
# this needs to go through AppKit directly instead -- see _set_dock_icon.
ICON_PATH = REPO_ROOT / "assets" / "characters" / "faber.png"

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


def _start(cmd: list[str], cwd: Path) -> subprocess.Popen:
    # start_new_session=True (setsid) puts each process in its own group --
    # `npm run dev` doesn't run the Vite server itself, it spawns a *child*
    # process that does, and Popen.terminate() only signals the immediate
    # child. Without this, closing the window left the real Vite process
    # (and its bound port) running invisibly in the background forever --
    # found by actually closing the window and checking `lsof`, not assumed.
    proc = subprocess.Popen(cmd, cwd=cwd, start_new_session=True)
    _procs.append(proc)
    return proc


def _cleanup() -> None:
    global _cleaned_up
    if _cleaned_up:
        return
    _cleaned_up = True
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


def main() -> None:
    # Registered three ways on purpose: webview's own closed event (the
    # normal path -- Cmd+Q/Cmd+W on a real Cocoa window), atexit (covers
    # webview.start() returning through any other path), and SIGTERM (covers
    # the process being killed directly). Verified live that a plain
    # try/finally around webview.start() was NOT enough on its own.
    atexit.register(_cleanup)
    signal.signal(signal.SIGTERM, lambda *_: (_cleanup(), sys.exit(0)))

    _start(
        [str(BACKEND_DIR / ".venv" / "bin" / "uvicorn"), "main:app", "--reload", "--port", "8000"],
        BACKEND_DIR,
    )
    _start(["npm", "run", "dev"], FRONTEND_DIR)

    if not _wait_for(BACKEND_URL):
        print("desktop/app.py: backend never became ready, exiting", file=sys.stderr)
        _cleanup()
        return
    if not _wait_for(FRONTEND_URL):
        print("desktop/app.py: frontend never became ready, exiting", file=sys.stderr)
        _cleanup()
        return

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
    webview.start(func=_set_dock_icon)
    _cleanup()


if __name__ == "__main__":
    main()
