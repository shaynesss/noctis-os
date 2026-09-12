"""What makes one mode different from another.

Everything here used to be a directory. Each mode had its own
CLAUDE_CONFIG_DIR holding a CLAUDE.md the orchestrator rewrote on every
launch, and that redirect is what made a Noctis session unlike an ordinary
Claude Code one: the config root is where plugins, skills, subagents, slash
commands, MCP servers, accumulated permissions and memory live, so pointing
at a private copy of it left every one of them behind. Faber was reading a
methodology that names Impeccable, the code-review plugin, a Critic
subagent, Playwright, shadcn and Magic MCP, and CodeRabbit -- none of which
its own process could reach.

So the mode is passed on the command line instead. `mode_methodology` is the
text that used to be that file, and `mode_agents` is the mode's subagent
roster as the inline JSON `--agents` takes. Nothing per-mode is written to
disk, which also retires the only real argument for the split dirs: two
concurrent sessions of one mode can no longer race on a file that no longer
exists.
"""
from __future__ import annotations

import json
from pathlib import Path

# Which vault folder a mode's files live in. Imported rather than restated:
# `jobs.py` has needed the same mapping since it was written, and a second
# copy here had already drifted before anything used it. Maintenance is
# absent because it is not under `modes/` at all, and general because it has
# no vault folder -- `jobs.py` names both cases.
from jobs import MODE_VAULT_DIR


def vault_folder(mode: str) -> str | None:
    """The mode's folder under `modes/`, or None when it has none."""
    return MODE_VAULT_DIR.get(mode)


# The inverse, for anything that names a mode by its folder rather than by
# its character. v1's launchers spoke "dev"/"learn" and are gone; this stays
# because the vault's own directory names are still the folder form.
MODE_OF_FOLDER = {folder: mode for mode, folder in MODE_VAULT_DIR.items()}


def mode_methodology(mode: str, job_context: str | None = None) -> str:
    """The mode's composed prompt: universal prompt, overlay, and this
    launch's job context.

    Imported from `prompts.render` rather than reimplemented, so there stays
    exactly one definition of what a mode's prompt is. A failure here is
    non-fatal by design: a session with the base Claude Code prompt and no
    overlay is a worse session, but a session that fails to spawn is no
    session at all, and the old code made the same call for the same reason.
    """
    from prompts.render import VAULT
    try:
        from prompts.render import compose
        text = compose(mode, job_context=job_context)
    except Exception:       # noqa: BLE001 - see docstring
        # The overlay is unreadable. The job context is not -- it came from a
        # different file and was already resolved -- so losing it here would
        # discard something we have because something else was missing. A
        # session that knows which job it is in and nothing else is still a
        # better session than one that knows neither.
        if not job_context:
            return ""
        text = f"## This session's job\n\n{job_context}"
    # Where the vault actually is, absolutely.
    #
    # system.md says 'Vault root: `second-brain/`', which is a *relative*
    # path and true only from ~/Developer. A session's cwd is the project it
    # was launched into, so resolving it there gives
    # <project>/second-brain -- and the first live Faber session duly
    # reported the vault unreadable and guessed ~/second-brain. It had the
    # directory the whole time: --add-dir grants it, and vault_search could
    # see straight into it. It simply did not know the path.
    #
    # Stated here rather than fixed in system.md because the value is
    # machine-specific: VAULT_PATH is an env var, and hardcoding one
    # person's absolute path into a vault document is how it goes stale.
    return f"{text.rstrip()}\n\n## Vault location\n\nThe vault root on this machine is `{VAULT}`. Use that absolute path for Read, Grep and Bash -- relative `second-brain/` resolves against the working directory, which is the project, not the vault.\n"


def mode_agents(mode: str) -> str:
    """The mode's subagents, as the JSON `--agents` expects, or "".

    These have always existed in the vault -- `modes/dev/agents/critic.md`,
    learn's gap-finder and quizmaster, research's credibility-checker and
    synthesizer -- and were never reachable from a session, because a
    subagent has to be registered in the config root and the config root was
    a copy with no agents dir in it. dev.md lists the Critic in its subagent
    roster and every Faber session has been unable to call it.

    Front matter is not parsed beyond `description`: the rest of an agent
    file is its prompt, which is what `--agents` wants.
    """
    folder = vault_folder(mode)
    if not folder:
        return ""
    from prompts.render import VAULT
    agents_dir = VAULT / "modes" / folder / "agents"
    if not agents_dir.is_dir():
        return ""

    agents: dict[str, dict[str, str]] = {}
    for path in sorted(agents_dir.glob("*.md")):
        description, prompt = _split(path.read_text())
        if prompt.strip():
            agents[path.stem] = {"description": description, "prompt": prompt}
    return json.dumps(agents) if agents else ""


def _split(text: str) -> tuple[str, str]:
    """Pull `description` out of YAML front matter; the body is the prompt.

    Deliberately not a YAML parse. These files are hand-written in the vault
    and a malformed one must cost its own description, not every agent in the
    mode -- and pulling one key needs no dependency to do badly.
    """
    description = ""
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            front, body = text[3:end], text[end + 4:]
            for line in front.splitlines():
                key, _, value = line.partition(":")
                if key.strip() == "description":
                    description = value.strip().strip("'\"")
                    break
    return description or "A subagent defined in the vault.", body.strip()
