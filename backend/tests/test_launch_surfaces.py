import json
import threading
from pathlib import Path

import launch_surfaces

HOOK_SCRIPT = Path("/fake/hook.py")


def test_merge_hook_creates_settings_file(tmp_path):
    settings_path = tmp_path / "settings.json"
    launch_surfaces._merge_hook(settings_path, "PostToolUse", "python3 /fake/hook.py", HOOK_SCRIPT)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "python3 /fake/hook.py"


def test_merge_hook_preserves_existing_keys(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"theme": "auto"}), encoding="utf-8")

    launch_surfaces._merge_hook(settings_path, "PostToolUse", "python3 /fake/hook.py", HOOK_SCRIPT)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["theme"] == "auto"
    assert settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "python3 /fake/hook.py"


def test_merge_hook_is_idempotent(tmp_path):
    settings_path = tmp_path / "settings.json"
    launch_surfaces._merge_hook(settings_path, "PostToolUse", "python3 /fake/hook.py", HOOK_SCRIPT)
    launch_surfaces._merge_hook(settings_path, "PostToolUse", "python3 /fake/hook.py", HOOK_SCRIPT)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert len(settings["hooks"]["PostToolUse"]) == 1


def test_merge_hook_replaces_stale_entry_for_same_script(tmp_path):
    """A new job in the same project must replace the old job's hook, not
    accumulate alongside it -- otherwise the old job's hook keeps firing on
    every future session in that project (2026-07-21 ship-gate finding)."""
    settings_path = tmp_path / "settings.json"
    # _merge_hook's replace-by-script-identity match is keyed on
    # PYTHON_BIN + script_path, not a literal "python3" prefix (launch
    # commands invoke the venv's own interpreter, not whatever's on PATH
    # in the launched shell -- see launch_surfaces.PYTHON_BIN).
    prefix = f"{launch_surfaces.PYTHON_BIN} {HOOK_SCRIPT}"
    old_command = f"{prefix} --mode dev --job-id old-job"
    new_command = f"{prefix} --mode dev --job-id new-job"

    launch_surfaces._merge_hook(settings_path, "PostToolUse", old_command, HOOK_SCRIPT)
    launch_surfaces._merge_hook(settings_path, "PostToolUse", new_command, HOOK_SCRIPT)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    commands = [h["command"] for e in settings["hooks"]["PostToolUse"] for h in e["hooks"]]
    assert commands == [new_command]


def test_merge_hook_leaves_other_scripts_alone(tmp_path):
    settings_path = tmp_path / "settings.json"
    other_script = Path("/fake/other.py")
    launch_surfaces._merge_hook(settings_path, "PostToolUse", "python3 /fake/other.py", other_script)
    launch_surfaces._merge_hook(settings_path, "PostToolUse", "python3 /fake/hook.py --job-id x", HOOK_SCRIPT)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    commands = [h["command"] for e in settings["hooks"]["PostToolUse"] for h in e["hooks"]]
    assert "python3 /fake/other.py" in commands
    assert "python3 /fake/hook.py --job-id x" in commands


def test_merge_hook_purges_stale_registration_under_a_different_event(tmp_path):
    """A script re-registered under a new event (e.g. mark_session_end.py
    moving from Stop to SessionEnd, since Stop turned out to fire after
    every agent turn rather than on real session termination) must not
    keep firing under its old event too -- otherwise a settings.json from
    before the fix double-fires on both forever.

    The stale entry uses a bare "python3" prefix on purpose, not
    PYTHON_BIN -- that's what a *real* pre-existing settings.json actually
    has (registered before PYTHON_BIN existed at all). A first version of
    this test used PYTHON_BIN for the stale command too, which made the
    purge's real bug invisible: it matched on a prefix built from
    PYTHON_BIN, so it could never have matched a genuinely old bare-python3
    entry in the first place -- confirmed live against the real running
    settings.json, which still had exactly this stale entry. Fixed by
    matching on the script's own path instead of the full interpreter
    prefix (2026-07-21 ship-gate review, angle B/C both caught it)."""
    settings_path = tmp_path / "settings.json"
    stale_command = f"python3 {HOOK_SCRIPT} --mode dev --job-id noctis-build"
    new_command = f"{launch_surfaces.PYTHON_BIN} {HOOK_SCRIPT} --mode dev --job-id noctis-build"

    launch_surfaces._merge_hook(settings_path, "Stop", stale_command, HOOK_SCRIPT)
    launch_surfaces._merge_hook(settings_path, "SessionEnd", new_command, HOOK_SCRIPT)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["hooks"]["Stop"] == []
    commands = [h["command"] for e in settings["hooks"]["SessionEnd"] for h in e["hooks"]]
    assert commands == [new_command]


