/* Reducer and SSE-framing tests.
 *
 * These cover the logic no type checker can: that many deltas are one
 * paragraph, that a result finds its call across interleaved events, and
 * that a chunk boundary landing mid-frame does not lose an event.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { emptyFold, fold, get, readSSE, runSession, type WireEvent } from './engine'
import {
  DEFAULT_EFFORT, EFFORT_CYCLE, patchEntry, recallOpenTabs, rememberOpenTabs, uniqueLabel,
} from './domain'
import type { Block, Effort } from './domain'

const run = (events: WireEvent[]) => events.reduce(fold, emptyFold())

describe('fold', () => {
  it('joins text deltas into one block rather than one per delta', () => {
    const s = run([{ t: 'text', text: 'Hel' }, { t: 'text', text: 'lo ' }, { t: 'text', text: 'there' }])
    expect(s.blocks).toHaveLength(1)
    expect(s.blocks[0]).toEqual({ kind: 'text', text: 'Hello there' })
  })

  it('starts a new text block after a tool call interrupts', () => {
    const s = run([
      { t: 'text', text: 'before' },
      { t: 'tool_call', id: '1', name: 'Read', summary: '/a.py' },
      { t: 'text', text: 'after' },
    ])
    expect(s.blocks.map((b) => b.kind)).toEqual(['text', 'tool', 'text'])
    expect((s.blocks[2] as { text: string }).text).toBe('after')
  })

  it('matches a result to its call by id, not by recency', () => {
    // Two calls open at once and the *first* resolves last -- matching by
    // position would put this content on the wrong row.
    const s = run([
      { t: 'tool_call', id: 'a', name: 'Read', summary: '/a.py' },
      { t: 'tool_call', id: 'b', name: 'Bash', summary: 'ls' },
      { t: 'tool_result', id: 'b', content: 'B-OUT', truncated: false, is_error: false },
      { t: 'tool_result', id: 'a', content: 'A-OUT', truncated: false, is_error: false },
    ])
    const tools = s.blocks.filter((b): b is Extract<Block, { kind: 'tool' }> => b.kind === 'tool')
    expect(tools.map((t) => [t.id, t.body])).toEqual([['a', 'A-OUT'], ['b', 'B-OUT']])
  })

  it('ignores a result for a call it never saw', () => {
    const s = run([{ t: 'tool_result', id: 'ghost', content: 'x', truncated: false, is_error: false }])
    expect(s.blocks).toHaveLength(0)
  })

  it('opens a failed tool call and leaves a successful one collapsed', () => {
    const s = run([
      { t: 'tool_call', id: '1', name: 'Bash', summary: 'boom' },
      { t: 'tool_result', id: '1', content: 'nope', truncated: false, is_error: true },
      { t: 'tool_call', id: '2', name: 'Read', summary: '/a' },
      { t: 'tool_result', id: '2', content: 'ok', truncated: false, is_error: false },
    ])
    const tools = s.blocks.filter((b): b is Extract<Block, { kind: 'tool' }> => b.kind === 'tool')
    expect(tools[0].open).toBe(true)
    expect(tools[0].meta).toBe('error')
    expect(tools[1].open).toBeFalsy()
  })

  it('marks a truncated result so the row can say so', () => {
    const s = run([
      { t: 'tool_call', id: '1', name: 'Read', summary: '/big' },
      { t: 'tool_result', id: '1', content: 'x', truncated: true, is_error: false },
    ])
    expect((s.blocks[0] as { meta: string }).meta).toBe('truncated')
  })

  it('keeps thinking progress out of the transcript', () => {
    // A block per tick would fill the transcript with counters that stop
    // being true the moment the next tick lands.
    const s = run([{ t: 'thinking_progress', tokens: 50 }, { t: 'thinking_progress', tokens: 250 }])
    expect(s.blocks).toHaveLength(0)
    expect(s.thinking).toBe(250)
  })

  it('clears the live counter once output arrives', () => {
    const s = run([{ t: 'thinking_progress', tokens: 90 }, { t: 'text', text: 'go' }])
    expect(s.thinking).toBeNull()
  })

  it('records a thinking block even though its text is empty', () => {
    const s = run([{ t: 'thinking', text: '', tokens: 300 }])
    expect(s.blocks[0]).toMatchObject({ kind: 'thinking', tokens: 300 })
  })

  it('puts an engine error in the transcript and marks a fatal one done', () => {
    const s = run([{ t: 'error', message: 'exited 3', fatal: true }])
    expect(s.blocks[0]).toMatchObject({ kind: 'error', message: 'exited 3', fatal: true })
    expect(s.done).toBe(true)
  })

  it('a non-fatal error does not end the session', () => {
    expect(run([{ t: 'error', message: 'hm', fatal: false }]).done).toBe(false)
  })

  it('captures the session id from start and turn_end for resume', () => {
    const s = run([
      { t: 'start', session_id: 'abc', model: 'opus-5', cwd: '/x', tools: [] },
      { t: 'turn_end', session_id: 'abc', duration_ms: 5, stop_reason: null,
        usage: { input: 1, output: 2, cached: 0, model: 'opus-5', aux_input: 0,
                 aux_output: 0, context_window: 1000000 } },
    ])
    expect(s.sessionId).toBe('abc')
    expect(s.done).toBe(true)
  })

  it('puts a silent turn in the transcript instead of leaving it blank', () => {
    // The failure this exists for: tools ran, no text came back, and the
    // transcript drew nothing -- which looks exactly like a dead backend.
    const s = run([
      { t: 'tool_call', id: '1', name: 'Bash', summary: 'ls' },
      { t: 'turn_end', session_id: 'a', duration_ms: 1, stop_reason: null,
        silent: true, text_chars: 0, tool_calls: 3,
        usage: { input: 1, output: 0, cached: 0, model: 'm', aux_input: 0,
                 aux_output: 0, context_window: 1000 } },
    ])
    const last = s.blocks[s.blocks.length - 1]
    expect(last.kind).toBe('silent')
    expect(last).toMatchObject({ tools: 3 })
  })

  it('marks a turn that narrated and then stopped on a tool call', () => {
    // The live 2026-09-12 case: the narrow check counted text across the
    // whole turn, so mid-turn commentary hid an unexplained trailing tool
    // call. Whether it spoke earlier says nothing about whether it finished.
    const s = run([
      { t: 'text', text: 'Now verifying — the repro and both suites:' },
      { t: 'tool_call', id: '1', name: 'Bash', summary: 'make test' },
      { t: 'turn_end', session_id: 'a', duration_ms: 1, stop_reason: null,
        silent: false, unclosed: true, text_chars: 41, tool_calls: 2,
        text_after_last_tool: 0,
        usage: { input: 1, output: 1, cached: 0, model: 'm', aux_input: 0,
                 aux_output: 0, context_window: 1000 } },
    ])
    const last = s.blocks[s.blocks.length - 1]
    expect(last.kind).toBe('silent')
    expect(last).toMatchObject({ spoke: true, tools: 2 })
  })

  it('adds nothing when the turn actually replied', () => {
    const s = run([
      { t: 'text', text: 'here you go' },
      { t: 'turn_end', session_id: 'a', duration_ms: 1, stop_reason: null,
        silent: false, unclosed: false, text_chars: 11, tool_calls: 0,
        usage: { input: 1, output: 1, cached: 0, model: 'm', aux_input: 0,
                 aux_output: 0, context_window: 1000 } },
    ])
    expect(s.blocks.some((b) => b.kind === 'silent')).toBe(false)
  })

  it('records context occupancy from the last snapshot, not the turn total', () => {
    const s = run([
      { t: 'context', tokens: 26589 },
      { t: 'turn_end', session_id: 'a', duration_ms: 1, stop_reason: null,
        usage: { input: 2, output: 5, cached: 0, model: 'm', aux_input: 0, aux_output: 0,
                 context_window: 1000000 } },
    ])
    expect(s.context).toBeCloseTo(0.0265, 3)
  })

  it('tracks the newest snapshot as a tool-running turn proceeds', () => {
    // The bug this replaced: summing every API call in the turn and dividing
    // by one window, which reported 470% full on a real turn.
    const s = run([
      { t: 'turn_end', session_id: 'a', duration_ms: 1, stop_reason: null,
        usage: { input: 2, output: 5, cached: 0, model: 'm', aux_input: 0, aux_output: 0,
                 context_window: 1000000 } },
      { t: 'context', tokens: 100000 },
      { t: 'context', tokens: 300000 },
    ])
    expect(s.context).toBeCloseTo(0.3, 3)
    expect(s.context!).toBeLessThanOrEqual(1)
  })

  it('leaves context unknown when no window is reported', () => {
    // Unknown must not become 0%, which reads as a conversation with room to
    // spare rather than one we know nothing about.
    const s = run([
      { t: 'context', tokens: 500 },
      { t: 'turn_end', session_id: 'a', duration_ms: 1, stop_reason: null,
        usage: { input: 2, output: 5, cached: 0, model: 'm', aux_input: 0, aux_output: 0,
                 context_window: 0 } },
    ])
    expect(s.context).toBeNull()
  })

  it('never mutates the state it was given', () => {
    const before = emptyFold([{ kind: 'text', text: 'a' }])
    const snapshot = JSON.stringify(before)
    fold(before, { t: 'text', text: 'b' })
    expect(JSON.stringify(before)).toBe(snapshot)
  })
})

/** A stream that hands out exactly the chunks given, to control where the
 *  boundaries fall. */
