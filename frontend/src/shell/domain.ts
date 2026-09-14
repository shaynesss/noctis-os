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
  | { kind: 'silent'; tools: number; spoke?: boolean; truncated?: boolean
      denials?: { tool: string; target: string }[] }
  /* A handed-off session opens with its provenance rather than a blank
   * transcript, so a tab you return to an hour later says where it came
   * from instead of looking like something you started and forgot. */
  | { kind: 'handoff'; from: Mode; fromLabel: string; carried: string }

/* A tab label that is not already taken.
 *
 * Two sessions of one mode on one directory are an ordinary thing to want --
 * two angles on the same repository -- and both would otherwise read
 * `Faber · noctis-os`, which makes the tab bar a guessing game. The suffix
 * only appears on the second and later, so the common case is unchanged.
 */
export function uniqueLabel(base: string, taken: readonly string[]): string {
  if (!taken.includes(base)) return base
  for (let n = 2; ; n++) {
    const candidate = `${base} (${n})`
    if (!taken.includes(candidate)) return candidate
  }
}

/* Apply a patch to one entry of a keyed map, or drop it if the entry is gone.
 *
 * The shape every session updater needs. A tab can be closed while its turn
 * is still unwinding -- the close deletes the session and aborts the stream,
 * but the abort resolves a tick later, so the stream's updaters and its
 * `finally` both still run against an entry that no longer exists.
 *
 * TypeScript cannot catch that: indexing a `Record<string, T>` is typed as
 * always present unless `noUncheckedIndexedAccess` is on. The guard has to be
 * written rather than inferred, which is why it lives here with a test on it
 * instead of being re-remembered at each call site. */
export function patchEntry<T>(
  map: Record<string, T>,
  key: string,
  patch: (prev: T) => T,
): Record<string, T> {
  return map[key] ? { ...map, [key]: patch(map[key]) } : map
}

/* The tabs that were open, remembered across a reload.
 *
 * Restore used to fetch "General plus the single most recent other session",
 * which was exactly right while the shell held exactly two tabs and wrong the
 * moment it could hold nine: open five, reload, get two back. Nothing
 * recorded the arrangement, so nothing could restore it.
 *
 * Kept per-viewer in localStorage rather than in the vault or the history
 * database. Which tabs you had open is not knowledge and not application
 * state either -- it is where this window was pointed, and it should not
 * follow you to another machine.
 *
 * Every read and write is wrapped: storage throws outright in a private
 * window and in some embedded contexts, and losing the arrangement is a far
 * smaller failure than refusing to start. */

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

export const EFFORT_CYCLE = ['low', 'medium', 'high', 'xhigh'] as const
export type Effort = (typeof EFFORT_CYCLE)[number]

/* What a tab runs at before anyone touches the chip. `high` because that is
 * what dev.md asks for -- "default high; medium/low for mechanical or
 * repetitive work" -- and because a default that quietly costs less is the
 * kind of thing nobody notices is wrong. */
export const DEFAULT_EFFORT: Effort = 'high'

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

