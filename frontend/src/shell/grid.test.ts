import { describe, expect, it } from 'vitest'
import { buildGrid, cellTitle, compactTokens, iso } from './grid'

describe('the activity grid', () => {
  it('reads token counts short', () => {
    expect(compactTokens(950)).toBe('950')
    expect(compactTokens(48_200)).toBe('48.2K')
    expect(compactTokens(48_200_000)).toBe('48.2M')
    expect(compactTokens(2_904_000_000)).toBe('2.90B')
  })

  it("titles a cell with its sessions, its tokens when there were any, and its date", () => {
    const d = new Date(2026, 8, 29)
    expect(cellTitle(d, 3, 48_200_000)).toBe('3 sessions · 48.2M tokens · Sep 29 2026')
    expect(cellTitle(d, 1, 0)).toBe('1 session · Sep 29 2026')
    expect(cellTitle(d, 0, 2_100_000)).toBe('No sessions · 2.1M tokens · Sep 29 2026')
    expect(cellTitle(d, 0, 0)).toBe('No sessions · Sep 29 2026')
  })

  it('keys cells by local date, the way the backend sends days', () => {
    const today = new Date(2026, 8, 30)
    const weeks = buildGrid(today, new Map([['2026-09-29', 2]]))
    const cell = weeks.flat().find((c) => iso(c.date) === '2026-09-29')
    expect(cell?.count).toBe(2)
    expect(iso(new Date(2026, 0, 5))).toBe('2026-01-05')
  })
})
