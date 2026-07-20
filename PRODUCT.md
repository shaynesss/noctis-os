# Product

## Register

product

## Users

Single user, single machine — Shayne, on his own Mac. No auth, no multi-tenancy. He's a developer/builder using this daily as the entry point into his own Claude Code work across five distinct kinds of session (Dev, Learn, Research, Settings, Nightshift).

## Product Purpose

Noctis OS makes mode-switching structural instead of manually held context. A persistent "world" screen shows five character sprites (one per mode) idling on a locked backdrop; each reflects that mode's live state at a glance. Clicking a character opens a profile overlay with that mode's real state (due items, current job, staged proposals) and a launch button that starts a Claude Code session with the right methodology file + working context preloaded, in that mode's designated launch surface (Terminal.app, tinted per character, or VS Code for Dev). Success = a fresh Mac running in under 10 minutes, every character's ambient state readable at a glance, and starting a session is a launcher action, never a manual context reload.

## Brand Personality

Pixel-art game world, not an admin panel. Flat chunky sprites (Faber the beaver/dev/warm red, Noctua the owl/learn/gold, Vesper the moth/research/purple, Custos the badger/settings/burnt orange, Echo the bat/nightshift/deep navy) idle on a peak-dusk cloud-bed backdrop — flat vector illustration, no gradients within any shape, ambient-only lighting, dark indigo-to-violet sky. Profile overlays lean retro-terminal: Press Start 2P header, JetBrains Mono body, typewriter-reveal entrance. Quiet and functional under the retro skin — this is a daily-driver launcher, not a showpiece; the game-world framing should never slow down "click character, see state, launch session."

## Anti-references

Generic SaaS dashboard patterns: card-grid layouts, gradient text, hero-metric tiles, tiny uppercase tracked eyebrows, numbered section markers. This is a game-world launcher, not an admin console — those patterns would fight the pixel-art register and are explicitly out.

## Design Principles

- Ambient state only, no new data — every badge/indicator is a rendering of state already tracked in the vault, never invented UI-only state.
- Fire-and-forget launching — the interface starts a session and reads back state via hooks/job-context files; it never tries to watch or control a running session live.
- One canonical source per asset class — sprite grid data and render script live only in `assets/characters/`, world plate + footing coordinates only in `assets/world/`; the frontend consumes generated output, never duplicates source data.
- Retro chrome, current substance — the pixel-art/terminal aesthetic is locked, but every card renders real, current backend state, not a mockup.
- Character color is a signal, not decoration — each character's locked hex is permanent chrome (launch button tint, Terminal.app window tint), consistent whether or not anything is currently happening.

## Accessibility & Inclusion

Standard practice: WCAG AA contrast on all text, `prefers-reduced-motion` alternative for the typewriter-reveal and any future animation. One open risk carried over from the locked Interface design, not yet resolved: Custos's three trigger badges (friction / accumulation / suspicion) currently signal lit/unlit by color alone with no separate glyph — worth a contrast/colorblind-safety pass when that component gets built, since color-only state signaling is a common a11y gap.
