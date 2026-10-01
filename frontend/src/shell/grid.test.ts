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

describe('token labels at a unit boundary', () => {
  it('moves up a unit instead of printing 1000.0', () => {
    expect(compactTokens(999_950)).toBe('1.0M')
    expect(compactTokens(999_960_000)).toBe('1.00B')
    expect(compactTokens(999_940)).toBe('999.9K')
  })
})

import { cardDate, dayStory, relativeDay, streakEnding } from './grid'

describe("the hover card's story", () => {
  const d = new Date(2026, 8, 29)

  it('names the character who did most, in a voice that is stable per day', () => {
    const story = dayStory(d, { faber: 4, general: 2, noctua: 1 })
    expect(story.lead).toBe('faber')
    expect(dayStory(d, { faber: 4, general: 2 }).line).toBe(story.line)   // same day, same words
    expect(dayStory(d, {}).lead).toBeNull()
    expect(['everyone slept', 'a quiet day', 'nobody home', 'the lights stayed off'])
      .toContain(dayStory(d, {}).line)
  })

  it('breaks a tie towards the build modes', () => {
    expect(dayStory(d, { general: 2, vesper: 2 }).lead).toBe('vesper')
  })

  it('counts a streak of real consecutive days ending on the day', () => {
    const s = new Map([['2026-09-27', 1], ['2026-09-28', 3], ['2026-09-29', 2], ['2026-09-25', 5]])
    expect(streakEnding(d, s)).toBe(3)
    expect(streakEnding(new Date(2026, 8, 26), s)).toBe(0)
  })

  it('says today and yesterday, and dates the rest', () => {
    const today = new Date(2026, 8, 30, 15, 0)
    expect(relativeDay(new Date(2026, 8, 30), today)).toBe('today')
    expect(relativeDay(d, today)).toBe('yesterday')
    expect(relativeDay(new Date(2026, 8, 1), today)).toBeNull()
    expect(cardDate(d)).toBe('Tue 29 Sep')
  })
})
