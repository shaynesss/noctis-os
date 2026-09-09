/* The contribution grid's date arithmetic.
 *
 * Named grid.ts, not activity.ts: on a case-insensitive filesystem that
 * collides with Activity.tsx and the wrong file wins the import. The same
 * mistake as markdown.ts beside Markdown.tsx, made twice in one afternoon —
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
 * matched on local YYYY-MM-DD, which is what SQLite's date() produces and
 * what the person looking at the grid means by "that day".
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

/** Local YYYY-MM-DD. `toISOString` would shift the date across a timezone
 *  boundary and put a late-evening session on the following day. */
function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
