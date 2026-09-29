"""Keep the backend up.

Something outside a process has to notice it died and start it again. That
is what `launchd` does for daemons and `systemd` does on Linux; this is the
same job, scoped to a single-user app that only wants a backend while it is
being used.

It lives here rather than inside a shell because it is not a property of any
shell. It was written into `desktop/app.py` first, which meant the supervision
only existed if you happened to launch through pywebview -- and pywebview is
v1's shell. A backend does not stop needing a supervisor because you opened a
different window.

Three properties, and the middle one is the one people skip:

  1. **Notice.** Poll `/health`, not the process table. A process can be alive
     and wedged, and "running" is not "working".
  2. **Back off, then keep trying slowly.** Restarting flat out forever turns
     one fault into a thrash that hides the cause, so the delays grow. But a
     supervisor that gives up turns a blip into an outage that lasts until a
     person notices: on 2026-09-16 a two-second probe timed out against a
     server that was answering every request, the supervisor killed it, four
     restarts in 48 seconds did not come up, and it exited -- Settings sat on
     "not responding" for an hour. Now the ladder ends in a steady retry
     every minute, forever, each one logged with its count, and a probe that
     fails is confirmed with a longer one before anything is killed. A
     permanent fault is still visible: it is the line that keeps repeating.
  3. **Reap before respawning.** The probe fires for a wedged process as well
     as a dead one, and spawning beside a wedged instance leaves it holding
     the port, so every replacement dies on "Address already in use".

Safe to kill at any point, because the state is not in here: the vault is
files and the history is SQLite. That is what makes a restart cost nothing.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8000"))
HEALTH = f"http://127.0.0.1:{PORT}/health"

POLL_S = 3.0
BACKOFF_S = (1, 2, 5, 10, 30)
STEADY_S = 60          # after the ladder: retry at this interval, forever
PROBE_S = 2.0          # the routine probe
CONFIRM_S = 10.0       # the second look before a failed probe counts
START_TIMEOUT_S = 30.0

_child: subprocess.Popen | None = None


def _log(msg: str) -> None:
    print(f"[supervise] {msg}", flush=True)


def healthy(timeout: float = 2.0) -> bool:
    """Answering, not merely running."""
    try:
        with urllib.request.urlopen(HEALTH, timeout=timeout):
            return True
    except Exception:                       # noqa: BLE001 - any failure is unhealthy
        return False


def uvicorn_command() -> list[str]:
    """The argv, separately so it can be asserted on without launching."""
    return [str(BACKEND_DIR / ".venv" / "bin" / "uvicorn"), "main:app",
            "--port", str(PORT)]


def spawn() -> subprocess.Popen:
    """Start uvicorn in its own process group.

    Its own group so a stop reaches the whole tree: uvicorn's reloader and
    workers are children, and signalling only the immediate process leaves
    them holding the port.

    No `--reload`. This supervisor and the reloader would fight -- a reload
    looks exactly like a death to a health probe, so the supervisor would reap
    the process the reloader had just started. `make browser` keeps the reloader
    and has no supervisor; they are alternatives, not layers.
    """
    return subprocess.Popen(
        uvicorn_command(), cwd=BACKEND_DIR, start_new_session=True,
    )


def reap() -> None:
    global _child
    if _child is None or _child.poll() is not None:
        _child = None
        return
    try:
        os.killpg(os.getpgid(_child.pid), signal.SIGTERM)
        _child.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(os.getpgid(_child.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    _child = None


def wait_until_healthy(deadline: float) -> bool:
    while time.time() < deadline:
        if healthy(timeout=1.0):
            return True
        time.sleep(0.3)
    return False


def answering() -> bool:
    """The routine probe, confirmed before it counts.

    A probe that times out is not a death: a server busy with a slow request
    answers late, not never. So a failed 2s probe is followed by one 10s look
    before the supervisor concludes anything -- the cost of being wrong the
    other way is killing a healthy server, which is what happened.
    """
    return healthy(timeout=PROBE_S) or healthy(timeout=CONFIRM_S)


def next_delay(failures: int) -> float:
    """Seconds to wait before restart number `failures + 1`: up the ladder,
    then the steady interval, forever."""
    return BACKOFF_S[failures] if failures < len(BACKOFF_S) else STEADY_S


def supervise(iterations: int | None = None) -> None:
    """The loop: probe, and restart when the backend stops answering.

    Never returns on its own. `iterations` bounds it for tests.
    """
    global _child
    failures = 0
    n = 0
    while iterations is None or n < iterations:
        n += 1
        time.sleep(POLL_S)
        if answering():
            if failures:
                _log(f"backend back after {failures} restart{'s' if failures != 1 else ''}")
            failures = 0
            continue
        delay = next_delay(failures)
        failures += 1
        if failures <= len(BACKOFF_S):
            _log(f"not answering; restart {failures} in {delay:g}s")
        else:
            _log(f"still not answering after {failures - 1} restarts; trying again in "
                 f"{delay:g}s -- run `make doctor`; if imports FAIL the fault is in the code")
        time.sleep(delay)
        reap()
        try:
            _child = spawn()
        except Exception as e:              # noqa: BLE001
            _log(f"restart failed: {type(e).__name__}: {e}")


def main() -> int:
    global _child

    def stop(*_: object) -> None:
        _log("stopping")
        reap()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    if healthy(timeout=1.0):
        _log(f"something is already answering on :{PORT}; supervising it is not "
             f"possible without owning it. Stop it first, or use `make browser`.")
        return 1

    _child = spawn()
    if not wait_until_healthy(time.time() + START_TIMEOUT_S):
        _log("backend never became ready")
        reap()
        return 1
    _log(f"backend up on :{PORT}")
    supervise()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
