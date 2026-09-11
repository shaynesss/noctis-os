/* The shell's half of the orchestrator connection.
 *
 * Three things live here: the wire types (mirroring backend/orchestrator/
 * wire.py, which is the contract), an SSE reader, and the reducer that folds
 * a stream of events into transcript blocks.
 *
 * The reducer is pure and separately tested. It is the only place that knows
 * a hundred TextDeltas are one paragraph and that a tool result belongs to a
 * call that arrived earlier -- get it wrong and the transcript is subtly
 * wrong in ways no type checker can see.
 */
import type { Block, Mode } from './domain'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
const API_TOKEN = import.meta.env.VITE_API_TOKEN ?? ''

/* ------------------------------------------------------------------ wire */
/* Mirrors backend/orchestrator/wire.py. If a field name changes there, it
 * changes here -- that file's tests assert these exact names so the break is
 * loud on the backend rather than silent in the UI. */
export type WireEvent =
  | { t: 'start'; session_id: string; model: string; cwd: string; tools: string[] }
  | { t: 'text'; text: string }
  | { t: 'thinking'; text: string; tokens: number }
  | { t: 'thinking_progress'; tokens: number }
  | { t: 'tool_call'; id: string; name: string; summary: string }
  | { t: 'tool_result'; id: string; content: string; truncated: boolean; is_error: boolean }
  | { t: 'limits'; five_hour: Window; seven_day: Window; using_overage: boolean }
  | { t: 'context'; tokens: number }
  | { t: 'turn_end'; session_id: string; duration_ms: number; stop_reason: string | null
      usage: { input: number; output: number; cached: number; model: string
               aux_input: number; aux_output: number
               context_window: number } }
  | { t: 'error'; message: string; fatal: boolean }

export interface Window {
  used: number
  resets_at: number
}

export interface LaunchRequest {
  mode: Mode
  prompt: string
  cwd: string
  permission_mode: string
  resume_id?: string
  images?: { media_type: string; data: string }[]
  /** Per-session model override; the mode's default when absent. */
  model?: string
  /** The server supplies the prompt: a mode session opened with nothing
   *  typed, so it runs its own session-start routine. */
  opener?: boolean
}

/* ------------------------------------------------------------------ SSE */

/** Split a byte stream into SSE `data:` payloads.
 *
 * Hand-rolled rather than using EventSource: every route requires a bearer
 * token and EventSource cannot set headers, so this reads a POST's body
 * instead. Chunk boundaries fall anywhere, including mid-frame and even
 * mid-UTF-8-character, so the decoder streams and the buffer only yields on
 * a complete frame terminator.
 */
export async function* readSSE(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<WireEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    for (;;) {
      if (signal?.aborted) return
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let cut: number
      while ((cut = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, cut)
        buffer = buffer.slice(cut + 2)
        const line = frame.split('\n').find((l) => l.startsWith('data: '))
        if (!line) continue
        try {
          yield JSON.parse(line.slice(6)) as WireEvent
        } catch {
          // One malformed frame must not kill a live session: the next one
          // is very likely fine, and a dead transcript is a worse failure
          // than a missing line in it.
        }
      }
    }
  } finally {
    // Releasing matters on abort: without it the underlying connection can
    // stay open after the tab is gone, and the session keeps burning the
    // 5h window with nothing reading it.
    reader.releaseLock()
  }
}

