"""What an interactive session needs, for the shell that hosts it in a PTY.

The Rust side owns the pseudo-terminal and knows nothing about modes; this
owns the mode and knows nothing about terminals. So the shell asks here for
the argv and gets back a list to hand `portable_pty`.

**It is deliberately not `driver.build_command`.** That builds a `-p` spawn:
`--output-format stream-json`, `--verbose`, a permission-prompt tool, a prompt
baked into the argv. An interactive session wants none of those -- it renders
itself, prompts for its own permissions, and reads what you type. Sharing one
function would mean a flag list with an `if interactive` running through it,
and the two genuinely differ more than they agree.

What they *do* share is the part that must not drift: the model per mode, the
methodology overlay, the subagent roster, the vault as a second allowed
directory, and the tracked permission policy. Those are imported, not copied.

See `PTY-MIGRATION.md`. This is step 1 of §7, and it runs beside the
orchestrator rather than replacing it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import jobs
import vault_io
from engine import MODE_MODELS, MODELS, SHARED_SETTINGS, claude_binary, mcp_config
from orchestrator.modes import mode_agents, mode_methodology

REPO_ROOT = Path(__file__).resolve().parent.parent
STATUSLINE = REPO_ROOT / "backend" / "scripts" / "statusline.sh"
# Absolute, and derived rather than committed, for the reason the hooks block
# in `engine.py` gives: an interpreter path cannot live in a tracked settings
# file. The venv's python is named explicitly because a PTY child inherits the
# shell's PATH, which need not have one.
PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python3"
GUARD_SHARED_TREE = REPO_ROOT / "backend" / "hooks" / "guard_shared_tree.py"


def statusline_settings(mode: str = "general", port: int | None = None,
                        slot: str | None = None) -> dict:
    """The tracked policy plus a status line that reports back here.

    `statusLine` is how an interactive session hands over what the stream used
    to: the 5h and 7d windows, context occupancy, effort, the model, and the
    session's own id and transcript path. The CLI runs this command on every
    render and passes the payload on stdin, so the status bar stops depending
    on a turn being in flight to know anything.

    Composed rather than written to a file for the same reason
    `driver.settings_config` composes: the command needs an absolute path that
    cannot be committed.
    """
    policy = json.loads(SHARED_SETTINGS.read_text())
    # The mode rides along as an argument. The transcript on disk does not
    # record which Noctis mode launched a session -- its `mode` field is the
    # CLI's permission mode -- so this is the one place the mapping can be
    # captured, at the moment the session first identifies itself.
    # The slot too: the shell's terminal strip needs to know which of its
    # terminals a report belongs to, and the session id is not known to the
    # shell until this very report arrives -- so the shell's own name for the
    # terminal rides out and comes back.
    #
    # `refreshInterval` keeps an idle terminal reporting. Without it the
    # status line only re-runs when the CLI redraws, so a session sitting at
    # its prompt after `/model` never told the bar its model changed. It
    # cannot make the rate-limit figures fresher than the session's last API
    # response -- nothing can -- which is why the bar shows the reading's age.
    policy["statusLine"] = {
        "type": "command",
        "command": f"bash {STATUSLINE} {port or os.environ.get('PORT', '8000')} {mode} {slot or '-'}",
        "refreshInterval": 5,
    }
    # The shared-tree guard rides in the argv rather than in a project's
    # `.claude/settings.local.json`, because it has to hold in every project,
    # including one that has no Noctis files in it at all. Sessions run in
    # parallel on one repository by design; this refuses only the commands that
    # act on the whole working tree, and only while someone else is in it.
    policy.setdefault("hooks", {}).setdefault("PreToolUse", []).append({
        "matcher": "Bash",
        "hooks": [{"type": "command",
                   "command": f"{PYTHON} {GUARD_SHARED_TREE}"}],
    })
    return policy


OPENING_PROMPT = (
    "Open the session: in a few lines, say which mode you are, what this "
    "session is for, and which directory you are in. If a job or project is "
    "evident from here, name it and its state. Then wait for direction."
)


# What `claude --effort` accepts. Listed rather than passed through, because
# an unknown level is rejected by the CLI *after* the terminal has opened:
# the pane shows a usage error where a session should be, which reads as the
# app being broken rather than as a bad argument.
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def spawn_args(mode: str, cwd: str, resume_id: str | None = None,
               slot: str | None = None, prompt: str | None = None,
               effort: str | None = None, model: str | None = None) -> dict:
    """Everything the shell needs to open one interactive session.

    Returns the binary separately from the arguments because the Rust side
    resolves the binary itself when this cannot -- the same PATH problem
    `driver.claude_binary` exists for, in a second process.
    """
    if mode not in MODE_MODELS:
        raise ValueError(f"unknown mode {mode!r}")

    # The mode's model unless the launcher said otherwise. A mode is its
    # methodology, not its model: running Faber on a cheaper tier for
    # mechanical work is effort routing, which dev.md already describes as a
    # per-job call rather than a property of the mode.
    if model and model not in MODELS:
        raise ValueError(f"unknown model {model!r}; expected one of {', '.join(MODELS)}")
    chosen_model = model or MODE_MODELS[mode]
    args: list[str] = ["--model", chosen_model]

    # How hard the session thinks, chosen at the launcher rather than typed
    # as `/effort` once it is already running. Omitted when not given, which
    # leaves the CLI's own configured level in place: this is an override,
    # and a default sent as an override would quietly outrank
    # `~/.claude/settings.json` for every session the app starts.
    if effort:
        if effort not in EFFORTS:
            raise ValueError(f"unknown effort {effort!r}; expected one of {', '.join(EFFORTS)}")
        args += ["--effort", effort]

    # The job whose project_path is this directory is the job this session is
    # about to work on, and its brief rides in the overlay. Resolved here
    # rather than sent by the shell: no parameter to keep in sync, and the
    # mapping is the one already made by opening that directory. The old
    # launch route did this and the first terminal version did not -- a Faber
    # session opened in a repo with its job context silently absent, which
    # is the never-called shape the 09-11 audit kept finding.
    job_context = jobs.job_brief(mode, Path(cwd))

    # The mode, as text in the argv. Same mechanism as a `-p` spawn: it cannot
    # be raced by a second session of the same mode, and it switches
    # system-prompt snapshotting off so an edited methodology reaches a
    # resumed session.
    if methodology := mode_methodology(mode, job_context):
        args += ["--append-system-prompt", methodology]
    if agents := mode_agents(mode):
        args += ["--agents", agents]

    args += ["--mcp-config", mcp_config()]
    args += ["--settings", json.dumps(statusline_settings(mode, slot=slot))]

    # The vault, always. A session sandboxed to its working directory cannot
    # read its own methodology, job context or lessons -- all of which live
    # outside it.
    if vault := vault_io.get_vault_path():
        args += ["--add-dir", str(vault)]

    if resume_id:
        args += ["--resume", resume_id]

    # A first prompt, submitted as the session opens. `claude "text"` starts
    # interactively with that text already sent, which is what a handoff
    # needs: the summary the previous session carried over arrives as the
    # opening message rather than sitting in a clipboard. Last, because it
    # is positional and everything before it is a flag.
    #
    # Behind `--`, always. A handoff summary that begins with a bullet --
    # "- first, the parser…" -- is an argument that begins with a dash, and
    # the CLI's option parser read one as `error: unknown option` and exited
    # before the terminal had painted. The terminator ends option parsing;
    # everything after it is the prompt, whatever it starts with.
    #
    # Never empty. A session that opens to a bare prompt is indistinguishable
    # from one that failed to load its methodology, and the first thing a
    # person does with it is ask what it is. So a fresh session -- not a
    # resume, which has its own history to come back to -- opens by saying
    # what it is, from the methodology it was actually given.
    if prompt and prompt.strip():
        args += ["--", prompt]
    elif not resume_id:
        args += ["--", OPENING_PROMPT]

    # The environment beside the argv. The telemetry hooks attribute an
    # action to a mode and a job by reading these; a PTY child otherwise
    # inherits the shell process's environment, and a vesper session was
    # found logging under `faber` -- whatever the shell happened to have.
    env = {"NOCTIS_MODE": mode}
    if slug := jobs.find_job_for_cwd(mode, Path(cwd)):
        env["NOCTIS_JOB_ID"] = slug

    return {
        "binary": claude_binary(),
        "args": args,
        "env": env,
        "cwd": cwd,
        "mode": mode,
        "model": chosen_model,
    }