def test_merge_hook_purge_runs_even_when_target_event_already_exact(tmp_path):
    """The purge must run on every call, not just when the target event's
    entry doesn't already match exactly. Writes a settings.json directly
    (not via _merge_hook) with SessionEnd already holding the exact correct
    command *and* a stale Stop entry still present -- a shape that can't
    arise from calling _merge_hook alone once the prefix-matching bug above
    is fixed, but is exactly what a hand-edited or externally-written
    settings.json could look like. A version of this function that returned
    early on "already registered exactly as-is" before running the
    cross-event purge would leave Stop's stale entry untouched forever."""
    settings_path = tmp_path / "settings.json"
    correct_command = f"{launch_surfaces.PYTHON_BIN} {HOOK_SCRIPT}"
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": f"python3 {HOOK_SCRIPT}"}]}],
                    "SessionEnd": [{"matcher": "", "hooks": [{"type": "command", "command": correct_command}]}],
                }
            }
        ),
        encoding="utf-8",
    )

    launch_surfaces._merge_hook(settings_path, "SessionEnd", correct_command, HOOK_SCRIPT)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["hooks"]["Stop"] == []


def test_launch_terminal_exports_job_env(monkeypatch):
    calls = []
    monkeypatch.setattr(launch_surfaces.subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(launch_surfaces, "_ensure_nondev_hooks", lambda: None)

    launch_surfaces.launch_terminal("learn", "no active job", "prompt text", job_slug="due-review")

    script = calls[0][0][2]  # osascript -e <script>
    assert "NOCTIS_MODE=learn" in script
    assert "NOCTIS_JOB_ID=due-review" in script


def test_launch_dev_registers_project_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(launch_surfaces.subprocess, "run", lambda *a, **k: None)

    launch_surfaces.launch_dev(str(tmp_path), "prompt text", job_slug="noctis-build")

    settings_path = tmp_path / ".claude" / "settings.local.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    command = settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert "--mode dev" in command
    assert "--job-id noctis-build" in command


def test_mark_session_end_registers_on_session_end_not_stop(tmp_path, monkeypatch):
    """Stop fires after every agent turn, not on real session termination --
    registering there cleared `busy`/wrote SESSION_END after Claude's first
    response, mid-session, well before the terminal closed. Found live: busy
    expressions flipped back to idle while the user was still working."""
    monkeypatch.setattr(launch_surfaces.subprocess, "run", lambda *a, **k: None)

    launch_surfaces.launch_dev(str(tmp_path), "prompt text", job_slug="noctis-build")

    settings_path = tmp_path / ".claude" / "settings.local.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "Stop" not in settings["hooks"]
    command = settings["hooks"]["SessionEnd"][0]["hooks"][0]["command"]
    assert "mark_session_end.py" in command
    assert "--mode dev" in command
    assert "--job-id noctis-build" in command


def test_launch_terminal_serializes_concurrent_calls(monkeypatch):
    """Regression test for a real race: two non-dev modes launched close
    together (e.g. Vesper + Noctua from the world screen) run
    launch_terminal on separate FastAPI thread-pool threads. Without a
    lock, both the shared settings.json hook merge and the osascript
    dispatch can interleave -- found live 2026-07-22 chasing a report that
    Noctua's session-start callout worked launched alone but not alongside
    Vesper."""
    import time

    in_critical_section = threading.Event()
    overlap_detected = threading.Event()

    def fake_ensure_hooks():
        if in_critical_section.is_set():
            overlap_detected.set()
        in_critical_section.set()
        time.sleep(0.05)  # hold the section long enough for a race to show
        in_critical_section.clear()

    monkeypatch.setattr(launch_surfaces, "_ensure_nondev_hooks", fake_ensure_hooks)
    monkeypatch.setattr(launch_surfaces.subprocess, "run", lambda *a, **k: None)

    threads = [
        threading.Thread(target=launch_surfaces.launch_terminal, args=("research", "job", "prompt"))
        for _ in range(2)
    ] + [
        threading.Thread(target=launch_surfaces.launch_terminal, args=("learn", "job", "prompt"))
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not overlap_detected.is_set()


def test_launch_terminal_includes_append_system_prompt_when_given(monkeypatch):
    calls = []
    monkeypatch.setattr(launch_surfaces.subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(launch_surfaces, "_ensure_nondev_hooks", lambda: None)

    launch_surfaces.launch_terminal(
        "learn", "no active job", "prompt text", system_prompt="Shallow or deep track?"
    )

    script = calls[0][0][2]
    assert "--append-system-prompt" in script
    assert "Shallow or deep track?" in script


def test_launch_terminal_omits_append_system_prompt_when_absent(monkeypatch):
    calls = []
    monkeypatch.setattr(launch_surfaces.subprocess, "run", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(launch_surfaces, "_ensure_nondev_hooks", lambda: None)

    launch_surfaces.launch_terminal("settings", "no active job", "prompt text")

    script = calls[0][0][2]
    assert "--append-system-prompt" not in script