/** Start or resume a session, yielding events as they arrive. */
export async function* runSession(
  req: LaunchRequest,
  signal?: AbortSignal,
): AsyncGenerator<WireEvent> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/v2/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${API_TOKEN}` },
      body: JSON.stringify(req),
      signal,
    })
  } catch (e) {
    // The backend being down is the ordinary case during development, and
    // it must read as an engine error in the transcript rather than an
    // unhandled rejection in the console.
    yield { t: 'error', message: `cannot reach backend: ${(e as Error).message}`, fatal: true }
    return
  }

  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => '')
    yield { t: 'error', message: `backend ${res.status}: ${detail.slice(0, 300)}`, fatal: true }
    return
  }

  yield* readSSE(res.body, signal)
}

/* -------------------------------------------------------------- reducer */

export interface Fold {
  blocks: Block[]
  sessionId: string | null
  /** The model the engine says it ran, not the one we asked for. */
  model: string | null
  /** 0-1 of the context window, null until both halves are known. */
  context: number | null
  /** Prompt size of the most recent API call — occupancy right now. */
  contextTokens: number | null
  /** Window size, which only the turn_end event reports. Remembered across
   *  turns: it is a property of the model, not of the turn. */
  contextWindow: number | null
  /** Live thinking-token estimate; null when not currently reasoning. */
  thinking: number | null
  done: boolean
}

export const emptyFold = (blocks: Block[] = []): Fold => ({
  blocks,
  sessionId: null,
  model: null,
  context: null,
  contextTokens: null,
  contextWindow: null,
  thinking: null,
  done: false,
})

/** Fold one event into the transcript. Pure: returns new state, mutates none.
 *
 * The append-vs-extend decisions are the whole point. Text arrives as many
 * small deltas that are one paragraph; a tool result arrives long after its
 * call and has to find it by id. */
export function fold(state: Fold, e: WireEvent): Fold {
  switch (e.t) {
    case 'start':
      /* The engine reports its own model here and again in the billing
       * record. Keeping it is the difference between the UI showing what
       * ran and showing what it asked for — and the session itself cannot
       * tell you, because a model has no introspective access to its own
       * weights. This is the only authoritative answer available. */
      return { ...state, sessionId: e.session_id, model: e.model }

    case 'text': {
      // Extend the trailing text block rather than pushing one per delta --
      // otherwise every few characters become their own paragraph.
      const last = state.blocks.at(-1)
      if (last?.kind === 'text') {
        const blocks = state.blocks.slice(0, -1)
        blocks.push({ ...last, text: last.text + e.text })
        return { ...state, blocks, thinking: null }
      }
      return { ...state, blocks: [...state.blocks, { kind: 'text', text: e.text }], thinking: null }
    }

    case 'thinking':
      // Text is normally empty by design; the block records that reasoning
      // happened and how much, which is the honest signal available.
      return {
        ...state,
        blocks: [...state.blocks, { kind: 'thinking', tokens: e.tokens, ms: 0 }],
        thinking: null,
      }

    case 'thinking_progress':
      // Deliberately not a block: it is a live counter during a pause, and
      // appending one per tick would fill the transcript with noise that
      // stops being true the moment the next tick lands.
      return { ...state, thinking: e.tokens }

    case 'tool_call':
      return {
        ...state,
        thinking: null,
        blocks: [...state.blocks, {
          kind: 'tool', id: e.id, name: e.name, target: e.summary, meta: 'running', body: '',
        }],
      }

    case 'tool_result': {
      // Match by id, not by position: results can arrive out of order and
      // interleaved with text, so "the most recent tool block" is wrong.
      const i = state.blocks.findIndex((b) => b.kind === 'tool' && b.id === e.id)
      if (i === -1) return state
      const blocks = [...state.blocks]
      const call = blocks[i] as Extract<Block, { kind: 'tool' }>
      blocks[i] = {
        ...call,
        body: e.content,
        meta: e.is_error ? 'error' : e.truncated ? 'truncated' : 'done',
        open: e.is_error || call.open,   // an error opens itself; success stays collapsed
      }
      return { ...state, blocks }
    }

    /* Occupancy, from the API call that just happened.
     *
     * Arrives several times a turn — once per assistant message — so a long
     * tool-running turn shows the window filling as it goes, rather than one
     * jump at the end. The window itself only comes with turn_end, so the
     * ratio stays null until the first turn completes. */
    case 'context': {
      const window = state.contextWindow
      return {
        ...state,
        contextTokens: e.tokens,
        context: window ? e.tokens / window : state.context,
      }
    }

    case 'turn_end': {
      // Remembered across turns: the window is a property of the model, and
      // null must render as unknown rather than as 0%, which would read as a
      // conversation with room to spare.
      const window = e.usage.context_window || state.contextWindow
      return {
        ...state,
        sessionId: e.session_id,
        thinking: null,
        done: true,
        // Confirms it at the end too: what was actually billed.
        model: e.usage.model || state.model,
        contextWindow: window,
        context: window && state.contextTokens
          ? state.contextTokens / window
          : state.context,
      }
    }

    case 'error':
      return {
        ...state,
        thinking: null,
        done: e.fatal || state.done,
        blocks: [...state.blocks, { kind: 'error', message: e.message, fatal: e.fatal }],
      }

    case 'limits':
      // Handled by the status bar, not the transcript.
      return state
  }
}

/* ----------------------------------------------------------------- reads */

export interface Stats {
  lifetime: {
    input: number; output: number; cached: number; cache_write: number; turns: number
    since: string | null; aux_input: number; aux_output: number
  }
  by_mode: { mode: string; input: number; output: number; turns: number }[]
  activity: { day: string; sessions: number }[]
}

/** GET a JSON route. Returns null on any failure rather than throwing.
 *
 * A panel whose data did not load should say so, not crash the shell -- the
 * backend being down is the ordinary case during development, and the whole
 * window going white because Stats could not fetch would be a worse failure
 * than an empty panel. */
export async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { Authorization: `Bearer ${API_TOKEN}` },
      /* A restarting backend does not always refuse a connection -- it can
       * accept and then never answer, and fetch has no timeout of its own.
       * The promise then never settles, so the caller sits in its loading
       * state forever and a panel reads "Loading..." for a reply that is
       * never coming. That is worse than an error, because it looks like
       * work in progress. Ten seconds turns a hang into a failure the UI
       * already knows how to show. */
      signal: AbortSignal.timeout(10_000),
    })
    return res.ok ? ((await res.json()) as T) : null
  } catch {
    return null
  }
}

export interface HistorySession {
  id: number
  mode: Mode
  title: string
  cwd: string | null
  state: string
  engine_id: string | null
  resumable: boolean
  started_at: string
  ended_at: string | null
}

export interface HistoryTranscript {
  id: number
  mode: Mode
  title: string
  cwd: string | null
  engine_id: string | null
  resumable: boolean
  blocks: Block[]
}

/** DELETE a route. Returns whether it succeeded. */
export async function del(path: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${API_TOKEN}` },
    })
    return res.ok
  } catch {
    return false
  }
}

