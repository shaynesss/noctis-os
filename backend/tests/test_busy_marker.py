import os
import time
from datetime import timedelta

import busy_marker


def test_fresh_marker_is_busy(tmp_path, monkeypatch):
    monkeypatch.setattr(busy_marker, "RUNTIME_DIR", tmp_path)
    busy_marker.set_busy("dev")

    assert busy_marker.is_busy("dev") is True


def test_stale_marker_self_heals_to_idle(tmp_path, monkeypatch):
    """A marker orphaned by a non-graceful exit (terminal killed, machine
    slept, crash) never gets a matching SessionEnd -- see busy_marker.py's
    module docstring. is_busy() must reconcile against STALE_THRESHOLD
    rather than trusting the marker's existence forever."""
    monkeypatch.setattr(busy_marker, "RUNTIME_DIR", tmp_path)
    busy_marker.set_busy("dev")
    marker = busy_marker._marker_path("dev")
    stale_time = time.time() - (busy_marker.STALE_THRESHOLD + timedelta(hours=1)).total_seconds()
    os.utime(marker, (stale_time, stale_time))

    assert busy_marker.is_busy("dev") is False
    assert not marker.exists()  # self-heals: also clears the orphaned marker
