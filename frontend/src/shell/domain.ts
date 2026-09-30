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

import { get, put } from './engine'

export type Mode = 'general' | 'faber' | 'noctua' | 'vesper' | 'maintenance'

export const MODE_ACCENT: Record<Mode, string> = {
  general: 'var(--color-ink-dim)',
  faber: 'var(--color-faber)',
  noctua: 'var(--color-noctua)',
  vesper: 'var(--color-vesper)',
  /* The signature, not its own orange (2026-09-17). Maintenance is not a
   * character: its persona was retired with v1 and what is left is a
   * nightly system function, so it is drawn in the hue the interface uses
   * for readings about itself rather than in one that implies somebody. */
  maintenance: 'var(--color-sig)',
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
  general: { blurb: 'Questions, comparisons, anything unscoped', model: 'opus-5.5' },
  faber: { blurb: 'Build: spec, implement, ship', model: 'opus-5.5' },
  noctua: { blurb: 'Learn: read closely, explain, retain', model: 'opus-5.5' },
  vesper: { blurb: 'Research: gather, weigh, return a verdict', model: 'opus-5.5' },
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

const VIEW_KEY = 'noctis.view'

/* Which rail item was showing when you left.
 *
 * The window opened on Repo, then on Terminal (2026-09-17), and both were
 * guesses about what you would want next. What you want next is what you
 * were doing, so it opens where you left it. A value that is no longer a
 * rail item (a tab removed between releases) falls back rather than
 * leaving the pane blank. */
export function rememberView(view: string): void {
  try {
    localStorage.setItem(VIEW_KEY, view)
  } catch {
    // A window that cannot remember it opens on the terminal, as before.
  }
}

export function recallView(known: readonly string[], fallback: string): string {
  try {
    const seen = localStorage.getItem(VIEW_KEY)
    return seen && known.includes(seen) ? seen : fallback
  } catch {
    return fallback
  }
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

/* Kept in two places since 2026-09-30: this window's localStorage, and the
 * backend (`/v2/sessions/arrangement`). localStorage belongs to one origin,
 * and the dev window (http://localhost:5180) and the packaged app
 * (tauri://localhost) are two, so the app's first launch would have opened
 * with no tabs. The backend copy is sent only when it changed: this runs on
 * every status-line report, every few seconds. */
let lastSent = ''

export function rememberSlots(
  slots: readonly RememberedSlot[],
  send: (slots: readonly RememberedSlot[]) => void = sendArrangement,
): void {
  const body = JSON.stringify(slots)
  try {
    localStorage.setItem(OPEN_SLOTS_KEY, body)
  } catch {
    // A window that cannot remember its arrangement still works.
  }
  if (body !== lastSent) {
    lastSent = body
    send(slots)
  }
}

function sendArrangement(slots: readonly RememberedSlot[]): void {
  // A copy that did not land is sent again on the next save, rather than
  // counted as sent: the backend may be restarting, or older than this page.
  void put('/v2/sessions/arrangement', slots).then((ok) => { if (!ok) lastSent = '' })
}

export function validSlots(parsed: unknown): RememberedSlot[] {
  if (!Array.isArray(parsed)) return []
  return parsed.filter(
    (t): t is RememberedSlot =>
      typeof t === 'object' && t !== null
      && typeof (t as RememberedSlot).mode === 'string'
      && typeof (t as RememberedSlot).cwd === 'string'
      && ((t as RememberedSlot).id === undefined || typeof (t as RememberedSlot).id === 'string'),
  )
}

export function recallSlots(): RememberedSlot[] {
  try {
    const raw = localStorage.getItem(OPEN_SLOTS_KEY)
    return raw ? validSlots(JSON.parse(raw)) : []
  } catch {
    return []
  }
}

/** The backend's copy, for a window whose own storage is empty. */
export async function recallSlotsFromBackend(): Promise<RememberedSlot[]> {
  const got = await get<{ slots: unknown }>('/v2/sessions/arrangement')
  return got ? validSlots(got.slots) : []
}

/* Which characters the strip shows, in order. Their *state* is not here:
 * it comes from the live sessions, because a hardcoded 'working' had Faber
 * lit with no Faber session running. */
export const CHARACTERS: { mode: Mode }[] = [
  { mode: 'faber' },
  { mode: 'noctua' },
  { mode: 'vesper' },
]


/* The reading column, in pixels, and the card that sits inside it.
 *
 * Stats and Settings centre their page in a 1050px column with the pane's
 * own 32px gutters inside it, so a card there is 986px wide. The Repo grid
 * reads CARD_WIDTH to cap itself a column at a time (see Panels' Repo):
 * one module is exactly a card, two are two of them side by side, and so
 * on. Here rather than inline in each view because the same number in three
 * files drifts, and the Repo cap is only right while it matches. */
export const PANE_COLUMN = 1050
export const PANE_GUTTER = 32
export const CARD_WIDTH = PANE_COLUMN - PANE_GUTTER * 2