function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder()
  return new ReadableStream({
    start(c) {
      chunks.forEach((ch) => c.enqueue(enc.encode(ch)))
      c.close()
    },
  })
}

async function collect(s: ReadableStream<Uint8Array>) {
  const out: WireEvent[] = []
  for await (const e of readSSE(s)) out.push(e)
  return out
}

describe('readSSE', () => {
  it('reads whole frames', async () => {
    const events = await collect(streamOf([
      'data: {"t":"text","text":"a"}\n\n',
      'data: {"t":"text","text":"b"}\n\n',
    ]))
    expect(events).toEqual([{ t: 'text', text: 'a' }, { t: 'text', text: 'b' }])
  })

  it('reassembles a frame split across chunks', async () => {
    // Chunk boundaries fall wherever the network puts them, including the
    // middle of a JSON payload.
    const events = await collect(streamOf(['data: {"t":"te', 'xt","text":"split"}', '\n\n']))
    expect(events).toEqual([{ t: 'text', text: 'split' }])
  })

  it('handles several frames arriving in one chunk', async () => {
    const events = await collect(streamOf([
      'data: {"t":"text","text":"1"}\n\ndata: {"t":"text","text":"2"}\n\n',
    ]))
    expect(events).toHaveLength(2)
  })

  it('survives a multi-byte character split across chunks', async () => {
    // "→" is three bytes; cutting it in half must not corrupt the frame.
    const enc = new TextEncoder()
    const bytes = enc.encode('data: {"t":"text","text":"→"}\n\n')
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(bytes.slice(0, 27))
        c.enqueue(bytes.slice(27))
        c.close()
      },
    })
    expect(await collect(stream)).toEqual([{ t: 'text', text: '→' }])
  })

  it('skips a malformed frame instead of killing the stream', async () => {
    // A dead transcript is a worse failure than one missing line.
    const events = await collect(streamOf([
      'data: {"t":"text","text":"ok"}\n\n',
      'data: {not json\n\n',
      'data: {"t":"text","text":"still here"}\n\n',
    ]))
    expect(events).toEqual([{ t: 'text', text: 'ok' }, { t: 'text', text: 'still here' }])
  })

  it('ignores a trailing partial frame rather than emitting half an event', async () => {
    const events = await collect(streamOf(['data: {"t":"text","text":"a"}\n\ndata: {"t":"tex']))
    expect(events).toEqual([{ t: 'text', text: 'a' }])
  })
})

