/* The arithmetic of the split: which slots share the screen with the shown
 * one, and how many columns that many take. */
import { describe, expect, it } from 'vitest'
import { gridColumns, visibleWith, type Slot } from './Terminals'

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
