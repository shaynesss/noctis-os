// Persistent world screen — single scene, no routing, five character sprites
// idling on the locked peak-dusk cloud-bed backdrop. See SPEC.md PRD
// "Persistent world screen" / assets/world/README.md for footing coordinates.
import { useEffect, useState } from 'react'
import { getModeState, type Mode, type ModeState } from './api'
import { MODE_META, MODE_ORDER } from './modes'

// Footing coordinates locked in assets/world/README.md (x-frac / y-frac).
const FOOTING: Record<Mode, { leftPct: number; topPct: number }> = {
  dev: { leftPct: 15.0, topPct: 64.2 },
  learn: { leftPct: 25.9, topPct: 67.6 },
  research: { leftPct: 44.3, topPct: 52.1 },
  settings: { leftPct: 58.7, topPct: 60.5 },
  nightshift: { leftPct: 77.2, topPct: 60.8 },
}

const POLL_INTERVAL_MS = 15_000

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

  return (
    <div id="world" className="world">
      <div className="health-strip">
        <span className="brand">NOCTIS OS</span>
        {/* TODO: wire to a real backend health endpoint (lint/orphan/istefox/
            nightshift-run status) once Settings mode's audit capabilities
            expose one — static for now, not fabricated live data. */}
        <span className="health-item">
          <span className="dot" />
          lint <b>—</b>
        </span>
        <span className="health-item">
          <span className="dot" />
          istefox <b>—</b>
        </span>
      </div>

      {MODE_ORDER.map((mode) => {
        const meta = MODE_META[mode]
        const footing = FOOTING[mode]
        const state = states[mode]
        const badge = ambientBadge(mode, state)
        return (
          <button
            key={mode}
            type="button"
            className={`character${state?.busy ? ' busy' : ''}${activeMode === mode ? ' active' : ''}`}
            style={{
              left: `${footing.leftPct}%`,
              top: `${footing.topPct}%`,
              ['--accent' as string]: `var(${meta.accentVar})`,
            }}
            onClick={() => onSelect(mode)}
          >
            <span className="sprite-wrap">
              {badge !== null && badge > 0 && <span className="badge">{badge}</span>}
              <img src={`/assets/characters/${meta.sprite}.png`} alt={`${meta.name}, ${mode} mode`} />
              <span className="state-dot" />
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
