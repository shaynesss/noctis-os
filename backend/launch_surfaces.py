"""Session launch surfaces, per mode — SPEC.md EDD "Session launch surfaces,
per mode": Dev opens VS Code, the other four open a character-tinted
Terminal.app window. Fire-and-forget: this module only starts the surface,
it never watches or controls the session afterward.
"""

import colorsys
import json
import shlex
import shutil
import subprocess
from pathlib import Path

# The desktop app (desktop/app.py) launches uvicorn via LaunchServices, not a
# login shell -- that process's inherited PATH is the bare macOS default
# (/usr/bin:/bin:/usr/sbin:/sbin), which doesn't include /usr/local/bin or
# /opt/homebrew/bin. shutil.which("code") silently returns None in that
# environment even though `code` works fine in every interactive terminal,
# which made every dev-mode launch (new build and resume) 500 with no
# indication why. Found live 2026-07-22 chasing a broken resume button.
_CODE_BIN_FALLBACKS = [
    "/usr/local/bin/code",
    "/opt/homebrew/bin/code",
    "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
]


def _find_code_binary() -> str:
    found = shutil.which("code")
    if found:
        return found
    for candidate in _CODE_BIN_FALLBACKS:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError(
        "Could not locate the `code` CLI (checked PATH and common install "
        "locations). Install the 'code' command from VS Code's Command "
        "Palette: 'Shell Command: Install code command in PATH'."
    )

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
# Bare "python3" resolves to whatever's on PATH in the launched Terminal
# shell, not this project's venv -- fine while the hooks were stdlib-only,
# but mark_session_end.py now needs vault_io (python-frontmatter) to clear
# the busy flag on session end, so hooks need the venv's interpreter
# specifically. Found while wiring that up, not before it mattered.
PYTHON_BIN = Path(__file__).parent / ".venv" / "bin" / "python3"


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

    Also purges the same script from every *other* event bucket, not just
    `event` — each hook script here is meant to be bound to exactly one
    event. Without this, moving mark_session_end.py from Stop to SessionEnd
    (found live: Stop fires per-turn, not on real session termination)
    would have left the stale Stop registration firing forever alongside
    the new correct one on any settings.json that predated the fix.

    Two bugs found in that purge itself during the 2026-07-21 ship-gate
    review (both confirmed live against the real running settings.json,
    which still had a stale `Stop` entry sitting next to the new
    `SessionEnd` one): (1) the match was keyed on a prefix built from
    PYTHON_BIN, so an entry registered before PYTHON_BIN existed (bare
    `python3`) never matched and never got purged — now matches on the
    script's own path as a substring, independent of whatever interpreter
    prefixed it historically. (2) the purge ran *after* an early return for
    "already registered exactly as-is," so once the target event's entry
    was correct, the purge never ran again on subsequent calls, even though
    a stale entry from the older prefix was still sitting in another event
    bucket — the purge now always runs first, unconditionally.
    """
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}

    script_marker = shlex.quote(str(script_path))

    def _same_script(existing_command: str) -> bool:
        return script_marker in existing_command

    hooks_by_event = settings.setdefault("hooks", {})

    changed = False
    for other_event, other_entries in hooks_by_event.items():
        if other_event == event:
            continue
        filtered = [
            entry for entry in other_entries if not any(_same_script(hook.get("command", "")) for hook in entry.get("hooks", []))
        ]
        if filtered != other_entries:
            changed = True
        other_entries[:] = filtered

    entries = hooks_by_event.setdefault(event, [])

    # Compare against *every* existing entry for this script, not just
    # whether the correct command is present somewhere -- an early return
    # keyed only on "already present" left a stale duplicate (e.g. from
    # before PYTHON_BIN existed) sitting alongside the correct entry
    # forever, since once the correct one existed the purge below never ran
    # again. Found live 2026-07-22: every PostToolUse call was firing
    # log_action.py twice. Now: strip anything for this script and
    # re-append exactly once, unless the entries already are exactly that
    # single correct entry (skip only to avoid a no-op file write).
    correct_entry = {"matcher": "", "hooks": [{"type": "command", "command": command}]}
    matching = [
        entry for entry in entries if any(_same_script(hook.get("command", "")) for hook in entry.get("hooks", []))
    ]
    if matching != [correct_entry]:
        entries[:] = [entry for entry in entries if not any(_same_script(hook.get("command", "")) for hook in entry.get("hooks", []))]
        entries.append(correct_entry)
        changed = True

    if changed:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _ensure_nondev_hooks() -> None:
    """Static hook commands, no baked args — both hook scripts read job
    identity from NOCTIS_MODE/NOCTIS_JOB_ID env vars set per-launch in the
    exported shell command (see launch_terminal), so concurrent Terminal.app
    sessions sharing this one settings.json never race on whose job gets
    logged/closed. SessionEnd registers mark_session_end.py -- the other
    half of staleness.py's flagging mechanism (a job that closes cleanly
    must never get flagged, however old it later gets). Deliberately
    SessionEnd, not Stop: Stop fires after every single agent turn (Claude
    finishes responding, waits for the next prompt), not on session
    termination -- registering there cleared `busy` and wrote the
    SESSION_END sentinel after the *first* response in a session, while
    the terminal was still open and very much in use. Found live: busy
    expressions were turning back to idle mid-session. SessionEnd only
    fires once, when the CLI process itself actually exits.
    """
    log_command = f"{shlex.quote(str(PYTHON_BIN))} {shlex.quote(str(HOOK_SCRIPT))}"
    _merge_hook(NONDEV_CONFIG_DIR / "settings.json", "PostToolUse", log_command, HOOK_SCRIPT)
    end_command = f"{shlex.quote(str(PYTHON_BIN))} {shlex.quote(str(SESSION_END_HOOK_SCRIPT))}"
    _merge_hook(NONDEV_CONFIG_DIR / "settings.json", "SessionEnd", end_command, SESSION_END_HOOK_SCRIPT)


def _ensure_dev_hooks(project_path: str, job_slug: str | None) -> None:
    """VS Code's URI handler doesn't carry shell env, so job identity is
    baked directly into both hook commands and registered in this project's
    own local settings — scoped per project. _merge_hook replaces rather
    than accumulates, so this always reflects the most recently launched
    job for this project_path, not every job that ever ran here.
    """
    settings_path = Path(project_path) / ".claude" / "settings.local.json"
    log_command = (
        f"{shlex.quote(str(PYTHON_BIN))} {shlex.quote(str(HOOK_SCRIPT))} "
        f"--mode dev --job-id {shlex.quote(job_slug or 'general')}"
    )
    _merge_hook(settings_path, "PostToolUse", log_command, HOOK_SCRIPT)
    end_command = (
        f"{shlex.quote(str(PYTHON_BIN))} {shlex.quote(str(SESSION_END_HOOK_SCRIPT))} "
        f"--mode dev --job-id {shlex.quote(job_slug or 'general')}"
    )
    # SessionEnd, not Stop -- see _ensure_nondev_hooks' docstring for why.
    _merge_hook(settings_path, "SessionEnd", end_command, SESSION_END_HOOK_SCRIPT)


def _darken_hex(hex_color: str, lightness: float = 0.175) -> tuple[int, int, int]:
    """Hue preserved, lightness reduced to ~15-20% — SPEC.md's spec for the
    Terminal.app background tint (full-saturation fights text readability).
    Returns 16-bit RGB (0-65535) as AppleScript's "background color" expects.
    """
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    h, _, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, lightness, s)
    return tuple(round(c * 65535) for c in (r, g, b))


def _write_resume_task(project_path: str, prompt: str, model: str | None) -> None:
    """Writes a VS Code task that runs the real `claude` CLI in the
    integrated terminal, set to fire automatically when the folder opens.
    Replaces the old vscode://anthropic.claude-code/open?prompt= URI
    approach (found live 2026-07-22: that pre-filled the extension's own
    chat panel, not a real terminal session -- Shayne wants the actual CLI,
    same as every other mode gets in Terminal.app). No CLAUDE_CONFIG_DIR
    override -- dev reads the default ~/.claude/CLAUDE.md -> modes/dev/dev.md.

    Gitignored, same as _ensure_dev_hooks' settings.local.json -- this is
    per-launch generated local config, not project source. Only covers the
    genuine-folder-open case: if VS Code already has this project open,
    `runOn: folderOpen` won't refire (VS Code only runs it on real open
    events, not window focus) -- a known gap, not attempted to be papered
    over here.

    "type": "process" with an explicit `zsh -lc <one string>`, not "type":
    "shell" with an args array -- found live 2026-07-22: the task failed to
    launch (exit code 1) because VS Code's own automatic arg-quoting choked
    on the prompt, which is markdown full of backticks, `$`, and apostrophe
    contractions from the vault docs. "process" hands args straight to
    execve with no extra quoting layer, so the one place doing any escaping
    is our own shlex.quote() on the whole command string -- the exact
    approach launch_terminal already uses successfully for Terminal.app.
    """
    model_flag = f"--model {shlex.quote(model)} " if model else ""
    command = f"claude {model_flag}{shlex.quote(prompt)}"
    task = {
        "version": "2.0.0",
        "tasks": [
            {
                "label": "Resume Claude Code session",
                "type": "process",
                "command": "/bin/zsh",
                "args": ["-lc", command],
                "presentation": {"reveal": "always", "panel": "new", "focus": True},
                "runOptions": {"runOn": "folderOpen"},
            }
        ],
    }
    vscode_dir = Path(project_path) / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    (vscode_dir / "tasks.json").write_text(json.dumps(task, indent=2), encoding="utf-8")

    # Without this, VS Code prompts "Do you want to allow automatic tasks in
    # this folder?" the first time -- silent otherwise, since this project
    # is only ever opened via our own launcher.
    settings_path = vscode_dir / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    settings["task.allowAutomaticTasks"] = "on"
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def launch_dev(
    project_path: str, prompt: str, job_slug: str | None = None, model: str | None = None
) -> None:
    """Two-step: write the resume task, then `code <path>` opens/focuses VS
    Code on the project -- the folderOpen task fires and runs `claude` for
    real in the integrated terminal.
    """
    _ensure_dev_hooks(project_path, job_slug)
    _write_resume_task(project_path, prompt, model)
    subprocess.run([_find_code_binary(), project_path], check=True)


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
