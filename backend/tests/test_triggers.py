import os
import time
from datetime import timedelta

import triggers
import vault_io


def _seed_cursor(cursor: dict):
    vault_io.write_frontmatter(
        "modes/settings/state.md",
        {"mode": "settings", "busy": False, "lessons_distilled_through": cursor},
        "",
    )


def test_no_triggers_when_nothing_changed(vault):
    _seed_cursor({m: 1 for m in triggers.MODES})
    for m in triggers.MODES:
        vault_io.write_file(f"modes/{m}/lessons.md", "# header\n")

    result = triggers.compute_triggers()

    assert result == {"friction": False, "accumulation": False, "suspicion": False}


def test_accumulation_fires_when_lessons_grow_past_cursor(vault):
    _seed_cursor({m: 1 for m in triggers.MODES})
    for m in triggers.MODES:
        vault_io.write_file(f"modes/{m}/lessons.md", "# header\n")
    vault_io.write_file("modes/dev/lessons.md", "# header\n- 2026-07-21 [x]: a real lesson.\n")

    result = triggers.compute_triggers()

    assert result["accumulation"] is True
    assert result["friction"] is False


def test_friction_fires_on_marker_in_new_text(vault):
    _seed_cursor({m: 1 for m in triggers.MODES})
    for m in triggers.MODES:
        vault_io.write_file(f"modes/{m}/lessons.md", "# header\n")
    vault_io.write_file(
        "modes/dev/lessons.md", "# header\n- 2026-07-21 [x]: FRICTION: the gate order forced a redo.\n"
    )

    result = triggers.compute_triggers()

    assert result["friction"] is True
    assert result["accumulation"] is True


def test_friction_marker_before_cursor_does_not_count(vault):
    # The FRICTION-tagged line is already "seen" (before the cursor) --
    # only text added since the last distillation pass should count.
    for m in triggers.MODES:
        vault_io.write_file(
            f"modes/{m}/lessons.md", "# header\n- 2026-07-21 [x]: FRICTION: old, already distilled.\n"
        )
    _seed_cursor({m: 2 for m in triggers.MODES})

    result = triggers.compute_triggers()

    assert result["friction"] is False
    assert result["accumulation"] is False


def test_suspicion_fires_for_stale_state_file(vault, monkeypatch):
    _seed_cursor({m: 1 for m in triggers.MODES})
    for m in triggers.MODES:
        vault_io.write_file(f"modes/{m}/lessons.md", "# header\n")

    stale_time = time.time() - timedelta(days=8).total_seconds()
    os.utime(vault / "modes" / "learn" / "state.md", (stale_time, stale_time))

    result = triggers.compute_triggers()

    assert result["suspicion"] is True


def test_no_suspicion_for_recently_touched_state_files(vault):
    _seed_cursor({m: 1 for m in triggers.MODES})
    for m in triggers.MODES:
        vault_io.write_file(f"modes/{m}/lessons.md", "# header\n")

    result = triggers.compute_triggers()

    assert result["suspicion"] is False