/* The model shown must be the one the engine reported, not the one we asked
 * for. A session cannot answer this about itself — a model has no
 * introspective access to its own weights, so "am I really Sonnet?" gets an
 * honest shrug. The engine reports it twice, and that is the only
 * authoritative answer available. */
describe('which model ran', () => {
  it('takes the model from the start event', () => {
    const s = run([{ t: 'start', session_id: 'a', model: 'claude-haiku-4-5', cwd: '/x', tools: [] }])
    expect(s.model).toBe('claude-haiku-4-5')
  })

  it('confirms it from what was actually billed', () => {
    const s = run([
      { t: 'start', session_id: 'a', model: 'claude-opus-5', cwd: '/x', tools: [] },
      { t: 'turn_end', session_id: 'a', duration_ms: 1, stop_reason: null,
        usage: { input: 1, output: 1, cached: 0, model: 'claude-haiku-4-5', aux_input: 0,
                 aux_output: 0, context_window: 0 } },
    ])
    // Billing is the last word: it is what was charged, not what was asked.
    expect(s.model).toBe('claude-haiku-4-5')
  })

  it('is unknown before a turn has run', () => {
    expect(run([]).model).toBeNull()
  })

  it('keeps the reported model when a later turn reports none', () => {
    const s = run([
      { t: 'start', session_id: 'a', model: 'claude-opus-5', cwd: '/x', tools: [] },
      { t: 'turn_end', session_id: 'a', duration_ms: 1, stop_reason: null,
        usage: { input: 1, output: 1, cached: 0, model: '', aux_input: 0,
                 aux_output: 0, context_window: 0 } },
    ])
    expect(s.model).toBe('claude-opus-5')
  })
})

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

