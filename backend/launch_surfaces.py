"""Session launch surfaces, per mode — SPEC.md EDD "Session launch surfaces,
per mode": Dev opens VS Code, the other four open a character-tinted
Terminal.app window. Fire-and-forget: this module only starts the surface,
it never watches or controls the session afterward.
"""

import colorsys
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


def _darken_hex(hex_color: str, lightness: float = 0.175) -> tuple[int, int, int]:
    """Hue preserved, lightness reduced to ~15-20% — SPEC.md's spec for the
    Terminal.app background tint (full-saturation fights text readability).
    Returns 16-bit RGB (0-65535) as AppleScript's "background color" expects.
    """
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, lightness, s)
    return tuple(round(c * 65535) for c in (r, g, b))


def launch_dev(project_path: str, prompt: str, model: str | None = None) -> None:
    """Two-step: `code <path>` opens/focuses VS Code on the project, then the
    Claude Code extension's URI handler pre-fills the prompt (doesn't
    auto-submit). No CLAUDE_CONFIG_DIR override — dev reads the default
    ~/.claude/CLAUDE.md -> modes/dev/dev.md. Model override, if given, is
    prepended to the pre-filled prompt text since the URI handler has no
    separate model parameter.
    """
    subprocess.run(["code", project_path], check=True)
    model_prefix = f"--model {model} " if model else ""
    encoded = shlex.quote(f"{model_prefix}{prompt}")
    subprocess.run(
        ["open", f"vscode://anthropic.claude-code/open?prompt={encoded}"],
        check=True,
    )


def launch_terminal(mode: str, job_label: str, prompt: str, model: str | None = None) -> None:
    """Opens a new Terminal.app window, tinted to the character's darkened
    hex, titled "{character} — {mode} — {job/topic}", with CLAUDE_CONFIG_DIR
    pointed at the minimal non-dev config so this session doesn't inherit
    Faber's build-phase methodology.
    """
    character = MODE_CHARACTER[mode]
    r, g, b = _darken_hex(CHARACTER_HEX[mode])
    title = f"{character} — {mode} — {job_label}"

    model_flag = f"--model {shlex.quote(model)} " if model else ""
    command = (
        f"export CLAUDE_CONFIG_DIR={shlex.quote(str(NONDEV_CONFIG_DIR))} && "
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