export interface Attachment {
  /** Display index, matching the `[Image #n]` written into the draft. */
  n: number
  media_type: string
  /** Base64, no data: prefix — sent with the turn, never written to disk. */
  data: string
}

/** Read a pasted image into base64.
 *
 * The bytes travel with the turn instead of being uploaded and referenced by
 * path. That removes a file to keep, a path from the transcript, and a Read
 * call standing between the picture and the answer.
 */
export function readImage(blob: Blob): Promise<Attachment | null> {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onerror = () => resolve(null)
    reader.onload = () => {
      const result = String(reader.result)
      const comma = result.indexOf(',')
      // A data: URL is "data:<type>;base64,<data>" — the engine wants only
      // the payload, and the type separately.
      resolve(comma === -1 ? null : { n: 0, media_type: blob.type, data: result.slice(comma + 1) })
    }
    reader.readAsDataURL(blob)
  })
}

/** PUT JSON to a route. Returns whether it succeeded. */
export async function put(path: string, body: unknown): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${API_TOKEN}` },
      body: JSON.stringify(body),
    })
    return res.ok
  } catch {
    return false
  }
}

/** POST JSON. Returns the parsed body, or an error message to show. */
export async function post<T>(path: string, body: unknown): Promise<T | { error: string }> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${API_TOKEN}` },
      body: JSON.stringify(body),
    })
    if (res.ok) return (await res.json()) as T
    // The backend's own detail, not a generic failure: "already exists" and
    // "escapes the vault" need different reactions from the person reading.
    const detail = await res.json().catch(() => null)
    return { error: (detail?.detail as string) ?? `Failed (${res.status})` }
  } catch {
    return { error: 'Cannot reach the backend' }
  }
}
