"""Session launch surfaces, per mode — SPEC.md EDD "Session launch surfaces,
per mode": Dev opens VS Code, the other four open a character-tinted
Terminal.app window. Fire-and-forget: this module only starts the surface,
it never watches or controls the session afterward.
"""

import colorsys
import json
import shlex
import subprocess
from pathlib import Path

MODE_CHARACTER = {
    "dev": "Faber",
    "learn": "Noctua",
    "research": "Vesper",
    "settings": "Custos",
    "nightshift": "Echo",
}

# Sampled directly from assets/characters/<name>.png's dominant fill color
# (see that folder's README) — still interim until the grid-data/PIL render
# pipeline locks exact production values, but real, not guessed.
CHARACTER_HEX = {
    "dev": "#E53311",
    "learn": "#ECA207",
    "research": "#953EAD",
    "settings": "#DA5B00",
    "nightshift": "#293187",
}

NONDEV_CONFIG_DIR = Path(__file__).parent / "launch_config" / "nondev"
HOOK_SCRIPT = Path(__file__).parent / "hooks" / "log_action.py"
SESSION_END_HOOK_SCRIPT = Path(__file__).parent / "hooks" / "mark_session_end.py"


def _merge_hook(settings_path: Path, event: str, command: str, script_path: Path) -> None:
    """Idempotently register `command` for `event` in a Claude Code
    settings.json, preserving whatever else Claude Code has already written
    there. The nondev settings.json is gitignored/CC-managed (see that
    dir's gitignore note), so this is the only place that guarantees our
    telemetry hook is actually present each launch, rather than committing
    a static file CC would just mutate around.

    Replaces any existing entry for the same script (matched by its command
    prefix) rather than appending alongside it. Dev's hooks bake a job_slug
    into the command, so without this, every new job in the same project
    would add a new hook entry and never remove the previous job's — with
    an unconditional matcher (""), *all* of them keep firing on every
    future session in that project, so an old job's runtime log keeps
    getting fresh activity/SESSION_END writes forever, permanently
    defeating staleness.py's flagging for that job. Found in the
    2026-07-21 ship-gate review; at most one hook per script per event now.
    """
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}

    script_prefix = f"python3 {shlex.quote(str(script_path))}"
    entries = settings.setdefault("hooks", {}).setdefault(event, [])

    for entry in entries:
        for hook in entry.get("hooks", []):
            if hook.get("command") == command:
                return  # already registered exactly as-is

    entries[:] = [
        entry
        for entry in entries
        if not any(hook.get("command", "").startswith(script_prefix) for hook in entry.get("hooks", []))
    ]
    entries.append({"matcher": "", "hooks": [{"type": "command", "command": command}]})
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _ensure_nondev_hooks() -> None:
    """Static hook commands, no baked args — both hook scripts read job
    identity from NOCTIS_MODE/NOCTIS_JOB_ID env vars set per-launch in the
    exported shell command (see launch_terminal), so concurrent Terminal.app
    sessions sharing this one settings.json never race on whose job gets
    logged/closed. Stop registers mark_session_end.py -- the other half of
    staleness.py's flagging mechanism (a job that closes cleanly must never
    get flagged, however old it later gets).
    """
    log_command = f"python3 {shlex.quote(str(HOOK_SCRIPT))}"
    _merge_hook(NONDEV_CONFIG_DIR / "settings.json", "PostToolUse", log_command, HOOK_SCRIPT)
    end_command = f"python3 {shlex.quote(str(SESSION_END_HOOK_SCRIPT))}"
    _merge_hook(NONDEV_CONFIG_DIR / "settings.json", "Stop", end_command, SESSION_END_HOOK_SCRIPT)


def _ensure_dev_hooks(project_path: str, job_slug: str | None) -> None:
    """VS Code's URI handler doesn't carry shell env, so job identity is
    baked directly into both hook commands and registered in this project's
    own local settings — scoped per project. _merge_hook replaces rather
    than accumulates, so this always reflects the most recently launched
    job for this project_path, not every job that ever ran here.
    """
    settings_path = Path(project_path) / ".claude" / "settings.local.json"
    log_command = (
        f"python3 {shlex.quote(str(HOOK_SCRIPT))} "
        f"--mode dev --job-id {shlex.quote(job_slug or 'general')}"
    )
    _merge_hook(settings_path, "PostToolUse", log_command, HOOK_SCRIPT)
    end_command = (
        f"python3 {shlex.quote(str(SESSION_END_HOOK_SCRIPT))} "
        f"--mode dev --job-id {shlex.quote(job_slug or 'general')}"
    )
    _merge_hook(settings_path, "Stop", end_command, SESSION_END_HOOK_SCRIPT)


def _darken_hex(hex_color: str, lightness: float = 0.175) -> tuple[int, int, int]:
    """Hue preserved, lightness reduced to ~15-20% — SPEC.md's spec for the
    Terminal.app background tint (full-saturation fights text readability).
    Returns 16-bit RGB (0-65535) as AppleScript's "background color" expects.
    """
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, lightness, s)
    return tuple(round(c * 65535) for c in (r, g, b))


def launch_dev(
    project_path: str, prompt: str, job_slug: str | None = None, model: str | None = None
) -> None:
    """Two-step: `code <path>` opens/focuses VS Code on the project, then the
    Claude Code extension's URI handler pre-fills the prompt (doesn't
    auto-submit). No CLAUDE_CONFIG_DIR override — dev reads the default
    ~/.claude/CLAUDE.md -> modes/dev/dev.md. Model override, if given, is
    prepended to the pre-filled prompt text since the URI handler has no
    separate model parameter.
    """
    _ensure_dev_hooks(project_path, job_slug)
    subprocess.run(["code", project_path], check=True)
    model_prefix = f"--model {model} " if model else ""
    encoded = shlex.quote(f"{model_prefix}{prompt}")
    subprocess.run(
        ["open", f"vscode://anthropic.claude-code/open?prompt={encoded}"],
        check=True,
    )


def launch_terminal(
    mode: str,
    job_label: str,
    prompt: str,
    job_slug: str | None = None,
    model: str | None = None,
) -> None:
    """Opens a new Terminal.app window, tinted to the character's darkened
    hex, titled "{character} — {mode} — {job/topic}", with CLAUDE_CONFIG_DIR
    pointed at the minimal non-dev config so this session doesn't inherit
    Faber's build-phase methodology.
    """
    _ensure_nondev_hooks()
    character = MODE_CHARACTER[mode]
    r, g, b = _darken_hex(CHARACTER_HEX[mode])
    title = f"{character} — {mode} — {job_label}"

    model_flag = f"--model {shlex.quote(model)} " if model else ""
    command = (
        f"export NOCTIS_MODE={shlex.quote(mode)} "
        f"NOCTIS_JOB_ID={shlex.quote(job_slug or 'general')} "
        f"CLAUDE_CONFIG_DIR={shlex.quote(str(NONDEV_CONFIG_DIR))} && "
        f"claude {model_flag}{shlex.quote(prompt)}"
    )

    script = f"""
    tell application "Terminal"
        activate
        set newWindow to do script {_applescript_string(command)}
        set background color of newWindow to {{{r}, {g}, {b}}}
        set custom title of newWindow to {_applescript_string(title)}
    end tell
    """
    subprocess.run(["osascript", "-e", script], check=True)


def _applescript_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
