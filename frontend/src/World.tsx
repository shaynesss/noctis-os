// Persistent world screen — single scene, no routing, five character sprites
// idling on the locked peak-dusk cloud-bed backdrop. See SPEC.md PRD
// "Persistent world screen" / assets/world/README.md for footing coordinates.
import { useEffect, useState } from 'react'
import { getHealthStrip, getModeState, type HealthStrip, type Mode, type ModeState } from './api'
import { MODE_META, MODE_ORDER } from './modes'

// Footing coordinates locked in assets/world/README.md (x-frac / y-frac).
const FOOTING: Record<Mode, { leftPct: number; topPct: number }> = {
  dev: { leftPct: 15.0, topPct: 64.2 },
  learn: { leftPct: 25.9, topPct: 67.6 },
  research: { leftPct: 44.3, topPct: 52.1 },
  settings: { leftPct: 58.7, topPct: 60.5 },
  nightshift: { leftPct: 77.2, topPct: 60.8 },
}

export const POLL_INTERVAL_MS = 15_000

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const deltaMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(deltaMs / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

// Ambient world badges are intentionally minimal per Interface.md's Views
// section: "busy/idle, count badges where relevant (due reviews for Noctua,
// pending inbox items for Echo)" — the richer per-mode stat blocks (Vesper's
// adopt/inquiry counts, Custos's trigger badges) live in the profile
// overlay, not on the world sprite itself.
function ambientBadge(mode: Mode, state: ModeState | undefined): number | null {
  if (!state) return null
  if (mode === 'learn') return typeof state.deep_due === 'number' ? state.deep_due : null
  if (mode === 'nightshift') return Array.isArray(state.inbox) ? state.inbox.length : null
  return null
}

interface WorldProps {
  onSelect: (mode: Mode) => void
  activeMode: Mode | null
}

export default function World({ onSelect, activeMode }: WorldProps) {
  const [states, setStates] = useState<Partial<Record<Mode, ModeState>>>({})
  const [health, setHealth] = useState<HealthStrip | null>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      const results = await Promise.allSettled(MODE_ORDER.map((mode) => getModeState(mode)))
      if (cancelled) return
      setStates((prev) => {
        const next = { ...prev }
        results.forEach((result, i) => {
          if (result.status === 'fulfilled') {
            next[MODE_ORDER[i]] = result.value
          }
        })
        return next
      })
    }

    poll()
    const id = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const result = await getHealthStrip()
        if (!cancelled) setHealth(result)
      } catch {
        // Health strip is ambient chrome, not a mode -- a failed poll
        // just leaves the last-known value (or the '—' placeholder)
        // showing rather than surfacing an error to the whole screen.
      }
    }

    poll()
    const id = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return (
    <div id="world" className="world">
      <div className="health-strip">
        <span className="brand">NOCTIS OS</span>
        <span className="health-item">
          <span className={`dot dot-${health?.lint.status ?? 'unknown'}`} />
          lint <b>{(health?.lint.last_run as string | undefined) ?? '—'}</b>
        </span>
        <span className="health-item">
          <span className={`dot dot-${health?.istefox.status ?? 'unknown'}`} />
          istefox <b>{relativeTime(health?.istefox.last_write as string | undefined)}</b>
        </span>
      </div>

      {MODE_ORDER.map((mode) => {
        const meta = MODE_META[mode]
        const footing = FOOTING[mode]
        const state = states[mode]
        const badge = ambientBadge(mode, state)
        const busy = state?.busy ?? false
        const sprite = busy ? meta.busySprite : meta.idleSprite
        return (
          <button
            key={mode}
            type="button"
            className={`character${busy ? ' busy' : ''}${activeMode === mode ? ' active' : ''}`}
            style={{
              left: `${footing.leftPct}%`,
              top: `${footing.topPct}%`,
              ['--accent' as string]: `var(${meta.accentVar})`,
            }}
            onClick={() => onSelect(mode)}
          >
            <span className="sprite-wrap">
              {badge !== null && badge > 0 && <span className="badge">{badge}</span>}
              <img
                src={`/assets/characters/${sprite}.png`}
                alt={`${meta.name}, ${mode} mode, ${busy ? 'active' : 'idle'}`}
              />
            </span>
            <span className="label">
              {meta.name.toUpperCase()} · {mode.toUpperCase()}
            </span>
          </button>
        )
      })}
    </div>
  )
}
