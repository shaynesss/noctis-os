"""Reading a mode's methodology and subagents out of the vault.

Separate from the driver tests because these touch the vault and those do
not: the driver's job is to put whatever comes back into the argv, and the
two failing independently is the point.
"""
import json

from orchestrator import modes


def _vault(tmp_path, monkeypatch, agents: dict[str, str]):
    d = tmp_path / "modes" / "dev" / "agents"
    d.mkdir(parents=True)
    for name, text in agents.items():
        (d / f"{name}.md").write_text(text)
    monkeypatch.setattr("prompts.render.VAULT", tmp_path)
    return tmp_path


def test_an_agent_becomes_a_registered_subagent(tmp_path, monkeypatch):
    """These files have existed in the vault the whole time and no session
    could reach one: a subagent has to be registered in the config root, and
    the config root was a private copy with no agents dir in it."""
    _vault(tmp_path, monkeypatch, {"critic": (
        "---\nname: critic\ndescription: Reviews against locked decisions\n---\n"
        "You are the Critic. Read-only.\n"
    )})
    agents = json.loads(modes.mode_agents("faber"))
    assert agents["critic"]["description"] == "Reviews against locked decisions"
    assert "You are the Critic" in agents["critic"]["prompt"]
    assert "---" not in agents["critic"]["prompt"], "front matter is not the prompt"


def test_a_malformed_agent_costs_only_its_own_description(tmp_path, monkeypatch):
    """Hand-written vault files, so one bad header must not take the roster
    down with it -- which a strict YAML parse would do."""
    _vault(tmp_path, monkeypatch, {
        "broken": "---\nthis: is: not: yaml\n---\nStill a usable prompt.\n",
        "fine": "---\ndescription: Good one\n---\nAlso usable.\n",
    })
    agents = json.loads(modes.mode_agents("faber"))
    assert set(agents) == {"broken", "fine"}
    assert agents["broken"]["description"]      # a fallback, never empty
    assert "Still a usable prompt." in agents["broken"]["prompt"]


def test_an_agent_with_no_body_is_skipped(tmp_path, monkeypatch):
    """--agents wants a prompt. An empty one would register a subagent that
    does nothing, which is worse than not offering it."""
    _vault(tmp_path, monkeypatch, {"hollow": "---\ndescription: nothing\n---\n"})
    assert modes.mode_agents("faber") == ""


def test_a_mode_with_no_roster_registers_nothing(tmp_path, monkeypatch):
    _vault(tmp_path, monkeypatch, {})
    assert modes.mode_agents("general") == ""


def test_a_missing_vault_is_not_fatal(tmp_path, monkeypatch):
    """A worse session beats no session: the spawn goes ahead with the base
    prompt rather than failing, which is the call the old code made too."""
    # Both, because render.py binds PROMPTS = VAULT / "prompts" at import:
    # moving VAULT alone leaves compose() still reading the real one, which
    # is a trap worth encoding rather than working around silently.
    monkeypatch.setattr("prompts.render.VAULT", tmp_path / "nope")
    monkeypatch.setattr("prompts.render.PROMPTS", tmp_path / "nope" / "prompts")
    assert modes.mode_agents("faber") == ""
    assert modes.mode_methodology("faber") == ""


def test_the_methodology_states_where_the_vault_actually_is(tmp_path, monkeypatch):
    """The first live Faber session reported the vault unreadable.

    It had the directory the whole time -- --add-dir grants it and
    vault_search read straight into it -- but nothing ever said where it was.
    system.md gives 'Vault root: `second-brain/`', which is relative and true
    only from ~/Developer; a session's cwd is the project it was launched
    into, so it resolved to <project>/second-brain and then guessed
    ~/second-brain. Faber's own overlay points at
    `second-brain/modes/dev/dev.md` for the real methodology, so the wrong
    path cost it the 22KB document the 672-byte overlay only points to.
    """
    prompts = tmp_path / "prompts"
    (prompts / "overlays").mkdir(parents=True)
    (prompts / "system.md").write_text("universal")
    (prompts / "overlays" / "faber.md").write_text("faber overlay")
    monkeypatch.setattr("prompts.render.VAULT", tmp_path)
    monkeypatch.setattr("prompts.render.PROMPTS", prompts)

    text = modes.mode_methodology("faber")
    assert str(tmp_path) in text, "the absolute vault root must be stated"
    assert "universal" in text and "faber overlay" in text


def test_an_unreadable_overlay_does_not_discard_the_job_context(tmp_path, monkeypatch):
    """They come from different files. Losing the context because the overlay
    was missing discards something already in hand — and a session that knows
    which job it is in beats one that knows neither."""
    monkeypatch.setattr("prompts.render.VAULT", tmp_path)
    monkeypatch.setattr("prompts.render.PROMPTS", tmp_path / "nope")
    text = modes.mode_methodology("faber", job_context="**proj** stage: Ship")
    assert "stage: Ship" in text
    assert modes.mode_methodology("faber") == "", "no overlay and no job is still nothing"
