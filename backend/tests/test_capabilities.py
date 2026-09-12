"""What a mode needs vs. what the harness has.

The failure this exists for: dev.md mandated seven tools -- Impeccable, the
code-review plugin, a Critic subagent, Playwright, shadcn and Magic MCP,
CodeRabbit -- and a Noctis-launched Faber session could reach none of them,
for months, silently. A requirement in prose and a capability in a config
root never meet on their own.
"""
import json
from pathlib import Path

import pytest

import capabilities

REAL_VAULT = Path("/Users/shayneyong/Developer/second-brain")


@pytest.fixture
def real_vault(monkeypatch):
    """conftest points VAULT at a tmp dir for every test, which is right for
    everything that writes and wrong for the two checks here that describe
    *this machine*. Without it they pass alone and fail in the suite, which
    is worse than either -- so they say which vault they mean."""
    if not REAL_VAULT.is_dir():
        pytest.skip("real vault not present")
    monkeypatch.setattr("prompts.render.VAULT", REAL_VAULT)
    monkeypatch.setattr("prompts.render.PROMPTS", REAL_VAULT / "prompts")


def test_this_machine_satisfies_every_mode(real_vault):
    """Regression guard for 2026-09-11. Faber in particular: it lost its
    whole toolkit to a CLAUDE_CONFIG_DIR redirect and nothing said so."""
    for r in capabilities.report_all():
        assert r.ok, f"{r.mode} is missing {sorted(r.missing)}"


def test_a_harness_without_plugins_is_reported_not_tolerated(monkeypatch, tmp_path):
    """The point of the module. Swapping to a harness with no plugin surface
    must name what Faber loses, at startup -- not leave a review gate quietly
    doing nothing three sessions later."""
    monkeypatch.setattr(capabilities, "_plugins", lambda root: set())
    r = capabilities.report("faber")
    assert not r.ok
    assert "skill:impeccable" in r.missing


def test_a_harness_without_subagents_names_the_agent_it_loses():
    """`--agents` is Claude Code's. Another harness may have no equivalent,
    and the honest answer is 'Faber loses critic', not silence."""
    import orchestrator.modes as modes
    original = modes.mode_agents
    try:
        modes.mode_agents = lambda mode: ""
        assert "agent:critic" in capabilities.report("faber").missing
        assert "agent:gap-finder" in capabilities.report("noctua").missing
    finally:
        modes.mode_agents = original


def test_the_probe_follows_a_redirected_config_root(monkeypatch, tmp_path):
    """Reports what is true, not what the code intends. build_env strips
    CLAUDE_CONFIG_DIR for spawns; a stray one in the environment would
    otherwise have this describing a different machine than sessions run on.
    """
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert capabilities.config_root() == tmp_path
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert capabilities.config_root().name == ".claude"


def test_every_declared_agent_actually_exists_in_the_vault(real_vault):
    """REQUIRED names agents by the filename the vault uses. A rename there
    would otherwise show up as a permanent, meaningless gap."""
    from orchestrator.modes import mode_agents
    for mode, needs in capabilities.REQUIRED.items():
        wanted = {n.removeprefix("agent:") for n in needs if n.startswith("agent:")}
        if not wanted:
            continue
        assert wanted <= set(json.loads(mode_agents(mode))), mode


def test_render_states_the_gap_rather_than_a_count(monkeypatch):
    monkeypatch.setattr(capabilities, "_plugins", lambda root: set())
    out = capabilities.render()
    assert "GAP" in out and "skill:impeccable" in out


def test_the_migration_brief_describes_the_live_config(real_vault):
    """Generated, not hand-written, so it cannot drift from what it describes
    -- which is the failure this whole module exists to prevent."""
    from orchestrator.driver import EFFORT_CYCLE

    brief = capabilities.migration_brief()
    assert "maintenance/audit.md" in brief, "the mode->methodology map"
    assert "enter_faber" in brief, "MCP prompts are how identity ports"
    assert "git push" in brief, "the one denial worth carrying over"
    for level in EFFORT_CYCLE:
        assert f"`{level}`" in brief
    for section in ("## 1.", "## 5.", "## 9."):
        assert section in brief


def test_the_brief_carries_the_lessons_not_just_the_settings(real_vault):
    """A settings dump in one harness's schema is worthless to another. What
    ports is why each setting exists -- so the reader can find the nearest
    equivalent rather than the identical flag."""
    brief = capabilities.migration_brief()
    assert "Someone must answer" in brief, "unanswered prompts deny silently"
    assert "absolute" in brief, "a relative vault path resolves to the project"
    assert "refused tools" in brief, "silent turn vs caged turn"
