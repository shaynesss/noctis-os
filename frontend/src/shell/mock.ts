/* Mocked data — Noctis v2 Stage 2 item 3.
 *
 * dev.md §3.0 is explicit that screens get built against fake data first,
 * and only once approved does the UI's data shape become the API contract,
 * never the reverse. So these types are the proposal: the backend's
 * Event/Usage/Limits dataclasses already match, and where they don't, this
 * file is what moves.
 *
 * Content is real work rather than lorem, because placeholder text hides
 * exactly the layout problems a transcript has — long tool paths, a wall of
 * prose, a collapsed block next to an expanded one. */

export type Mode = 'general' | 'faber' | 'noctua' | 'vesper' | 'maintenance'

export const MODE_ACCENT: Record<Mode, string> = {
  general: 'var(--color-ink-dim)',
  faber: 'var(--color-faber)',
  noctua: 'var(--color-noctua)',
  vesper: 'var(--color-vesper)',
  maintenance: 'var(--color-maint)',
}

export const MODE_LABEL: Record<Mode, string> = {
  general: 'General',
  faber: 'Faber',
  noctua: 'Noctua',
  vesper: 'Vesper',
  maintenance: 'Maintenance',
}

export type Block =
  | { kind: 'user'; text: string; at: string }
  | { kind: 'text'; text: string }
  | { kind: 'thinking'; tokens: number; ms: number }
  | { kind: 'tool'; name: string; target: string; meta: string; body: string; open?: boolean }

export interface Tab {
  id: string
  mode: Mode
  label: string
  pinned?: boolean
}

export interface SessionState {
  mode: Mode
  blocks: Block[]
  draft: string
}

export const TABS: Tab[] = [
  { id: 't0', mode: 'general', label: 'General', pinned: true },
  { id: 't1', mode: 'faber', label: 'Faber · noctis-os' },
  { id: 't2', mode: 'vesper', label: 'Vesper · mcp-servers' },
]

export const SESSIONS: Record<string, SessionState> = {
  t0: {
    mode: 'general',
    blocks: [
      { kind: 'user', text: 'can you compare postgres and sqlite for the history store', at: '12:02' },
      {
        kind: 'text',
        text:
          'This is research — hand off to **Vesper**? If you\'d rather stay here, tell me the ' +
          'access pattern and I\'ll take a run at it.',
      },
    ],
    draft: '',
  },
  t1: {
    mode: 'faber',
    blocks: [
      { kind: 'user', text: 'start stage 1 item 3 — the mode merge', at: '12:19' },
      { kind: 'thinking', tokens: 206, ms: 4200 },
      {
        kind: 'tool',
        name: 'vault_search',
        target: '"mode methodology structure"',
        meta: '4 hits · 31ms',
        open: true,
        body:
          'modes/dev/dev.md                 bm25 −8.42\n' +
          'wiki/Noctis OS/Modes.md          bm25 −7.91\n' +
          'modes/settings/settings.md       bm25 −7.10\n' +
          'modes/nightshift/nightshift.md   bm25 −6.88',
      },
      {
        kind: 'tool',
        name: 'Read',
        target: 'modes/settings/settings.md',
        meta: '218 lines',
        body: 'Custos — audit → propose → apply, propose-never-commit.\nOwns: methodology diffs, trigger thresholds, the proposal inbox.',
      },
      {
        kind: 'tool',
        name: 'job_context',
        target: 'read · noctis-os',
        meta: 'ok',
        body: 'stage: Build · track: Overhaul\nNext: Stage 1 item 3 — mode merge, by hand.',
      },
      {
        kind: 'text',
        text:
          'Both files are read. The split is cleaner than the spec implies — Custos and Nightshift ' +
          'barely overlap: `settings.md` owns the *judgement* half, `nightshift.md` the ' +
          '*scheduling* half.\n\nSo `maintenance/` takes both, but as two files rather than one. ' +
          'Merging them would lose the propose-never-commit boundary that exists *because* they ' +
          'were separate.\n\nFlagging that as a deviation before I write anything — the spec says ' +
          '"collapsed into `maintenance/`", which I read as one directory, not one file. Confirm?',
      },
    ],
    draft:
      'yes — two files. but call them audit.md and schedule.md so the split is obvious from the filename alone',
  },
  t2: {
    mode: 'vesper',
    blocks: [
      { kind: 'user', text: 'which mcp servers are worth adopting for the vault?', at: '09:41' },
      { kind: 'thinking', tokens: 512, ms: 8100 },
      { kind: 'text', text: 'Two candidates left unscored — I paused mid-comparison. Want me to finish?' },
    ],
    draft: '',
  },
}

/* Mirrors orchestrator/driver.py's PERMISSION_CYCLE. bypassPermissions is
 * deliberately absent: it stays a settable flag but must not be reachable by
 * tapping a key. Order escalates -- each step lets a session do more without
 * asking -- so cycling forward is always the direction that grants, which is
 * the direction worth being deliberate about. */
export const PERMISSION_CYCLE = ['plan', 'manual', 'acceptEdits', 'auto'] as const
export type Permission = (typeof PERMISSION_CYCLE)[number]

export const PERMISSION_LABEL: Record<Permission, string> = {
  plan: 'plan only',
  manual: 'ask each time',
  acceptEdits: 'auto-accept edits',
  auto: 'auto',
}

/* Escalating: green through amber to the accent, so the permissive end of
 * the cycle reads as warmer without being alarming -- these are all valid
 * states, not warnings. */
export const PERMISSION_TONE: Record<Permission, string> = {
  plan: 'var(--color-good)',
  manual: 'var(--color-ink-dim)',
  acceptEdits: 'var(--color-noctua)',
  auto: 'var(--color-faber)',
}

export const CHARACTERS: { mode: Mode; state: 'working' | 'idle' }[] = [
  { mode: 'faber', state: 'working' },
  { mode: 'noctua', state: 'idle' },
  { mode: 'vesper', state: 'idle' },
]

export const STATUS = {
  cwd: '~/Developer/noctis-os',
  branch: 'main',
  model: 'Opus 5',
  clock: '12:23',
  contextPct: 41,
  fiveHourPct: 20,
  fiveHourResets: '3h44m',
  sevenDayPct: 24,
}

export const USAGE = {
  windows: [
    { label: 'Current session', sub: '5h window · resets in 3h 44m', pct: 20 },
    { label: 'Weekly · all models', sub: 'resets in 2d 6h', pct: 24 },
  ],
  lifetime: { total: '950.5M', since: '9 May 2026', input: 8.4, output: 4.1, cacheRead: 892.0, cacheWrite: 46.0 },
}
