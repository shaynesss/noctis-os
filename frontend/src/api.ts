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
  flagged?: boolean
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

export interface HealthItem {
  status: 'ok' | 'stale' | 'unknown'
  [key: string]: unknown
}

export interface HealthStrip {
  lint: HealthItem
  istefox: HealthItem
}

export interface HistoryEntry {
  timestamp: string
  decision: 'accepted' | 'rejected'
  detail?: string | null
  slug: string
  origin_mode: Mode
  description: string
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

export function getJobLog(mode: Mode, slug: string, lines = 20): Promise<{ lines: string[] }> {
  return request(`/mode/${mode}/jobs/${slug}/log?lines=${lines}`)
}

export function launchSession(mode: Mode, jobSlug?: string, model?: string) {
  return request<{ launched: boolean; mode: Mode; surface: string }>('/session/launch', {
    method: 'POST',
    body: JSON.stringify({ mode, job_slug: jobSlug, model }),
  })
}

export function createJob(mode: Mode, slug: string, name: string, projectPath?: string, notes?: string) {
  return request<Job>(`/mode/${mode}/jobs`, {
    method: 'POST',
    body: JSON.stringify({ slug, name, project_path: projectPath, notes }),
  })
}

export function updateJob(
  mode: Mode,
  slug: string,
  update: { stage?: string; status?: string; track?: string; flagged?: boolean; project_path?: string },
) {
  return request<Job>(`/mode/${mode}/jobs/${slug}`, {
    method: 'PATCH',
    body: JSON.stringify(update),
  })
}

export function getHealthStrip(): Promise<HealthStrip> {
  return request('/health/strip')
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

export function getNightshiftHistory(limit = 50): Promise<HistoryEntry[]> {
  return request(`/nightshift/history?limit=${limit}`)
}

export function getArchivedProposal(itemId: string): Promise<{ slug: string; proposal: string }> {
  return request(`/nightshift/archive/${itemId}`)
}

export const LODGE_CATEGORIES = [
  'Interactables',
  'Navigation',
  'Hero section',
  'Typography',
  'Color themes/palette',
  'Icons',
  'Animation patterns',
] as const

export type LodgeCategory = (typeof LODGE_CATEGORIES)[number]

export interface LodgeEntry {
  slug: string
  name: string
  category: string
  tags: string[]
  source: string
  projects_used: string[]
  superseded_by: string | null
  has_preview: boolean
}

export interface LodgeEntryDetail extends LodgeEntry {
  body: string
}

export interface LodgeInboxItem {
  slug: string
  link: string
  note: string
  added_at: string
}

export function getLodgeEntries(category?: string, tag?: string): Promise<LodgeEntry[]> {
  const params = new URLSearchParams()
  if (category) params.set('category', category)
  if (tag) params.set('tag', tag)
  const qs = params.toString()
  return request(`/design-lodge/entries${qs ? `?${qs}` : ''}`)
}

export function getLodgeEntry(slug: string): Promise<LodgeEntryDetail> {
  return request(`/design-lodge/entries/${slug}`)
}

export function createLodgeEntry(entry: {
  slug: string
  name: string
  category: string
  tags?: string[]
  source?: string
  code?: string
  reference?: string
  projects_used?: string[]
}): Promise<LodgeEntry> {
  return request('/design-lodge/entries', { method: 'POST', body: JSON.stringify(entry) })
}

export function updateLodgeEntry(
  slug: string,
  update: Partial<{
    name: string
    category: string
    tags: string[]
    source: string
    code: string
    reference: string
    projects_used: string[]
    superseded_by: string | null
  }>,
): Promise<LodgeEntry> {
  return request(`/design-lodge/entries/${slug}`, { method: 'PATCH', body: JSON.stringify(update) })
}

export function getLodgeInbox(): Promise<LodgeInboxItem[]> {
  return request('/design-lodge/inbox')
}

export function addLodgeInboxItem(link: string, note?: string): Promise<LodgeInboxItem> {
  return request('/design-lodge/inbox', { method: 'POST', body: JSON.stringify({ link, note }) })
}

export function processLodgeInboxItem(slug: string): Promise<{ processed: string }> {
  return request(`/design-lodge/inbox/${slug}/process`, { method: 'POST' })
}

// Fetched as an authenticated blob, never a token-in-URL <img src> -- the
// bearer token is a header, not something safe to expose in a query string.
export async function getLodgePreviewUrl(slug: string): Promise<string | null> {
  const response = await fetch(`${API_BASE}/design-lodge/entries/${slug}/preview`, {
    headers: { Authorization: `Bearer ${API_TOKEN}` },
  })
  if (!response.ok) return null
  const blob = await response.blob()
  return URL.createObjectURL(blob)
}

export function uploadLodgePreview(slug: string, imageBase64: string) {
  return request<{ slug: string; has_preview: boolean }>(`/design-lodge/entries/${slug}/preview`, {
    method: 'POST',
    body: JSON.stringify({ image_base64: imageBase64 }),
  })
}
