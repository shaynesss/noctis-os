/* The nightshift line and the relative-date label: sentences composed from
 * counts, held to the string. (The digest these came from is gone; the
 * line lives on in Settings' Maintenance section.) */
import { describe, expect, it } from 'vitest'
import { nightshiftLine, reflow, sinceLabel, trailsLine } from './Panels'

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

describe('reflow', () => {
  it('joins the lines of a paragraph and keeps the blank lines between paragraphs', () => {
    const body = 'Bodies show in the\nRepo view, newest expanded; the parser pads\nthe trailing field.\n\nLeaves the view as the landing page.\nNext: push from the Repo tab.\n'
    expect(reflow(body)).toEqual([
      'Bodies show in the Repo view, newest expanded; the parser pads the trailing field.',
      'Leaves the view as the landing page. Next: push from the Repo tab.',
    ])
  })
  it('keeps the lines of a list', () => {
    expect(reflow('- one\n- two\n\n1. first\n2. second')).toEqual(['- one\n- two', '1. first\n2. second'])
  })
  it('returns nothing for an empty body', () => {
    expect(reflow('  \n')).toEqual([])
  })
})

describe('trailsLine', () => {
  it('says the record is current when the vault was written after the code, or within the hour', () => {
    expect(trailsLine({ project_at: 1000, record_at: 2000, behind: -1000 })).toMatch(/current/)
    expect(trailsLine({ project_at: 5000, record_at: 2000, behind: 3000 })).toMatch(/current/)
  })
  it('says how far the record trails the code in hours, then days', () => {
    expect(trailsLine({ project_at: 0, record_at: 0, behind: 5 * 3600 })).toBe('The record is 5h behind the code — the newest project commit has no vault entry after it.')
    expect(trailsLine({ project_at: 0, record_at: 0, behind: 72 * 3600 })).toMatch(/3d behind/)
  })
  it('says so when there is no record at all', () => {
    expect(trailsLine(null)).toMatch(/No record commits yet/)
  })
})
