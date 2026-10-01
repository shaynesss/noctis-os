/* The contribution grid's date arithmetic.
 *
 * Named grid.ts, not activity.ts: on a case-insensitive filesystem that
 * collides with Activity.tsx and the wrong file wins the import. The same
 * mistake as markdown.ts beside Markdown.tsx, made twice in one afternoon:
 * a lowercase sibling of a component file is the trap.
 *
 * Its own module because this is where the bug was: the component held a
 * hardcoded `today`, so every real session landed on a day the grid thought
 * was in the future, where counts are forced to zero -- "0 sessions in the
 * last year" printed directly above the rows that disproved it. Out here it
 * is testable without a DOM.
 */

export const WEEKS = 53

export interface Cell {
  date: Date
  count: number
  future: boolean
}

/** The 53-week grid, filled from real per-day session counts.
 *
 * Only days with activity come from the backend, so the grid supplies the
 * gaps rather than the payload carrying 365 mostly-zero rows. Dates are
 * matched on local YYYY-MM-DD, which is what the backend sends
 * (`date(started_at, 'localtime')` since 2026-09-29; plain SQLite date() is
 * the UTC day, which this comment used to claim was local) and what the
 * person looking at the grid means by "that day".
 */
export function buildGrid(today: Date, counts: Map<string, number>): Cell[][] {
  const start = new Date(today)
  start.setDate(start.getDate() - 364 - today.getDay())

  const weeks: Cell[][] = []
  for (let w = 0; w < WEEKS; w++) {
    const col: Cell[] = []
    for (let d = 0; d < 7; d++) {
      const date = new Date(start)
      date.setDate(date.getDate() + w * 7 + d)
      const future = date > today
      col.push({ date, future, count: future ? 0 : (counts.get(iso(date)) ?? 0) })
    }
    weeks.push(col)
  }
  return weeks
}

/** A token count the way the hover reads it: 950, 48.2K, 48.2M, 2.90B. */
export function compactTokens(n: number): string {
  if (n < 1_000) return String(n)
  // The unit is chosen after rounding, or 999,950 read "1000.0K".
  const k = Number((n / 1_000).toFixed(1))
  if (k < 1_000) return `${k.toFixed(1)}K`
  const m = Number((n / 1_000_000).toFixed(1))
  if (m < 1_000) return `${m.toFixed(1)}M`
  return `${(n / 1_000_000_000).toFixed(2)}B`
}

/** One cell's hover: sessions, then tokens when there were any, then the
 *  date. "Sep 29" style, the way the month labels read. */
export function cellTitle(date: Date, sessions: number, tokens: number): string {
  const s = `${sessions || 'No'} session${sessions === 1 ? '' : 's'}`
  const t = tokens ? ` · ${compactTokens(tokens)} tokens` : ''
  return `${s}${t} · ${date.toDateString().slice(4)}`
}

/** Local YYYY-MM-DD. `toISOString` would shift the date across a timezone
 *  boundary and put a late-evening session on the following day. */
export function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/* ── The hover card's story (2026-10-01) ───────────────────────────────────
 * Whimsy from the data, never invented: the line names the character who
 * did most that day, a streak counts real consecutive days, and a quiet day
 * says so. Each day keeps its own wording (picked by the date, not at
 * random), so a day reads the same every time you look at it, and
 * neighbouring days read differently. */

type CardMode = 'general' | 'faber' | 'noctua' | 'vesper' | 'maintenance'

const VOICE: Record<CardMode | 'quiet', string[]> = {
  faber: ['Faber built all day', 'Faber had the tools out', 'a building day', 'Faber, mid-build'],
  noctua: ['Noctua hit the books', 'Noctua read late', 'a studying day', 'Noctua, taking notes'],
  vesper: ['Vesper went digging', 'Vesper chased a question', 'a research day', 'Vesper, on the trail'],
  maintenance: ['the night crew swept up', 'a tidying day', 'Maintenance did the rounds'],
  general: ['a bit of everything', 'a general sort of day', 'odds and ends'],
  quiet: ['everyone slept', 'a quiet day', 'nobody home', 'the lights stayed off'],
}

const pick = (options: string[], date: Date) =>
  options[(date.getFullYear() * 372 + date.getMonth() * 31 + date.getDate()) % options.length]

/** Who worked most that day, and a line in their voice. A tie goes to the
 *  build modes first, then General, which is where the work was. */
export function dayStory(date: Date, modes: Partial<Record<string, number>>): { lead: CardMode | null; line: string } {
  const order: CardMode[] = ['faber', 'noctua', 'vesper', 'maintenance', 'general']
  let lead: CardMode | null = null
  for (const m of order) {
    if ((modes[m] ?? 0) > (lead ? modes[lead] ?? 0 : 0)) lead = m
  }
  return { lead, line: pick(VOICE[lead ?? 'quiet'], date) }
}

/** Consecutive days with a session, ending on `date`; 0 if that day had none. */
export function streakEnding(date: Date, sessions: Map<string, number>): number {
  let n = 0
  const d = new Date(date)
  while ((sessions.get(iso(d)) ?? 0) > 0) {
    n += 1
    d.setDate(d.getDate() - 1)
  }
  return n
}

/** "today" / "yesterday", or null for any other day. */
export function relativeDay(date: Date, today: Date): 'today' | 'yesterday' | null {
  const a = new Date(date); a.setHours(0, 0, 0, 0)
  const b = new Date(today); b.setHours(0, 0, 0, 0)
  const days = Math.round((b.getTime() - a.getTime()) / 86_400_000)
  return days === 0 ? 'today' : days === 1 ? 'yesterday' : null
}

/** "Tue 29 Sep": weekday, day, month, the way the grid's labels read. */
export function cardDate(date: Date): string {
  const wd = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][date.getDay()]
  const mo = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][date.getMonth()]
  return `${wd} ${date.getDate()} ${mo}`
}
