/* The shell's connection to the backend: reads, writes, and the shapes
 * they return in.
 *
 * This used to hold the other half of the orchestrator too -- the SSE
 * reader and the reducer that folded stream events into transcript blocks.
 * A session is a real terminal now and renders itself, so what remains is
 * the ordinary HTTP surface: panels, history, stats, and the terminal's own
 * spawn arguments.
 */
import type { Block, Mode } from './domain'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
const API_TOKEN = import.meta.env.VITE_API_TOKEN ?? ''

/* Rolling-window shape, shared by /limits and the status bar. */
export interface Window {
  used: number
  resets_at: number
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
/** Why a GET produced no data. `offline` is nothing on the socket; `error` is
 *  a backend that answered, and said no. */
export type GetFailure = { ok: false; kind: 'offline' | 'error'; status?: number }
export type GetResult<T> = { ok: true; data: T } | GetFailure

/** GET a route, distinguishing "could not reach it" from "it returned an error".
 *
 * Collapsing the two is how a crashing route came to be reported as an
 * unreachable backend: ⌘K told you the socket was dead while /v2/search was
 * up and returning 500 on every concurrent request, which sent the search for
 * the cause in exactly the wrong direction. Anything that renders a cause to
 * a person should use this rather than `get`.
 */
export async function getResult<T>(path: string): Promise<GetResult<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { Authorization: `Bearer ${API_TOKEN}` },
      signal: AbortSignal.timeout(10_000),
    })
    if (!res.ok) return { ok: false, kind: 'error', status: res.status }
    return { ok: true, data: (await res.json()) as T }
  } catch {
    // fetch only throws for a transport failure or the timeout above, so
    // there is genuinely nothing answering at the other end.
    return { ok: false, kind: 'offline' }
  }
}

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
