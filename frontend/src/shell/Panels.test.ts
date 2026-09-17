/* The nightshift line and the relative-date label: sentences composed from
 * counts, held to the string. (The digest these came from is gone; the
 * line lives on in Settings' Maintenance section.) */
import { describe, expect, it } from 'vitest'
import { nightshiftLine, reflow, sinceLabel } from './Panels'

describe('nightshiftLine', () => {
  const at = new Date(2026, 8, 15, 3, 0).toISOString()
  it('says when it ran, and nothing else when nothing went wrong', () => {
    expect(nightshiftLine(null)).toBe('Nightshift has not recorded a run.')
    // The outcome went (2026-09-17): the proposals it staged are listed
    // directly underneath, so the sentence was reading the list out.
    expect(nightshiftLine({ ran_at: at, staged: 2, failed: 0, seen: 2, error: null, dropped: 0, gates: [], kind: 'staged', streak: 1 }))
      .toBe('Nightshift ran at 03:00')
    expect(nightshiftLine({ ran_at: at, staged: 0, failed: 0, seen: 0, error: null, dropped: 0, gates: [], kind: 'quiet', streak: 3 }))
      .toBe('Nightshift ran at 03:00')
  })

  it('names a discarded draft, which read as a plain "ran" for two nights', () => {
    /* seen 3, staged 0, failed 0 is what 2026-09-16 recorded: three distiller
       calls whose drafts were dropped by a silent gate. The line said
       "Nightshift ran at 01:04" and nothing else. */
    expect(nightshiftLine({ ran_at: at, staged: 0, failed: 0, seen: 3, error: null, dropped: 3, gates: ['no-draft'], kind: 'dropped', streak: 2 }))
      .toBe('Nightshift ran at 03:00, 3 drafts discarded (no-draft) (2 nights running)')
    // Staging something does not excuse discarding the rest.
    expect(nightshiftLine({ ran_at: at, staged: 1, failed: 0, seen: 4, error: null, dropped: 3, gates: ['no-confidence', 'no-rationale'], kind: 'dropped', streak: 1 }))
      .toBe('Nightshift ran at 03:00, 3 drafts discarded (no-confidence, no-rationale), 1 staged')
    // One draft, singular, and no gate recorded (an entry from before the
    // gates existed) still says the count rather than saying nothing.
    expect(nightshiftLine({ ran_at: at, staged: 0, failed: 0, seen: 1, error: null, dropped: 1, gates: [], kind: 'dropped', streak: 1 }))
      .toBe('Nightshift ran at 03:00, 1 draft discarded')
  })

  it('still says so when the night failed, which is the whole point of the record', () => {
    // It failed every night for forty-one nights while its log said
    // "quiet"; a failure that reads like a success is the bug this exists
    // to prevent, so it is the one outcome the line keeps.
    expect(nightshiftLine({ ran_at: at, staged: 0, failed: 4, seen: 4, error: "No such file or directory: 'claude'", dropped: 0, gates: [], kind: 'broken', streak: 41 }))
      .toBe("Nightshift failed at 03:00: No such file or directory: 'claude' (41 nights running)")
    expect(nightshiftLine({ ran_at: at, staged: 1, failed: 1, seen: 3, error: null, dropped: 0, gates: [], kind: 'partial', streak: 1 }))
      .toBe('Nightshift ran at 03:00, 1 of 3 failed')
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
