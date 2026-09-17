/* The arithmetic of the split: which slots share the screen with the shown
 * one, and how many columns that many take. */
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { Terminals, gridColumns, visibleWith, type Slot } from './Terminals'

const slot = (id: string, group?: string): Slot => ({ id, mode: 'faber', cwd: '/x', group })

describe('split arithmetic', () => {
  it('shows the shown slot alone unless it is grouped, then its whole group', () => {
    const slots = [slot('a', 'g'), slot('b', 'g'), slot('c'), slot('d', 'h'), slot('e', 'h')]
    expect(visibleWith(slots, slots[2]).map((s) => s.id)).toEqual(['c'])
    expect(visibleWith(slots, slots[0]).map((s) => s.id)).toEqual(['a', 'b'])
    expect(visibleWith(slots, slots[4]).map((s) => s.id)).toEqual(['d', 'e'])
    expect(visibleWith(slots, undefined)).toEqual([])
  })

  it('lays up to three in a row, then squares up to 3×3', () => {
    expect([1, 2, 3, 4, 5, 6, 7, 8, 9].map(gridColumns)).toEqual([1, 2, 3, 2, 3, 3, 3, 3, 3])
    // Rows follow: 4 → 2×2, 5–6 → 3×2, 7–9 → 3×3.
    expect(Math.ceil(4 / gridColumns(4))).toBe(2)
    expect(Math.ceil(6 / gridColumns(6))).toBe(2)
    expect(Math.ceil(9 / gridColumns(9))).toBe(3)
  })
})

/* The strip's directory label, which is the same fact the status bar shows.
 *
 * `slot.cwd` is fixed when a terminal is opened and never moves, so a session
 * that cd'd left the strip naming the old directory while the bar named the
 * new one: one fact on screen twice, disagreeing (found 2026-09-17). The
 * strip takes the bar's own value now, and these pin that it does. */
const shownIn = (shownCwd?: string) =>
  renderToStaticMarkup(
    <Terminals
      slots={[slot('t1')]} active="t1" accent="#fff" hidden={false} shownCwd={shownCwd}
      onSelect={() => {}} onClose={() => {}} onAdd={() => {}}
      onReorder={() => {}} onSplit={() => {}}
    />,
  ).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ')

describe('the terminal strip directory label', () => {
  it('shows where the session is, not where its terminal was opened', () => {
    const html = shownIn('~/Developer/second-brain')
    expect(html).toContain('~/Developer/second-brain')
    expect(html).not.toContain('/x')
  })

  it('falls back to the launch directory before the first report', () => {
    expect(shownIn(undefined)).toContain('/x')
  })
})
