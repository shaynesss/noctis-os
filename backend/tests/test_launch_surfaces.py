import json
from pathlib import Path

import launch_surfaces

HOOK_SCRIPT = Path("/fake/hook.py")


def test_merge_hook_creates_settings_file(tmp_path):
    settings_path = tmp_path / "settings.json"
    launch_surfaces._merge_hook(settings_path, "PostToolUse", "python3 hook.py", HOOK_SCRIPT)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "python3 hook.py"


def test_merge_hook_preserves_existing_keys(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"theme": "auto"}), encoding="utf-8")

    launch_surfaces._merge_hook(settings_path, "PostToolUse", "python3 hook.py", HOOK_SCRIPT)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["theme"] == "auto"
    assert settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "python3 hook.py"


def test_merge_hook_is_idempotent(tmp_path):
    settings_path = tmp_path / "settings.json"
    launch_surfaces._merge_hook(settings_path, "PostToolUse", "python3 hook.py", HOOK_SCRIPT)
    launch_surfaces._merge_hook(settings_path, "PostToolUse", "python3 hook.py", HOOK_SCRIPT)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert len(settings["hooks"]["PostToolUse"]) == 1


def test_merge_hook_replaces_stale_entry_for_same_script(tmp_path):
    """A new job in the same project must replace the old job's hook, not
    accumulate alongside it -- otherwise the old job's hook keeps firing on
    every future session in that project (2026-07-21 ship-gate finding)."""
    settings_path = tmp_path / "settings.json"
    old_command = f"python3 {HOOK_SCRIPT} --mode dev --job-id old-job"
    new_command = f"python3 {HOOK_SCRIPT} --mode dev --job-id new-job"

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
