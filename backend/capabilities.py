"""What a mode needs, what the harness provides, and the gap between them.

On 2026-09-11 it emerged that `dev.md` mandates seven tools -- Impeccable,
the code-review plugin, a Critic subagent, Playwright, shadcn MCP, Magic MCP,
CodeRabbit -- and a Noctis-launched Faber session could reach none of them.
The methodology had said so for months. Nothing checked, because nothing
could: a requirement written in prose and a capability installed in a config
root never meet.

So they meet here. A mode declares what its methodology assumes; the harness
reports what it actually has; `gaps()` is the difference, and it is the whole
point of the module. An instruction naming a tool the session cannot load is
not a strict instruction, it is a silent one.

**This is also what makes "workflow agnostic" mean something.** Portability
is not a promise that everything survives a move to another harness -- it
will not, because permissions, hooks and spawn flags are harness-specific by
nature. It is a promise that a move *tells you exactly what it costs*. Point
Noctis at a harness with no subagents and the answer should be "Faber loses
critic", printed at startup, not discovered three sessions later when a
review gate quietly does nothing.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# What each mode's methodology assumes it can reach.
#
# Declared here rather than in the vault deliberately. These are claims about
# *infrastructure*, not method, and the vault holds method -- putting a
# harness requirement in a mode file would make the methodology depend on
# what machine reads it. The names are the ones the methodology actually
# uses, so a reader can grep either direction.
REQUIRED: dict[str, set[str]] = {
    "faber": {
        "skill:impeccable",       # dev.md Stage 2 + 3.0, Live Mode iteration
        "skill:code-review",      # dev.md 3.3 review gates, Ship step 9
        "skill:security-review",  # dev.md Ship step 9
        "agent:critic",           # dev.md section 5, subagent roster
        "mcp:noctis",             # vault retrieval, every mode
        "tool:Bash", "tool:Edit", "tool:Write",
    },
    "noctua": {"agent:gap-finder", "agent:quizmaster", "mcp:noctis", "tool:Read"},
    "vesper": {"agent:credibility-checker", "agent:synthesizer",
               "mcp:noctis", "tool:WebSearch", "tool:Read"},
    "maintenance": {"mcp:noctis", "tool:Read"},
    "general": {"mcp:noctis", "tool:Read"},
}


@dataclass(frozen=True)
class Report:
    mode: str
    required: set[str]
    provided: set[str]

    @property
    def missing(self) -> set[str]:
        return self.required - self.provided

    @property
    def ok(self) -> bool:
        return not self.missing


def config_root() -> Path:
    """Where the harness actually reads its config from.

    Honours CLAUDE_CONFIG_DIR when something in the environment still sets
    it, because the point of this module is to report what is true rather
    than what the code intends. `build_env` strips it for spawns; a stray one
    here would otherwise make this probe describe a different machine than
    the sessions run on.
    """
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override) if override else Path.home() / ".claude"


def _plugins(root: Path) -> set[str]:
    """Plugin- and user-provided skills, as `skill:<name>`.

    Named loosely on purpose: `impeccable@impeccable` in settings and a
    `refero-design` directory on disk are both "the impeccable surface is
    here", and a strict match on either spelling would report a false gap.
    """
    found: set[str] = set()
    try:
        settings = json.loads((root / "settings.json").read_text())
    except (OSError, json.JSONDecodeError):
        settings = {}
    for entry in (settings.get("enabledPlugins") or {}):
        found.add(f"skill:{str(entry).split('@')[0]}")
    for d in (root / "skills", root / "plugins" / "marketplaces"):
        if d.is_dir():
            found |= {f"skill:{p.name}" for p in d.iterdir() if not p.name.startswith(".")}
    return found


def _builtin_skills() -> set[str]:
    """Skills the engine ships regardless of what is installed.

    Verified present on 2026-09-11 in a session run with user settings
    excluded, which is the only way to tell these apart from plugin ones.
    """
    return {"skill:code-review", "skill:security-review", "skill:simplify"}


def provided(mode: str) -> set[str]:
    """What this machine can actually give a session of `mode` right now."""
    from orchestrator.driver import ALL_TOOLS, mcp_config
    from orchestrator.modes import mode_agents

    have = _plugins(config_root()) | _builtin_skills()
    have |= {f"tool:{t}" for t in ALL_TOOLS.split() if not t.startswith("mcp__")}
    have |= {f"mcp:{name}" for name in json.loads(mcp_config())["mcpServers"]}
    if agents := mode_agents(mode):
        have |= {f"agent:{name}" for name in json.loads(agents)}
    return have


def report(mode: str) -> Report:
    return Report(mode=mode, required=REQUIRED.get(mode, set()), provided=provided(mode))


def report_all() -> list[Report]:
    return [report(m) for m in REQUIRED]


def render() -> str:
    """One block, for `make doctor` and for a human deciding whether a move
    to another harness is survivable."""
    lines = []
    for r in report_all():
        if r.ok:
            lines.append(f"{r.mode:12} ok    {len(r.required)} capabilities")
        else:
            lines.append(f"{r.mode:12} GAP   missing: {', '.join(sorted(r.missing))}")
    return "\n".join(lines)


if __name__ == "__main__":       # `python -m capabilities`
    print(render())
    raise SystemExit(0 if all(r.ok for r in report_all()) else 1)