describe('remembering which tabs were open', () => {
  /* A stub rather than jsdom. The suite runs in node, and the only thing
   * under test here is the read/write/guard logic -- pulling in a DOM for a
   * two-method object would be a dependency bought for one file. */
  beforeEach(() => {
    const store = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('round-trips the arrangement', () => {
    rememberOpenTabs([
      { mode: 'faber', label: 'Faber · noctis-os', engineId: 'e1' },
      { mode: 'vesper', label: 'Vesper · second-brain', engineId: 'e2' },
    ])
    expect(recallOpenTabs().map((t) => t.engineId)).toEqual(['e1', 'e2'])
  })

  it('drops tabs that never reached the backend', () => {
    // No engine id means no transcript to fetch, so restoring it would add
    // an empty tab that looks like a lost conversation rather than a new one.
    rememberOpenTabs([
      { mode: 'faber', label: 'a', engineId: 'e1' },
      { mode: 'faber', label: 'b' },
    ])
    expect(recallOpenTabs()).toHaveLength(1)
  })

  it('survives junk in storage rather than throwing', () => {
    localStorage.setItem('noctis.openTabs', '{not json')
    expect(recallOpenTabs()).toEqual([])
    localStorage.setItem('noctis.openTabs', '"a string"')
    expect(recallOpenTabs()).toEqual([])
  })

  it('returns nothing on a fresh install', () => {
    // Which is what keeps a first launch on the old behaviour: one
    // conversation beside General rather than an empty restore.
    expect(recallOpenTabs()).toEqual([])
  })


  it('a boot-time read is unaffected by a later write', () => {
    // The ordering hazard this exists for. React runs effects in declaration
    // order, and the writer is declared before the restorer -- so on the
    // remount that follows a crash, `tabs` is the bare General seed and the
    // writer would persist an empty list *before* the restorer reads it.
    // The arrangement would be destroyed by the recovery meant to preserve
    // it. Capturing at boot is what makes the read immune.
    rememberOpenTabs([{ mode: 'faber', label: 'Faber · noctis-os', engineId: 'e1' }])
    const atBoot = recallOpenTabs()

    rememberOpenTabs([])                       // what the ungated writer did

    expect(atBoot.map((t) => t.engineId)).toEqual(['e1'])
    expect(recallOpenTabs()).toEqual([])       // storage really was cleared
  })

  it('survives storage being unavailable entirely', () => {
    // A private window, or an embedded context with site data blocked, throws
    // on access rather than returning null. Losing the arrangement is a far
    // smaller failure than refusing to start.
    vi.stubGlobal('localStorage', {
      getItem: () => { throw new Error('denied') },
      setItem: () => { throw new Error('denied') },
    })
    expect(() => rememberOpenTabs([{ mode: 'faber', label: 'x', engineId: 'e' }])).not.toThrow()
    expect(recallOpenTabs()).toEqual([])
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

describe('runSession when the connection dies mid-turn', () => {
  const withFetch = async (impl: typeof fetch, run: () => Promise<unknown>) => {
    const real = globalThis.fetch
    globalThis.fetch = impl
    try {
      return await run()
    } finally {
      globalThis.fetch = real
    }
  }

  /* A stream that delivers a few frames and then fails, which is what a
   * dropped connection actually looks like -- not a rejected fetch. The
   * opening request succeeded; the failure is in `reader.read()`. */
  const dyingStream = (err: Error): ReadableStream<Uint8Array> => {
    const enc = new TextEncoder()
    let sent = false
    return new ReadableStream({
      pull(c) {
        if (!sent) {
          sent = true
          c.enqueue(enc.encode('data: {"t":"text","text":"working"}\n\n'))
          return
        }
        c.error(err)
      },
    })
  }

  const respondWith = (body: ReadableStream<Uint8Array>) =>
    (() => Promise.resolve({ ok: true, body } as Response)) as unknown as typeof fetch

  it('reports the drop instead of throwing past the caller', async () => {
    // The whole defect: this rejection used to escape `runSession`, and the
    // caller's try/finally has no catch -- so `busy` cleared, the composer
    // unlocked, and nothing was written. The turn appeared to be ignored.
    const events = await withFetch(
      respondWith(dyingStream(new TypeError('Load failed'))),
      async () => {
        const out: WireEvent[] = []
        for await (const e of runSession({ mode: 'noctua', prompt: 'x', cwd: '/tmp', permission_mode: 'manual' })) out.push(e)
        return out
      },
    ) as WireEvent[]

    expect(events[0]).toEqual({ t: 'text', text: 'working' })
    const last = events[events.length - 1]
    expect(last.t).toBe('error')
    expect(last).toMatchObject({ fatal: true })
    expect((last as { message: string }).message).toContain('connection lost')
  })

  it('says nothing when the reader was aborted on purpose', async () => {
    // Escape aborts the stream. Reporting the user's own action back to them
    // as a fatal error is noise, and would make stopping look like breaking.
    const ctrl = new AbortController()
    const events = await withFetch(
      respondWith(dyingStream(new DOMException('aborted', 'AbortError'))),
      async () => {
        const out: WireEvent[] = []
        for await (const e of runSession({ mode: 'noctua', prompt: 'x', cwd: '/tmp', permission_mode: 'manual' },
                                  ctrl.signal)) {
          out.push(e)
          ctrl.abort()
        }
        return out
      },
    ) as WireEvent[]

    expect(events.some((e) => e.t === 'error')).toBe(false)
  })
})
