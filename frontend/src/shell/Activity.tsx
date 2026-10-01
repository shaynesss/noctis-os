/* Contribution grid, Stage 2 item 3.
 *
 * One general grid, not per-mode. The mode split is already legible from the
 * tabs and the character strip, and a single grid answers the only question
 * this panel is really for: *am I actually using this?*, which is v1's
 * failure mode made visible.
 *
 * The ramp is the signature (since 2026-09-15; it began as Faber red), and
 * most cells sit near-black, so the grid reads as texture with occasional
 * warm hits rather than a slab of colour.
 *
 * Real data: sessions per local day from `store.daily_activity()` and each
 * day's tokens from the transcripts, both through `/v2/sessions/stats`. A
 * cell's hover names both (2026-09-30). */

import { useRef, useState } from 'react'
import { buildGrid, cellTitle, compactTokens, iso, streakEnding } from './grid'
import { DayCard } from './DayCard'
import type { Mode } from './domain'
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



/** Which cell the card is about, and the element it is anchored to. */
type Hover = { w: number; d: number }

export function Activity(
  { days }: { days: { day: string; sessions: number; tokens?: number; modes?: Partial<Record<Mode, number>> }[] | null | false },
) {
  const [hover, setHover] = useState<Hover | null>(null)
  const cells = useRef(new Map<string, HTMLDivElement>())
  /* Absent data is not zero activity.
   *
   * This was handed `[]` while the request was still in flight or had
   * failed, so a year of real work rendered as "0 sessions in the last
   * year" -- a measurement, stated confidently, of something that had not
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
  // Tokens by day, for the hover (2026-09-30). Colour stays by sessions: a
  // day's tokens are mostly cache re-reads, which grow with how long a
  // conversation is rather than with how much happened in it.
  const tokens = new Map(days.map((d) => [d.day, d.tokens ?? 0]))
  const yearTokens = weeks.flat().reduce((n, c) => n + (c.future ? 0 : tokens.get(iso(c.date)) ?? 0), 0)
  const modes = new Map(days.map((d) => [d.day, d.modes ?? {}]))
  const sessionsByDay = new Map(days.map((d) => [d.day, d.sessions]))
  const maxTokens = weeks.flat().reduce((n, c) => Math.max(n, c.future ? 0 : tokens.get(iso(c.date)) ?? 0), 0)

  /* The card for the hovered (or keyboard-focused) day, measured from the
   * cell itself so it sits on it whatever the grid's size. */
  const hovered = hover && weeks[hover.w]?.[hover.d]
  const anchor = hover && cells.current.get(`${hover.w}-${hover.d}`)?.getBoundingClientRect()
  const card = hovered && !hovered.future && anchor ? {
    date: hovered.date,
    sessions: hovered.count,
    tokens: tokens.get(iso(hovered.date)) ?? 0,
    modes: modes.get(iso(hovered.date)) ?? {},
    maxTokens,
    streak: streakEnding(hovered.date, sessionsByDay),
    anchor,
  } : null

  /* Arrow keys walk the grid: left and right a week, up and down a day.
   * Focus lands on today, the day you most likely want. */
  const lastWeek = weeks.length - 1
  const todayIndex = weeks[lastWeek].findIndex((c) => iso(c.date) === iso(today))
  const move = (dw: number, dd: number) => setHover((h) => {
    const at = h ?? { w: lastWeek, d: Math.max(0, todayIndex) }
    let w = at.w + dw, d = at.d + dd
    if (d < 0) { w -= 1; d = 6 } else if (d > 6) { w += 1; d = 0 }
    w = Math.max(0, Math.min(lastWeek, w))
    return weeks[w]?.[d]?.future ? at : { w, d }
  })
  const onKey = (e: React.KeyboardEvent) => {
    const step: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }
    if (step[e.key]) { e.preventDefault(); move(...step[e.key]) }
    if (e.key === 'Escape') setHover(null)
  }

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
          <span className="font-mono text-[10.5px] text-ink-faint">
            sessions in the last year{yearTokens ? ` · ${compactTokens(yearTokens)} tokens` : ''}
          </span>
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
          <div className="grid grid-flow-col gap-[3px] rounded-[3px] outline-none focus-visible:ring-1 focus-visible:ring-[var(--color-sig-5)]"
               tabIndex={0}
               aria-label={`Activity: ${total} sessions in the last year. Arrow keys move between days.`}
               onPointerLeave={() => setHover(null)}
               onFocus={() => setHover((h) => h ?? { w: lastWeek, d: Math.max(0, todayIndex) })}
               onBlur={() => setHover(null)}
               onKeyDown={onKey}
               style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))`, gridTemplateRows: 'repeat(7, auto)' }}>
            {weeks.flatMap((col, w) =>
              col.map((c, d) => (
                <div
                  key={`${w}-${d}`}
                  ref={(el) => { if (el) cells.current.set(`${w}-${d}`, el); else cells.current.delete(`${w}-${d}`) }}
                  aria-label={cellTitle(c.date, c.count, tokens.get(iso(c.date)) ?? 0)}
                  onPointerEnter={() => { if (!c.future) setHover({ w, d }) }}
                  className="aspect-square w-full rounded-[2px] transition-[box-shadow,filter] duration-100"
                  style={{
                    background: level(c.count),
                    visibility: c.future ? 'hidden' : undefined,
                    // The day being read: a ring in the signature, lifted a
                    // touch, so the eye can find the cell the card is about.
                    ...(hover && hover.w === w && hover.d === d
                      ? { boxShadow: '0 0 0 1px var(--color-sig-6), 0 0 8px rgba(222,119,138,0.45)', filter: 'brightness(1.25)' }
                      : {}),
                  }}
                />
              )),
            )}
          </div>
        </div>
      </div></Beam>
      {card && <DayCard day={card} today={today} />}
    </Frame>
  )
}
