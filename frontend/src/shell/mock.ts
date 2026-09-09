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

/* What each mode is for, and what it actually runs. The model and tool
 * policy are not decoration: they are the difference between the modes, and
 * they are why a handoff has to open a new session rather than re-label a
 * live one -- a running `claude -p` cannot change either mid-flight.
 *
 * Mirrors MODE_MODELS and MODE_TOOLS in orchestrator/driver.py. Duplicated
 * here only while the shell is on mocks; item 3's wiring reads it from the
 * backend and this constant goes. */
export const MODE_INFO: Record<Mode, { blurb: string; model: string; policy?: string }> = {
  general: { blurb: 'Questions, comparisons, anything unscoped', model: 'opus-5' },
  faber: { blurb: 'Build: spec, implement, ship', model: 'opus-5' },
  noctua: { blurb: 'Learn: read closely, explain, retain', model: 'opus-5' },
  vesper: { blurb: 'Research: gather, weigh, return a verdict', model: 'opus-5' },
  maintenance: {
    blurb: 'Audit the vault and propose repairs',
    model: 'opus-5',
    policy: 'proposes only — cannot edit',
  },
}

/** Recent working directories. Real ones come from session history. */
export const CWD_RECENTS = [
  '~/Developer/noctis-os',
  '~/Developer/second-brain',
  '~/Developer/portfolio-platform',
]

export type Block =
  | { kind: 'user'; text: string; at: string }
  | { kind: 'text'; text: string }
  | { kind: 'thinking'; tokens: number; ms: number }
  /* `id` pairs a call with the result that arrives later -- results can be
   * interleaved with text and can land out of order, so they are matched by
   * id rather than by "the most recent tool block". */
  | { kind: 'tool'; id?: string; name: string; target: string; meta: string; body: string; open?: boolean }
  /* An engine failure belongs in the transcript, where the work was. A
   * toast would put it somewhere the session's own history does not record,
   * and a failed turn is exactly the thing you scroll back to find. */
  | { kind: 'error'; message: string; fatal: boolean }
  /* A handed-off session opens with its provenance rather than a blank
   * transcript, so a tab you return to an hour later says where it came
   * from instead of looking like something you started and forgot. */
  | { kind: 'handoff'; from: Mode; fromLabel: string; carried: string }

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
  /** Where the engine runs. Sent on every turn; the backend confines it. */
  cwd: string
  /** The engine's own id, learned from the first event. `--resume` takes
   *  it, so a turn without one starts a fresh session rather than
   *  continuing -- which is why it is stored per session, not per app. */
  engineId?: string
  /** A turn is in flight. The composer disables on it: a second prompt sent
   *  mid-turn would race the first rather than queue behind it. */
  busy?: boolean
  /** Live thinking-token estimate during a pause, null otherwise. */
  thinking?: number | null
}

/* The seed is now only what an empty install starts with: one General tab
 * and nothing in it. Real conversations are loaded from the backend on
 * than on a demo.
 *
 * TABS/SESSIONS below are the sample transcripts, no longer wired to the
 * app. They stay because the screens still need something to render when
 * working on them with no backend running -- import them in place of the
 * empty seed for that. */
export const EMPTY_TAB: Tab = { id: 't0', mode: 'general', label: 'General', pinned: true }
export const EMPTY_SESSION: SessionState = {
  mode: 'general', blocks: [], draft: '', cwd: '~/Developer/noctis-os',
}

export const TABS: Tab[] = [
  { id: 't0', mode: 'general', label: 'General', pinned: true },
  { id: 't1', mode: 'faber', label: 'Faber · noctis-os' },
  { id: 't2', mode: 'vesper', label: 'Vesper · mcp-servers' },
]

export const SESSIONS: Record<string, SessionState> = {
  t0: {
    cwd: '~/Developer/noctis-os',
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
    cwd: '~/Developer/noctis-os',
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
    cwd: '~/Developer/second-brain',
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
