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

/* The vault names modes by their folder -- dev, learn, research -- and the
 * shell by their character. An inbox item arrives with the vault's name;
 * this is how it gets its face. */
export const VAULT_MODE: Record<string, Mode> = {
  dev: 'faber', faber: 'faber',
  learn: 'noctua', noctua: 'noctua',
  research: 'vesper', vesper: 'vesper',
  maintenance: 'maintenance', settings: 'maintenance',
  general: 'general',
}

export const MODE_LABEL: Record<Mode, string> = {
  general: 'General',
  faber: 'Faber',
  noctua: 'Noctua',
  vesper: 'Vesper',
  maintenance: 'Maintenance',
}

/* What each mode is for, and the model it runs by default -- the launcher's
 * blurbs. The model is a fallback shown before the status line names the model actually
 * running. The engine is the authority — a duplicate that silently drifts is
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

/* Which terminals are open, so a reload brings them back.
 *
 * A terminal cannot survive a reload -- the PTY belongs to the window that
 * opened it -- but its *session* can: the engine's session id, learned from
 * the terminal's own status-line report, is what `--resume` takes. So the
 * arrangement is remembered as mode, directory and session id, and each
 * comes back resumed rather than blank.
 *
 * Written on every change rather than on unload: a crash or a force-quit
 * never fires unload, and those are exactly when losing it hurts. */
export interface RememberedSlot {
  mode: Mode
  cwd: string
  sessionId?: string
  /** The slot's own id. The PTY registry outlives the page and is keyed by
   *  this, so a slot that comes back under the same id can reattach to the
   *  session it had rather than resume a copy. Absent in older records,
   *  which come back with a fresh id and resume. */
  id?: string
  /** Slots sharing a group are shown side by side. */
  group?: string
}

const DISMISSED_REFUSAL_KEY = 'noctis.dismissed-refusal'

/* Which refusal you have already waved away.
 *
 * The banner is about an event, not a state: the engine refused a model at
 * a moment, and saying "I know" should hold. It was React state, so every
 * reload brought the same 21:51 back (2026-09-17). Keyed by the refusal's
 * own timestamp, so a *different* refusal still arrives: dismissing Fable's
 * says nothing about the next model to stop. */
export function rememberDismissedRefusal(at: string): void {
  try {
    localStorage.setItem(DISMISSED_REFUSAL_KEY, at)
  } catch {
    // A window that cannot remember it will ask again, which is survivable.
  }
}

export function recallDismissedRefusal(): string | null {
  try {
    return localStorage.getItem(DISMISSED_REFUSAL_KEY)
  } catch {
    return null
  }
}

const OPEN_SLOTS_KEY = 'noctis.open-slots'

export function rememberSlots(slots: readonly RememberedSlot[]): void {
  try {
    localStorage.setItem(OPEN_SLOTS_KEY, JSON.stringify(slots))
  } catch {
    // A window that cannot remember its arrangement still works.
  }
}

export function recallSlots(): RememberedSlot[] {
  try {
    const raw = localStorage.getItem(OPEN_SLOTS_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (t): t is RememberedSlot =>
        typeof t === 'object' && t !== null
        && typeof (t as RememberedSlot).mode === 'string'
        && typeof (t as RememberedSlot).cwd === 'string'
        && ((t as RememberedSlot).id === undefined || typeof (t as RememberedSlot).id === 'string'),
    )
  } catch {
    return []
  }
}

/* Which characters the strip shows, in order. Their *state* is not here:
 * it comes from the live sessions, because a hardcoded 'working' had Faber
 * lit with no Faber session running. */
export const CHARACTERS: { mode: Mode }[] = [
  { mode: 'faber' },
  { mode: 'noctua' },
  { mode: 'vesper' },
]

