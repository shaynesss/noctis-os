/* The nightshift line and the relative-date label: sentences composed from
 * counts, held to the string. (The digest these came from is gone; the
 * line lives on in Settings' Maintenance section.) */
import { describe, expect, it } from 'vitest'
import { nightshiftLine, sinceLabel } from './Panels'

describe('nightshiftLine', () => {
  const at = new Date(2026, 8, 15, 3, 0).toISOString()
  it('says what the night did, and counts a run of the same outcome', () => {
    expect(nightshiftLine(null)).toBe('Nightshift has not recorded a run.')
    expect(nightshiftLine({ ran_at: at, staged: 0, failed: 4, seen: 4, error: "No such file or directory: 'claude'", kind: 'broken', streak: 41 }))
      .toBe("Nightshift failed at 03:00 — No such file or directory: 'claude' (41 nights running)")
    expect(nightshiftLine({ ran_at: at, staged: 2, failed: 0, seen: 2, error: null, kind: 'staged', streak: 1 }))
      .toBe('Nightshift ran at 03:00 — 2 proposals staged')
    expect(nightshiftLine({ ran_at: at, staged: 1, failed: 1, seen: 3, error: null, kind: 'partial', streak: 1 }))
      .toBe('Nightshift ran at 03:00 — 1 proposal staged, 1 of 3 failed')
    expect(nightshiftLine({ ran_at: at, staged: 0, failed: 0, seen: 0, error: null, kind: 'quiet', streak: 3 }))
      .toBe('Nightshift ran at 03:00 — nothing to stage (3 nights running)')
  })
})

describe('sinceLabel', () => {
  const now = new Date(2026, 8, 15, 10, 0)
  it('reads as a person would say it', () => {
    expect(sinceLabel(new Date(2026, 8, 15, 9, 12).toISOString(), now)).toBe('since 09:12')
    expect(sinceLabel(new Date(2026, 8, 14, 23, 40).toISOString(), now)).toBe('since yesterday 23:40')
    expect(sinceLabel(new Date(2026, 8, 10, 23, 40).toISOString(), now)).toBe('since Thu 10 Sep 23:40')
  })
  it('a missing date says what the window really was', () => {
    expect(sinceLabel(null, now)).toBe('the last day')
    expect(sinceLabel('not a date', now)).toBe('the last day')
  })
})
