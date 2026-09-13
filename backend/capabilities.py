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
    from engine import ALL_TOOLS, mcp_config
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




# --------------------------------------------------------------- migration

def migration_brief() -> str:
    """Everything Tier 3, written as intent rather than as Claude Code syntax.

    Tier 3 is the part that does not port: permissions, hooks, spawn flags,
    event-stream shape. The instinct is to treat that as a loss and move on.
    The better move is to write it down in a form the *next* harness can act
    on -- an agent in Cursor or Codex reads this and sets up the nearest
    equivalent, or says plainly which parts it cannot.

    So this is deliberately not a config file. A config file in one harness's
    schema is worthless to another; a statement of what the configuration is
    *for* is not. Each item says what it does and why, because a harness with
    no `--effort` still has some notion of how hard to think, and only the
    reason tells you what to reach for.

    Generated rather than hand-written so it cannot drift from the code it
    describes -- the failure this whole module exists to prevent.
    """
    from engine import (ALL_TOOLS, EFFORT_CYCLE, MODE_MODELS,
                        PERMISSION_CYCLE, mcp_config, settings_config)
    from jobs import methodology_path

    policy = json.loads(settings_config())
    allow = policy["permissions"]["allow"]
    deny = policy["permissions"].get("deny", [])
    tools = [t for t in ALL_TOOLS.split() if not t.startswith("mcp__")]

    out = [
        "# Noctis — harness migration brief",
        "",
        "Generated by `python -m capabilities --migrate`. Everything here is",
        "**Tier 3**: configuration that does not port between harnesses. Tiers 1",
        "and 2 need no instructions — the methodology is markdown in the vault,",
        "and retrieval plus mode-loading travel over MCP.",
        "",
        "Read this as *intent*, not as settings to copy. Reproduce what you can,",
        "and say plainly what you cannot: a gap that is named costs a sentence,",
        "and a gap that is silent costs a session.",
        "",
        "## 1. Connect the MCP server first",
        "",
        "This is the whole of Tiers 1 and 2 and it is already portable.",
        "",
        "```json",
        json.dumps(json.loads(mcp_config()), indent=2),
        "```",
        "",
        "It serves `tools/*` — `vault_search`, `history_search`, `job_context`,",
        "`worklist`, `propose` — and, importantly, `prompts/*`: `enter_faber`,",
        "`enter_noctua`, `enter_vesper`, `enter_maintenance`. Those load a mode's",
        "methodology and job context. If the harness speaks MCP prompts, mode",
        "switching already works and most of what follows is refinement.",
        "",
        "## 2. Identity per session",
        "",
        "Each session is one mode, and the mode is passed in, never inherited",
        "from the machine. Do not put a mode's methodology in a global config",
        "file: that made the machine itself Faber and leaked the build process",
        "into every other mode (2026-09-11).",
        "",
        "| Mode | Default model | Methodology |",
        "|---|---|---|",
    ]
    for mode, model in MODE_MODELS.items():
        out.append(f"| `{mode}` | {model} | `{methodology_path(mode) or '— (no method)'}` |")
    out += [
        "",
        "Compose as: universal prompt (`prompts/system.md`) + the mode overlay",
        "(`prompts/overlays/<mode>.md`) + the current job's context. Inject it as",
        "a system-level instruction if the harness has one, and as a preamble to",
        "the first message if it does not.",
        "",
        "## 3. Permissions",
        "",
        "Every mode gets the **same** tool surface. Capability is not the axis the",
        "modes vary on — methodology is. A mode handed work it cannot perform ends",
        "its turn with nothing done and no way to say so.",
        "",
        f"Pre-approved, no prompting: `{'`, `'.join(allow)}`",
        "",
        f"Denied outright: `{'`, `'.join(deny) or '— none'}`",
        "",
        "`git push` is denied as a fact rather than a rule in a document, because",
        "pushing is the one action the author reserves. If the harness cannot deny",
        "a single command, deny the tool and say so.",
        "",
        f"Tools expected: `{'`, `'.join(tools)}`",
        "",
        "## 4. Effort",
        "",
        f"Levels used: `{'`, `'.join(EFFORT_CYCLE)}`, default `high`.",
        "",
        "High by default; medium or low for mechanical work; the top level for",
        "genuine deep exploration. If the harness has no effort control, map it to",
        "model choice — a smaller model for mechanical work — and record that this",
        "is a substitution rather than the real thing.",
        "",
        "## 5. Permission prompting",
        "",
        f"Modes offered: `{'`, `'.join(PERMISSION_CYCLE)}`.",
        "",
        "**Someone must answer.** A harness that emits a permission request with",
        "no handler attached denies it silently, and the session then ends having",
        "done nothing with nothing to report. If prompts cannot be answered, set",
        "the policy to allow-listed-and-never-ask rather than leaving requests",
        "unanswered.",
        "",
        "## 6. Telemetry hooks",
        "",
        "Two, both non-blocking, both fed the mode via a `NOCTIS_MODE` environment",
        "variable:",
        "",
        "- **after each tool call** → `backend/hooks/log_action.py` (the action feed)",
        "- **at session end** → `backend/hooks/mark_session_end.py` (clears the busy flag)",
        "",
        "If the harness has no hooks, the interface loses live activity and stale",
        "sessions stop being flagged. Degraded, not broken — say so rather than",
        "faking it.",
        "",
        "## 7. Turn events the interface needs",
        "",
        "Parsed from the engine's stream into `orchestrator/events.py`. A new",
        "harness needs a parser producing the same shapes.",
        "",
        "Required: session id (for resume), assistant text, tool calls and results,",
        "token usage, and **turn end carrying the turn's text length, tool count",
        "and any refused tools**. That last one is not optional: a turn ending with",
        "tool calls and no text renders as a blank screen indistinguishable from a",
        "crash, and the refusals are what tell a caged session apart from a quiet",
        "one.",
        "",
        "## 8. Working directories",
        "",
        "The session's project, plus the vault as a second readable root. State the",
        "vault's **absolute** path in the prompt: a relative `second-brain/`",
        "resolves against the project and a live session duly reported the vault",
        "missing while reading it through MCP.",
        "",
        "## 9. Check yourself",
        "",
        "Run `python -m capabilities` against the new harness. It prints, per mode,",
        "what the methodology assumes and what is actually reachable. Anything under",
        "`GAP` is a capability the mode's own instructions reference and the session",
        "cannot use — fix it or amend the methodology, but do not leave it.",
        "",
    ]
    return "\n".join(out)


if __name__ == "__main__":       # `python -m capabilities [--migrate]`
    import sys
    if "--migrate" in sys.argv:
        print(migration_brief())
        raise SystemExit(0)
    print(render())
    raise SystemExit(0 if all(r.ok for r in report_all()) else 1)
