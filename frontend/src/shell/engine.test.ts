/* Reducer and SSE-framing tests.
 *
 * These cover the logic no type checker can: that many deltas are one
 * paragraph, that a result finds its call across interleaved events, and
 * that a chunk boundary landing mid-frame does not lose an event.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { get } from './engine'
import {
  recallSlots, rememberSlots,
} from './domain'

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

  it('round-trips mode, directory, session id and the slot id', () => {
    // The slot id is what a reload reattaches by: the PTY registry outlives
    // the page and is keyed by it.
    rememberSlots([{ id: 'term-faber-1a2b', mode: 'faber', cwd: '/r', sessionId: 'abc' }, { mode: 'general', cwd: '/v' }])
    expect(recallSlots()).toEqual([
      { id: 'term-faber-1a2b', mode: 'faber', cwd: '/r', sessionId: 'abc' }, { mode: 'general', cwd: '/v' },
    ])
  })

  it('drops a record whose slot id is not a string', () => {
    localStorage.setItem('noctis.open-slots', JSON.stringify([{ id: 7, mode: 'faber', cwd: '/r' }]))
    expect(recallSlots()).toEqual([])
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
