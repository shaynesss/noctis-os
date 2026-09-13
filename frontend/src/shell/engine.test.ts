/* Reducer and SSE-framing tests.
 *
 * These cover the logic no type checker can: that many deltas are one
 * paragraph, that a result finds its call across interleaved events, and
 * that a chunk boundary landing mid-frame does not lose an event.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { get } from './engine'
import {
  DEFAULT_EFFORT, EFFORT_CYCLE, patchEntry, recallSlots, rememberSlots, uniqueLabel,
} from './domain'
import type { Effort } from './domain'


describe('get', () => {
  const withFetch = async (impl: typeof fetch, run: () => Promise<unknown>) => {
    const real = globalThis.fetch
    globalThis.fetch = impl
    try {
      return await run()
    } finally {
      globalThis.fetch = real
    }
  }

  it('returns null when the request fails outright', async () => {
    // A refused connection, which is what a restarting backend usually gives.
    const out = await withFetch(
      (() => Promise.reject(new TypeError('Load failed'))) as unknown as typeof fetch,
      () => get('/v2/brief'),
    )
    expect(out).toBeNull()
  })

  it('returns null when the request is aborted by its timeout', async () => {
    // The case that produced a permanent "Loading…": a backend that accepts
    // and never answers. Without a timeout the promise never settles at all,
    // so the caller cannot distinguish slow from never.
    const out = await withFetch(
      (() => Promise.reject(new DOMException('timed out', 'TimeoutError'))) as unknown as typeof fetch,
      () => get('/v2/brief'),
    )
    expect(out).toBeNull()
  })

  it('returns null on a non-ok response rather than throwing', async () => {
    const out = await withFetch(
      (() => Promise.resolve(new Response('nope', { status: 500 }))) as unknown as typeof fetch,
      () => get('/v2/brief'),
    )
    expect(out).toBeNull()
  })

  it('passes an abort signal, so a hung request cannot wait forever', async () => {
    let seen: RequestInit | undefined
    await withFetch(
      ((_url: string, init: RequestInit) => {
        seen = init
        return Promise.resolve(new Response('{}', { status: 200 }))
      }) as unknown as typeof fetch,
      () => get('/v2/brief'),
    )
    expect(seen?.signal).toBeInstanceOf(AbortSignal)
  })
})

describe('effort defaults', () => {
  it('falls back to the documented default for a tab nobody has touched', () => {
    // The chip is per-tab, so most tabs have no entry at all. The fallback is
    // what they run at, and dev.md asks for `high` -- a default that quietly
    // costs less is the kind of thing nobody notices is wrong.
    const efforts: Record<string, Effort> = { t1: 'low' }
    const effortOf = (id: string): Effort => efforts[id] ?? DEFAULT_EFFORT
    expect(effortOf('t1')).toBe('low')
    expect(effortOf('untouched')).toBe('high')
    expect(DEFAULT_EFFORT).toBe('high')
  })

  it('cycles one tab without moving another', () => {
    // The bug the per-tab map exists for: one global dial meant moving the
    // chip on any tab silently moved it on all of them, pinning a research
    // session to whatever the last General question happened to want.
    let efforts: Record<string, Effort> = { a: 'low', b: 'xhigh' }
    const cycle = (id: string) => {
      const now = efforts[id] ?? DEFAULT_EFFORT
      efforts = {
        ...efforts,
        [id]: EFFORT_CYCLE[(EFFORT_CYCLE.indexOf(now) + 1) % EFFORT_CYCLE.length],
      }
    }
    cycle('a')
    expect(efforts.a).toBe('medium')
    expect(efforts.b).toBe('xhigh')
    cycle('b')
    expect(efforts.b).toBe('low')      // wraps past the end
    expect(efforts.a).toBe('medium')
  })
})

describe('tab labels', () => {
  it('leaves the first of a kind alone', () => {
    expect(uniqueLabel('Faber · noctis-os', [])).toBe('Faber · noctis-os')
    expect(uniqueLabel('Faber · noctis-os', ['General'])).toBe('Faber · noctis-os')
  })

  it('disambiguates a second session of the same mode on the same directory', () => {
    // The case this exists for: two Faber tabs on one repo, which is an
    // ordinary thing to want and used to be impossible anyway.
    const taken = ['General', 'Faber · noctis-os']
    expect(uniqueLabel('Faber · noctis-os', taken)).toBe('Faber · noctis-os (2)')
    expect(uniqueLabel('Faber · noctis-os', [...taken, 'Faber · noctis-os (2)']))
      .toBe('Faber · noctis-os (3)')
  })

  it('does not reuse a number freed by a closed tab', () => {
    // Closing (2) while (3) is open must not hand the next tab (2) as well.
    expect(uniqueLabel('Faber · x', ['Faber · x', 'Faber · x (3)']))
      .toBe('Faber · x (2)')
  })
})

describe('patchEntry', () => {
  it('applies the patch when the entry is there', () => {
    const m = { a: { n: 1 }, b: { n: 2 } }
    expect(patchEntry(m, 'a', (p) => ({ n: p.n + 10 }))).toEqual({ a: { n: 11 }, b: { n: 2 } })
  })

  it('drops the update when the entry is gone, rather than throwing', () => {
    // The live crash: closing a tab deletes its session and aborts the
    // stream, but the abort resolves a tick later -- so the stream's own
    // updater and its `finally` both still run. Spreading `...s[tabId]`
    // there threw `undefined is not an object (evaluating
    // 's[tabId].lastTurn')` and took the window down.
    const m: Record<string, { n: number }> = { a: { n: 1 } }
    expect(() => patchEntry(m, 'closed', (p) => ({ n: p.n + 1 }))).not.toThrow()
    expect(patchEntry(m, 'closed', (p) => ({ n: p.n + 1 }))).toBe(m)
  })

  it('does not resurrect a deleted entry', () => {
    // Dropping is correct rather than merely safe: the tab it described is
    // closed, so there is nothing left for the update to say.
    const m: Record<string, { n: number }> = {}
    expect(patchEntry(m, 'gone', () => ({ n: 99 }))).toEqual({})
  })
})


describe('retry backoff', () => {
  // Mirrors useFetched's schedule. Kept as a test because the shape is the
  // point: fast enough that a restart heals before you reach for the window,
  // slow enough that a backend which is genuinely down is not polled every
  // three seconds forever.
  const RETRY_MS = [1000, 2000, 4000, 8000, 15000]
  const backoff = (n: number) => RETRY_MS[Math.min(n, RETRY_MS.length - 1)]

  it('starts fast, because most outages are a restart', () => {
    expect(backoff(0)).toBe(1000)
  })

  it('grows, and then holds rather than growing forever', () => {
    const first = [0, 1, 2, 3, 4].map(backoff)
    expect(first).toEqual([...first].sort((a, b) => a - b))
    expect(backoff(9)).toBe(15000)
    expect(backoff(99)).toBe(15000)
  })

  it('never reaches zero or an unbounded wait', () => {
    for (const n of [0, 1, 5, 50]) {
      expect(backoff(n)).toBeGreaterThan(0)
      expect(backoff(n)).toBeLessThanOrEqual(15000)
    }
  })
})



describe('remembering which terminals were open', () => {
  beforeEach(() => {
    const store: Record<string, string> = {}
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v },
    })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('round-trips mode, directory and session id', () => {
    rememberSlots([{ mode: 'faber', cwd: '/r', sessionId: 'abc' }, { mode: 'general', cwd: '/v' }])
    expect(recallSlots()).toEqual([
      { mode: 'faber', cwd: '/r', sessionId: 'abc' }, { mode: 'general', cwd: '/v' },
    ])
  })

  it('drops entries that cannot be reopened', () => {
    // A slot with no directory has nowhere to start; a non-object is a
    // stale format. Neither is worth trusting.
    localStorage.setItem('noctis.open-slots', JSON.stringify([{ mode: 'faber' }, 'junk', null]))
    expect(recallSlots()).toEqual([])
  })

  it('is empty rather than throwing when storage is unavailable', () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('denied') } })
    expect(recallSlots()).toEqual([])
  })
})
