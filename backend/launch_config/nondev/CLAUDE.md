# CLAUDE.md — Universal (non-dev Noctis modes)

Loaded only for Learn, Research, Settings, and Nightshift sessions — the launcher sets `CLAUDE_CONFIG_DIR` to this directory for those launches specifically. Dev-mode sessions and any ad hoc terminal use in Shayne's other projects read the default `~/.claude/CLAUDE.md` (`second-brain/modes/dev/dev.md`) instead; this file is deliberately not that, and deliberately not a copy of it.

The active mode's own methodology (`second-brain/modes/<name>/<name>.md`) and working context are injected into the session's initial prompt by the launcher, exactly as already specified in the interface's launch action. This file supplies only what's true across every mode, not anything mode-specific or dev-specific.

## Vault

- Vault root: `second-brain/`. Schema and write discipline live in `second-brain/CLAUDE.md` — read it before writing to `wiki/`.
- State vs. knowledge: durable reasoning goes in `wiki/`; volatile state goes in the mode's own `state.md`, `lessons.md`, and `jobs/<slug>/context.md` — never in wiki pages.
- Verify after every vault write: re-read the modified region, check for duplicate headings or fused lines, before considering the write complete.

## Communication

- Short status updates between major steps. Flag blockers immediately rather than silently working around them.
- Surface assumptions and ambiguity rather than resolving them silently — every mode carries some form of the Confusion Protocol; the specific wording for this mode lives in its own methodology file, not here.
- Paste-ready output over long explanation, unless asked.

## Session close

- Append to this mode's `lessons.md` before ending any substantive session — no gate, no format beyond a plain entry. This is the inner improvement loop (see Improvement Loops in the vault); skipping it is the one thing that silently breaks the two-tier evolution design.
