/* Reducer and SSE-framing tests.
 *
 * These cover the logic no type checker can: that many deltas are one
 * paragraph, that a result finds its call across interleaved events, and
 * that a chunk boundary landing mid-frame does not lose an event.
 */
import { describe, expect, it } from 'vitest'
import { emptyFold, fold, readSSE, type WireEvent } from './engine'
import type { Block } from './mock'

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
                 aux_output: 0, context_tokens: 26589, context_window: 1000000 } },
    ])
    expect(s.sessionId).toBe('abc')
    expect(s.done).toBe(true)
  })

  it('records context occupancy from a turn that reports a window', () => {
    const s = run([{ t: 'turn_end', session_id: 'a', duration_ms: 1, stop_reason: null,
      usage: { input: 2, output: 5, cached: 0, model: 'm', aux_input: 0, aux_output: 0,
               context_tokens: 26589, context_window: 1000000 } }])
    expect(s.context).toBeCloseTo(0.0265, 3)
  })

  it('leaves context unknown when no window is reported', () => {
    // Unknown must not become 0%, which reads as a conversation with room to
    // spare rather than one we know nothing about.
    const s = run([{ t: 'turn_end', session_id: 'a', duration_ms: 1, stop_reason: null,
      usage: { input: 2, output: 5, cached: 0, model: 'm', aux_input: 0, aux_output: 0,
               context_tokens: 500, context_window: 0 } }])
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
