/* Noctis v2 shell — Stage 2 item 3.
 *
 * Built against mocked data per dev.md §3.0: screens first, and only once
 * approved does the UI's data shape become the API contract. Nothing here
 * calls the backend yet, deliberately.
 *
 * v1's World.tsx / ProfileOverlay.tsx are left in place, unreferenced, until
 * the Stage 2 cutover removes them with their routes — the same
 * "move the new thing, leave the old until it can go cleanly" pattern the
 * mode merge used. */
import { useEffect, useRef, useState } from 'react'
import { Activity } from './Activity'
import { Composer, Rail, StatusBar, TabBar } from './Chrome'
import { Transcript } from './Transcript'
import { MODE_ACCENT, PERMISSION_CYCLE, SESSIONS, TABS, USAGE, type Permission } from './mock'
import './tokens.css'

export default function App() {
  const [view, setView] = useState('chat')
  const [activeTab, setActiveTab] = useState('t1')
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const [permission, setPermission] = useState<Permission>('manual')
  const [drafts, setDrafts] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(SESSIONS).map(([id, s]) => [id, s.draft])),
  )

  const session = SESSIONS[activeTab]
  const accent = MODE_ACCENT[session.mode]

  // Cmd+1/2/3 switches tab. Implemented rather than merely labelled: a
  // shortcut shown in the UI that does nothing is a worse lie than the
  // explanatory text it sits next to.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Shift+Tab cycles permission, the affordance carried over from the
      // CLI's TUI. Wrapping past the end returns to `plan`, so the cycle
      // never strands you at the permissive end.
      if (e.key === 'Tab' && e.shiftKey && !e.metaKey) {
        e.preventDefault()
        setPermission((p) => PERMISSION_CYCLE[(PERMISSION_CYCLE.indexOf(p) + 1) % PERMISSION_CYCLE.length])
        return
      }
      if (!e.metaKey || e.shiftKey || e.altKey) return
      const i = ['1', '2', '3'].indexOf(e.key)
      if (i === -1 || !TABS[i]) return
      e.preventDefault()
      setActiveTab(TABS[i].id)
      setView('chat')
      composerRef.current?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="flex h-full" style={{ ['--accent' as string]: accent }}>
      <Rail view={view} onView={setView} />

      <div className="flex min-w-0 flex-1 flex-col">
        <TabBar
          tabs={TABS}
          active={activeTab}
          onSelect={(id) => {
            setActiveTab(id)
            setView('chat')
          }}
        />

        {view === 'chat' ? (
          <>
            <Transcript blocks={session.blocks} accent={accent} />
            <Composer
              ref={composerRef}
              mode={session.mode}
              value={drafts[activeTab] ?? ''}
              onChange={(v) => setDrafts({ ...drafts, [activeTab]: v })}
              onSend={() => setDrafts({ ...drafts, [activeTab]: '' })}
              permission={permission}
              onCyclePermission={() =>
                setPermission(PERMISSION_CYCLE[(PERMISSION_CYCLE.indexOf(permission) + 1) % PERMISSION_CYCLE.length])
              }
            />
          </>
        ) : (
          <Pane view={view} />
        )}

        <StatusBar />
      </div>
    </div>
  )
}

/* The non-chat views are stubs at this stage. They exist so the rail is
 * honest -- a nav item that goes nowhere is worse than one that says "not
 * built yet" -- and so the shell's layout is exercised at every width. */
function Pane({ view }: { view: string }) {
  if (view === 'stats') return <Stats />
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[840px] px-8 pt-7">
        <h2 className="m-0 mb-[14px] font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">
          {view}
        </h2>
        <p className="text-ink-dim">Not built yet — Stage 2 items 5–6.</p>
      </div>
    </div>
  )
}

function Stats() {
  const { windows, lifetime } = USAGE
  const bar = (pct: number) => (pct < 60 ? 'var(--color-good)' : pct < 85 ? 'var(--color-noctua)' : 'var(--color-faber)')

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[840px] px-8 pb-8 pt-7">
        <h2 className="m-0 mb-[14px] font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">
          Usage
        </h2>

        <div className="mb-[10px] rounded-[3px] border border-line bg-surface px-4 pb-[6px] pt-1">
          {windows.map((w, i) => (
            <div
              key={w.label}
              className={`grid grid-cols-[minmax(120px,1fr)_minmax(0,2.2fr)_62px] items-center gap-4 py-[13px] ${
                i ? 'border-t border-line' : ''
              }`}
            >
              <div className="min-w-0">
                <div className="mb-[2px] text-[13px] text-ink">{w.label}</div>
                <div className="font-mono text-[10.5px] text-ink-faint">{w.sub}</div>
              </div>
              <div className="h-[6px] overflow-hidden rounded-sm border border-line bg-ground">
                <div className="h-full rounded-sm" style={{ width: `${w.pct}%`, background: bar(w.pct) }} />
              </div>
              <div className="text-right font-mono text-[12px] tabular-nums" style={{ color: bar(w.pct) }}>
                {w.pct}%
              </div>
            </div>
          ))}
        </div>

        <Activity />

        <h2 className="m-0 mb-[14px] mt-7 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">
          Lifetime tokens
        </h2>
        <div className="rounded-[3px] border border-line bg-surface px-4 py-[14px]">
          <div className="mb-4 flex items-baseline gap-[9px]">
            <b className="font-mono text-[29px] font-bold tabular-nums tracking-[-0.02em] text-ink">
              {lifetime.total}
            </b>
            <span className="font-mono text-[11px] text-ink-faint">total · since {lifetime.since}</span>
          </div>
          <div className="grid grid-cols-[auto_1fr_auto] items-center gap-x-[14px] gap-y-[9px] font-mono text-[11.5px]">
            {[
              ['input', lifetime.input, 'var(--color-ink-dim)'],
              ['output', lifetime.output, 'var(--color-faber)'],
              ['cache read', lifetime.cacheRead, 'var(--color-good)'],
              ['cache write', lifetime.cacheWrite, 'var(--color-noctua)'],
            ].map(([label, val, tone]) => (
              <Row key={label as string} label={label as string} value={val as number} tone={tone as string} />
            ))}
          </div>
          {/* The ratio is the diagnostic number on this page -- a drop means
              prompt or context structure has begun thrashing the cache -- but
              it is shown as a stat, not explained. The reasoning belongs in
              the spec, not on screen. */}
          <div className="mt-[13px] flex items-baseline gap-2 border-t border-line pt-[11px] font-mono text-[11.5px]">
            <span className="text-ink-dim">cache hit rate</span>
            <span className="ml-auto tabular-nums text-good">94%</span>
          </div>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, tone }: { label: string; value: number; tone: string }) {
  const pct = Math.max(0.5, (value / 950.5) * 100)
  return (
    <>
      <span className="text-ink-dim">{label}</span>
      <span className="h-[5px] min-w-[60px] overflow-hidden rounded-sm border border-line bg-ground">
        <span className="block h-full" style={{ width: `${pct}%`, background: tone }} />
      </span>
      <span className="text-right tabular-nums text-ink">{value}M</span>
    </>
  )
}
