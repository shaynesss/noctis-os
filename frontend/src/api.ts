// Thin fetch wrapper over the backend — auth (bearer token + Origin, the
// Origin header is set by the browser itself) is mandatory per this
// project's hard constraints, see backend/auth.py.

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
const API_TOKEN = import.meta.env.VITE_API_TOKEN ?? ''

export type Mode = 'dev' | 'learn' | 'research' | 'settings' | 'nightshift'

export interface Job {
  slug: string
  name: string
  stage: string
  status: string
  last_touched: string | null
}

export interface ModeState {
  mode: Mode
  busy: boolean
  last_touched: string | null
  jobs?: Job[]
  // mode-specific ambient fields (deep_due, adopt_counts, triggers, inbox, ...)
  [key: string]: unknown
}

export interface InboxItem {
  slug: string
  origin_mode: Mode
  description: string
  rationale: string
  confidence: 'high' | 'low' | null
  staged_at: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  })
  if (!response.ok) {
    throw new Error(`${init?.method ?? 'GET'} ${path} failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function getModeState(mode: Mode): Promise<ModeState> {
  return request(`/mode/${mode}`)
}

export function launchSession(mode: Mode, jobSlug?: string, model?: string) {
  return request<{ launched: boolean; mode: Mode; surface: string }>('/session/launch', {
    method: 'POST',
    body: JSON.stringify({ mode, job_slug: jobSlug, model }),
  })
}

export function getInbox(): Promise<InboxItem[]> {
  return request('/nightshift/inbox')
}

export function getInboxItem(itemId: string): Promise<InboxItem & { proposal: string }> {
  return request(`/nightshift/inbox/${itemId}`)
}

export function acceptInboxItem(itemId: string) {
  return request(`/nightshift/inbox/${itemId}/accept`, { method: 'POST' })
}

export function rejectInboxItem(itemId: string) {
  return request(`/nightshift/inbox/${itemId}/reject`, { method: 'POST' })
}
