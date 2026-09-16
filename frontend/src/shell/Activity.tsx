/* Contribution grid — Stage 2 item 3.
 *
 * One general grid, not per-mode. The mode split is already legible from the
 * tabs and the character strip, and a single grid answers the only question
 * this panel is really for: *am I actually using this?* — which is v1's
 * failure mode made visible.
 *
 * Ramp is Faber red rather than GitHub green: the Design Brief says the
 * character accents are the only chromatic events on screen, and most cells
 * sit near-black, so the grid reads as texture with occasional warm hits
 * rather than a slab of colour.
 *
 * Data will come from `store.daily_activity()` (sessions per day). Mocked
 * here per dev.md §3.0 — screens before wiring. */

import { buildGrid } from './grid'
import { Unreachable } from './Async'
import { Beam } from './Panels'

/** The heading, shared by the grid and by the two states that replace it, so
 *  the section does not vanish entirely while it is unavailable. */
function Frame({ children }: { children: React.ReactNode }) {
  return (
    <>
      <h2 className="m-0 mb-[14px] mt-7 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">
        Activity
      </h2>
      {children}
    </>
  )
}

// The empty cell is a fixed step *above* the card, not a fixed colour: the
// card is glass, so an opaque near-black cell sat darker than the surface
// on a light desktop and vanished into it on a dark one.
const LEVELS = ['rgba(255, 255, 255, 0.06)', 'var(--sig-ramp-1)', 'var(--sig-ramp-2)', 'var(--sig-ramp-3)', 'var(--sig-ramp-4)']
/** Count to swatch. The ramp is the signature (2026-09-15; it was Faber
 *  red, which made a day's count read as a Faber thing rather than a
 *  reading); the empty cell is a step above the page's own surface so
 *  quiet days recede rather than reading as a value. */
function level(count: number): string {
  if (count <= 0) return LEVELS[0]
  return LEVELS[Math.min(LEVELS.length - 1, count)]
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']



export function Activity(
  { days }: { days: { day: string; sessions: number }[] | null | false },
) {
  /* Absent data is not zero activity.
   *
   * This was handed `[]` while the request was still in flight or had
   * failed, so a year of real work rendered as "0 sessions in the last
   * year" — a measurement, stated confidently, of something that had not
   * been measured. It sat directly above a "Lifetime tokens" panel that
   * handled the same two states properly, which is what made it obvious.
   *
   * Neither state draws a grid: an empty grid *is* the zero reading. */
  if (days === false) return <Frame><Unreachable what="usage history" /></Frame>
  if (days === null) {
    return (
      <Frame>
        <div className="rounded-card border border-line bg-surface px-4 py-[13px] text-[12.5px] text-ink-faint">
          Loading…
        </div>
      </Frame>
    )
  }

  /* Real today, at local midnight.
   *
   * This was hardcoded to a fixed date from the mock era, and once the grid
   * took real data every session landed on a day the grid believed was in
   * the future -- where counts are forced to zero. The result was "0
   * sessions in the last year" sitting directly above the rows that proved
   * otherwise. Midnight, so a cell is a day rather than a moment. */
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const weeks = buildGrid(today, new Map(days.map((d) => [d.day, d.sessions])))
  const total = weeks.flat().reduce((n, c) => n + c.count, 0)

  // A month label sits above the first week that begins that month, which is
  // the only placement that stays aligned as the year rolls.
  const monthLabel = (w: number): string => {
    const first = weeks[w][0].date
    if (first.getDate() > 7) return ''
    if (w > 0 && weeks[w - 1][0].date.getMonth() === first.getMonth()) return ''
    return MONTHS[first.getMonth()]
  }

  return (
    <Frame>
      <Beam><div className="rounded-card border border-line bg-surface px-4 py-[14px]">
        <div className="mb-[14px] flex items-baseline gap-2">
          <b className="text-[14px] font-semibold text-ink tabular-nums">{total}</b>
          <span className="font-mono text-[10.5px] text-ink-faint">sessions in the last year</span>
        </div>

        {/* Wide content scrolls inside its own container so the app body never
            scrolls sideways. */}
        {/* The cells size from the card, not from a fixed 13px (2026-09-16):
            one column per week across the full width, each cell square, so
            the grid fills whatever width the card is given instead of
            leaving a third of it dark. The day labels share the grid's rows
            so they stay level with the cells at any size. */}
        <div className="grid grid-cols-[auto_1fr] gap-x-[7px] gap-y-[5px] font-mono text-[9px] text-ink-faint">
          <div />
          <div className="grid h-3" style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }}>
            {weeks.map((_, w) => (
              <span key={w} className="whitespace-nowrap">
                {monthLabel(w)}
              </span>
            ))}
          </div>

          <div className="grid grid-rows-[repeat(7,minmax(0,1fr))] items-center pr-px text-right">
            {['', 'Mon', '', 'Wed', '', 'Fri', ''].map((d, i) => (
              <span key={i}>{d}</span>
            ))}
          </div>
          <div className="grid grid-flow-col gap-[3px]"
               style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))`, gridTemplateRows: 'repeat(7, auto)' }}>
            {weeks.flatMap((col, w) =>
              col.map((c, d) => (
                <div
                  key={`${w}-${d}`}
                  title={`${c.count || 'No'} session${c.count === 1 ? '' : 's'} · ${c.date.toDateString().slice(4)}`}
                  className="aspect-square w-full rounded-[2px]"
                  style={{ background: level(c.count), visibility: c.future ? 'hidden' : undefined }}
                />
              )),
            )}
          </div>
        </div>
      </div></Beam>
    </Frame>
  )
}
