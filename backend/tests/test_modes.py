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
