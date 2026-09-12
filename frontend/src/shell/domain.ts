/* Shared types and UI constants for the shell.
 *
 * This was mock.ts, and held the fake transcripts and status values the
 * screens were built against — dev.md §3.0 is explicit that screens come
 * first and only then does the UI's data shape become the API contract.
 * Every one of those values is now real, so what remains is the domain:
 * modes and their colours, block shapes, permission levels.
 *
 * Renamed because a file called mock.ts that holds no mocks is the same
 * stale signal as a hardcoded clock. Four of those shipped as bugs before
 * being caught — the frozen clock, a lit Faber light with no Faber session,
 * an activity grid measuring against a fixed date, and a status bar naming a
 * model the session was not running.
 */

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
/* The model here is a *fallback* only, shown before /v2/config answers.
 * The orchestrator is the authority — a duplicate that silently drifts is
 * how the status bar came to claim opus while the session ran sonnet. */
export const MODE_INFO: Record<Mode, { blurb: string; model: string; policy?: string }> = {
  general: { blurb: 'Questions, comparisons, anything unscoped', model: 'opus-5' },
  faber: { blurb: 'Build: spec, implement, ship', model: 'opus-5' },
  noctua: { blurb: 'Learn: read closely, explain, retain', model: 'opus-5' },
  vesper: { blurb: 'Research: gather, weigh, return a verdict', model: 'opus-5' },
  maintenance: {
    blurb: 'Audit the vault and propose repairs',
    model: 'haiku-4.5',
    /* "cannot edit" until 2026-09-12, when it could not: Edit and Write were
     * refused at spawn. The cage also stopped it reading a repo it was asked
     * to audit, so it went -- propose-only is its methodology now, not a
     * tool list, and the copy should not claim a guarantee the code no
     * longer makes. */
    policy: 'proposes only, by methodology',
  },
}

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
  /* A turn that ended without saying anything. It is a legal shape -- the
   * model runs tools, treats the last result as "still working", and the
   * turn stops -- but the transcript renders text, so it drew nothing, and
   * nothing looks identical to a dead backend, a session still thinking,
   * and a finished job. Rendering it makes those four states four pictures. */
  | { kind: 'silent'; tools: number; denials?: { tool: string; target: string }[] }
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
  /** 0-1 of the context window, from the last turn that reported one. */
  context?: number | null
  /** Epoch ms when the running turn began, null when nothing is running. */
  startedAt?: number | null
  /** One-line reminder of where a restored conversation left off. */
  recap?: string | null
  /** Per-session model override; the mode's default when absent. */
  model?: string
  /** The model the engine reported running. Authoritative, unlike the
   *  request — and unlike the session's own answer, since a model cannot
   *  introspect its weights. */
  ranModel?: string
  /** The last turn's duration and end time, for the line it leaves behind. */
  lastTurn?: { seconds: number; at: number } | null
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

/* How hard the engine thinks. This is what the composer's chip cycles now.
 *
 * It replaced the permission chip, and the swap is not cosmetic: every mode
 * spawns with the same tools and one shared allowlist, so the permission
 * mode changes little anyone would notice, while effort changes the answer.
 * `max` is a real level, left out of the cycle so it cannot be landed on by
 * tapping a key -- the same treatment bypassPermissions gets. */
export const EFFORT_CYCLE = ['low', 'medium', 'high', 'xhigh'] as const
export type Effort = (typeof EFFORT_CYCLE)[number]

export const EFFORT_LABEL: Record<Effort, string> = {
  low: 'low',
  medium: 'medium',
  high: 'high',
  xhigh: 'extra high',
}

/* Dim through the accent as the engine works harder. Deliberately the same
 * shape of scale as PERMISSION_TONE: all four are valid, none is a warning. */
export const EFFORT_TONE: Record<Effort, string> = {
  low: 'var(--color-ink-faint)',
  medium: 'var(--color-ink-dim)',
  high: 'var(--color-noctua)',
  xhigh: 'var(--color-faber)',
}

/* Which characters the strip shows, in order. Their *state* is not here:
 * it comes from the live sessions, because a hardcoded 'working' had Faber
 * lit with no Faber session running. */
export const CHARACTERS: { mode: Mode }[] = [
  { mode: 'faber' },
  { mode: 'noctua' },
  { mode: 'vesper' },
]

