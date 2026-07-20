// Shared mode/character metadata — the one place World.tsx and
// ProfileOverlay.tsx both read from, so the mode->character mapping and
// accent colors can't drift between the two.
import type { Mode } from './api'

export interface ModeMeta {
  mode: Mode
  name: string
  sprite: string
  accentVar: string
}

export const MODE_META: Record<Mode, ModeMeta> = {
  dev: { mode: 'dev', name: 'Faber', sprite: 'faber', accentVar: '--faber' },
  learn: { mode: 'learn', name: 'Noctua', sprite: 'noctua', accentVar: '--noctua' },
  research: { mode: 'research', name: 'Vesper', sprite: 'vesper', accentVar: '--vesper' },
  settings: { mode: 'settings', name: 'Custos', sprite: 'custos', accentVar: '--custos' },
  nightshift: { mode: 'nightshift', name: 'Echo', sprite: 'echo', accentVar: '--echo' },
}

export const MODE_ORDER: Mode[] = ['dev', 'learn', 'research', 'settings', 'nightshift']
