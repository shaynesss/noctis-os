/* The digest's sentences: every clause is a count, and the count is tested. */
import { describe, expect, it } from 'vitest'
import { digestLines, sinceLabel, type DigestPayload } from './Panels'

const base: DigestPayload = {
  date: 'Tuesday 15 September',
  since: '2026-09-14T23:40:00+00:00',
  sessions: [],
  repos: [],
  modes: [
    { label: 'Faber', job: 'Noctis OS', days: 0, more: 0 },
    { label: 'Vesper', job: null, days: null, more: 0 },
    { label: 'Noctua', job: 'Rust', days: 9, more: 2 },
  ],
  owed: [],
  open: 4,
  on_hold: 2,
  inbox: { waiting: 0, flagged: 0, arrived: 0 },
  nightshift: null,
}

describe('digestLines', () => {
  it('says what happened, and says so when nothing did', () => {
    const { happened, next } = digestLines(base)
    expect(happened).toEqual(['No sessions ran.', 'No commits.', 'Nightshift has not recorded a run.'])
    expect(next).toEqual(['nothing'])
  })

  it('a broken nightshift is a line of its own, counted, and a next', () => {
    const at = new Date(2026, 8, 15, 3, 0).toISOString()
    const { happened, next } = digestLines({ ...base, nightshift: { ran_at: at, staged: 0, failed: 4, seen: 4, error: "No such file or directory: 'claude'", kind: 'broken', streak: 41 } })
    expect(happened.at(-1)).toBe("Nightshift failed at 03:00 — No such file or directory: 'claude' (41 nights running)")
    expect(next[0]).toBe("nightshift is broken — No such file or directory: 'claude'")
    expect(digestLines({ ...base, nightshift: { ran_at: at, staged: 2, failed: 0, seen: 2, error: null, kind: 'staged', streak: 1 } }).happened.at(-1))
      .toBe('Nightshift ran at 03:00 — 2 proposals staged')
    expect(digestLines({ ...base, nightshift: { ran_at: at, staged: 0, failed: 0, seen: 0, error: null, kind: 'quiet', streak: 3 } }).happened.at(-1))
      .toBe('Nightshift ran at 03:00 — nothing to stage (3 nights running)')
  })

  it('names the sessions by character and the repositories by movement', () => {
    const { happened } = digestLines({
      ...base,
      sessions: [{ mode: 'faber', count: 3, titles: ['Stats list price', 'Repo modules'] }, { mode: 'noctua', count: 1, titles: [] }],
      repos: [
        { name: 'noctis-os', branch: 'main', commits: 12, ahead: 12, dirty: 0 },
        { name: 'second-brain', branch: 'main', commits: 0, ahead: 11, dirty: 2 },
        { name: 'quiet', branch: 'main', commits: 0, ahead: 0, dirty: 0 },
      ],
      inbox: { waiting: 2, flagged: 0, arrived: 2 },
    })
    expect(happened).toEqual([
      'Faber ran 3 sessions — Stats list price · Repo modules',
      'Noctua ran 1 session',
      'noctis-os · 12 commits, 12 not pushed',
      'second-brain · nothing new, 11 not pushed, 2 files uncommitted',
      '2 proposals arrived.',
      'Nightshift has not recorded a run.',
    ])
  })

  it('what is next is derived, not written: pushes, decisions, the owed', () => {
    const { next } = digestLines({
      ...base,
      repos: [
        { name: 'noctis-os', branch: 'main', commits: 1, ahead: 12, dirty: 0 },
        { name: 'second-brain', branch: 'main', commits: 0, ahead: 11, dirty: 0 },
      ],
      owed: [{ name: 'Old topic', days: 45, mode: 'Noctua' }],
      inbox: { waiting: 1, flagged: 2, arrived: 0 },
    })
    expect(next).toEqual([
      'push noctis-os and second-brain from Repo',
      '1 proposal waiting below',
      '2 flagged jobs below',
      'Old topic untouched 45 days — a decision is owed',
    ])
  })

  it('the standing line is one job per character, the rest counted', () => {
    expect(digestLines(base).standing).toBe(
      'Faber · Noctis OS, touched today  ·  Vesper — nothing open  ·  Noctua · Rust +2, 9 days  ·  4 open  ·  2 on hold',
    )
  })
})

describe('sinceLabel', () => {
  const now = new Date(2026, 8, 15, 10, 0)
  it('reads as a person would say it', () => {
    expect(sinceLabel(new Date(2026, 8, 15, 9, 12).toISOString(), now)).toBe('since 09:12')
    expect(sinceLabel(new Date(2026, 8, 14, 23, 40).toISOString(), now)).toBe('since yesterday 23:40')
    expect(sinceLabel(new Date(2026, 8, 10, 23, 40).toISOString(), now)).toBe('since Thu 10 Sep 23:40')
  })
  it('a first look says what the window really was', () => {
    expect(sinceLabel(null, now)).toBe('the last day')
    expect(sinceLabel('not a date', now)).toBe('the last day')
  })
})
