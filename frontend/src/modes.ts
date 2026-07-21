// Shared mode/character metadata — the one place World.tsx and
// ProfileOverlay.tsx both read from, so the mode->character mapping and
// accent colors can't drift between the two.
import type { Mode } from './api'

export interface ModeMeta {
  mode: Mode
  name: string
  accentVar: string
  // Busy/idle told through which expression is showing rather than a
  // separate status dot (Shayne's call, 2026-07-21 -- supersedes
  // Interface.md's original "ambient state indicators only, no
  // expression swapping in v1" scoping). Pulls from the expression set
  // extracted from the reference sheet; falls back to the base idle
  // sprite for characters without a clean pair for a given state.
  idleSprite: string
  busySprite: string
}

export const MODE_META: Record<Mode, ModeMeta> = {
  dev: { mode: 'dev', name: 'Faber', accentVar: '--faber', idleSprite: 'faber', busySprite: 'expressions/faber-hardhat' },
  learn: { mode: 'learn', name: 'Noctua', accentVar: '--noctua', idleSprite: 'expressions/noctua-sleepy', busySprite: 'noctua' },
  research: { mode: 'research', name: 'Vesper', accentVar: '--vesper', idleSprite: 'expressions/vesper-drowsy', busySprite: 'expressions/vesper-alert' },
  settings: { mode: 'settings', name: 'Custos', accentVar: '--custos', idleSprite: 'expressions/custos-sleepy', busySprite: 'expressions/custos-magnifier' },
  nightshift: { mode: 'nightshift', name: 'Echo', accentVar: '--echo', idleSprite: 'echo', busySprite: 'expressions/echo-alert' },
}

export const MODE_ORDER: Mode[] = ['dev', 'learn', 'research', 'settings', 'nightshift']
