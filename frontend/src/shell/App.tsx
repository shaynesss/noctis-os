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
import { BottomBar, Composer, Rail, TabBar, TitleStrip } from './Chrome'
import { Launcher, type LaunchRequest } from './Launcher'
import { Transcript } from './Transcript'
import {
  MODE_ACCENT, MODE_LABEL, PERMISSION_CYCLE, SESSIONS, TABS, USAGE,
  type Mode, type Permission, type SessionState, type Tab,
} from './mock'
import './tokens.css'

interface HandoffSource {
  mode: Mode
  label: string
  cwd: string
  carried: string
}

const now = () =>
  new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })

export default function App() {
  const [view, setView] = useState('chat')
  const [activeTab, setActiveTab] = useState('t1')
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const [permission, setPermission] = useState<Permission>('manual')

  // Tabs and sessions are state rather than the imported constants now that
  // mode entry can create them. The constants are the seed, not the store.
  const [tabs, setTabs] = useState<Tab[]>(TABS)
  const [sessions, setSessions] = useState<Record<string, SessionState>>(SESSIONS)
  const [drafts, setDrafts] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(SESSIONS).map(([id, s]) => [id, s.draft])),
  )

  // `null` closed; otherwise a launch, carrying its handoff source if any.
  const [launcher, setLauncher] = useState<null | { handoff?: HandoffSource }>(null)

  /* The key listener is registered once, so its closure would otherwise hold
   * the first render's tabs forever -- Cmd+3 would keep selecting the third
   * tab as it was at mount, not as it is. Refs give the handler the current
   * values without re-registering a capture-phase listener on every state
   * change, which would drop keystrokes during the swap. */
  const tabsRef = useRef(tabs)
  const launcherRef = useRef(launcher)
  const handoffRef = useRef(() => {})
  tabsRef.current = tabs
  launcherRef.current = launcher

  // The panels are not conversations. While one is open the composer binds
  // to General rather than to whichever tab you happened to leave behind --
  // typing into a Faber-labelled box from the Settings page would send to a
  // session you are not looking at, which is the kind of thing you only
  // notice after it has happened.
  const generalTab = tabs.find((t) => t.mode === 'general')!.id
  const inChat = view === 'chat'
  const composerTab = inChat ? activeTab : generalTab

  const session = sessions[activeTab]
  const composerMode = sessions[composerTab].mode
  const accent = MODE_ACCENT[session.mode]

  // Sending from a panel takes you to the conversation it went to. Leaving
  // you on Settings while a reply arrives somewhere unseen would be worse
  // than the extra navigation.
  const send = () => {
    setDrafts({ ...drafts, [composerTab]: '' })
    if (!inChat) {
      setActiveTab(composerTab)
      setView('chat')
    }
  }

  /* A launch always lands in a new tab, whether it came from + or from a
   * handoff. The opening prompt is written into the transcript as a user
   * turn rather than left in the composer, because the session has already
   * been given it -- showing it as an unsent draft would misreport state. */
  const launch = (req: LaunchRequest) => {
    const id = `t${Date.now()}`
    const label = `${MODE_LABEL[req.mode]} · ${req.cwd.split('/').pop()}`
    const blocks: SessionState['blocks'] = []
    if (req.from) {
      blocks.push({
        kind: 'handoff',
        from: req.from.mode,
        fromLabel: req.from.label,
        carried: req.from.carried,
      })
    }
    blocks.push({ kind: 'user', text: req.prompt, at: now() })

    setTabs([...tabs, { id, mode: req.mode, label }])
    setSessions({ ...sessions, [id]: { mode: req.mode, blocks, draft: '' } })
    setDrafts({ ...drafts, [id]: '' })
    setActiveTab(id)
    setView('chat')
    setLauncher(null)
    composerRef.current?.focus()
  }

  /* What a handoff carries is a summary, not the transcript -- so it is
   * built here and shown for editing rather than passed silently. Until the
   * orchestrator is wired this takes the last assistant turn, which is a
   * stand-in for a real summarisation pass and is labelled as one in the
   * dialog. */
  const openHandoff = () => {
    const tab = tabs.find((t) => t.id === activeTab)!
    const lastText = [...session.blocks].reverse().find((b) => b.kind === 'text')
    setLauncher({
      handoff: {
        mode: tab.mode,
        label: tab.label,
        cwd: `~/Developer/${tab.label.split(' · ')[1] ?? ''}`,
        carried: lastText && lastText.kind === 'text' ? lastText.text.slice(0, 240) : '',
      },
    })
  }

  handoffRef.current = openHandoff

  // Cmd+1/2/3 switches tab. Implemented rather than merely labelled: a
  // shortcut shown in the UI that does nothing is a worse lie than the
  // explanatory text it sits next to.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // While the launcher is open it owns the keyboard: its own Cmd+1-5
      // picks a mode, and cycling permission for a session you are not
      // looking at would change something you cannot see.
      if (launcherRef.current) return

      // Shift+Tab cycles permission, the affordance carried over from the
      // CLI's TUI. Wrapping past the end returns to `plan`, so the cycle
      // never strands you at the permissive end.
      if (e.key === 'Tab' && e.shiftKey && !e.metaKey) {
        e.preventDefault()
        e.stopPropagation()
        setPermission((p) => PERMISSION_CYCLE[(PERMISSION_CYCLE.indexOf(p) + 1) % PERMISSION_CYCLE.length])
        return
      }
      if (!e.metaKey || e.altKey) return

      // Cmd+Shift+H hands the active session off to another mode.
      if (e.shiftKey && e.key.toLowerCase() === 'h') {
        e.preventDefault()
        handoffRef.current()
        return
      }
      if (e.shiftKey) return

      // Cmd+T starts a session, matching every tabbed app on the machine.
      if (e.key.toLowerCase() === 't') {
        e.preventDefault()
        setLauncher({})
        return
      }

      const i = ['1', '2', '3'].indexOf(e.key)
      if (i === -1 || !tabsRef.current[i]) return
      e.preventDefault()
      setActiveTab(tabsRef.current[i].id)
      setView('chat')
      composerRef.current?.focus()
    }
    // Capture phase, not bubble. On bubble, focus traversal and any focused
    // control get the Tab first, so the shortcut only appeared to work from
    // wherever happened not to consume it. Capture runs before all of that,
    // which is what makes it genuinely global -- click anywhere, it works.
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [])

  // Focus the composer on mount. Without it the document has no keyboard
  // focus until something is clicked, so window-level shortcuts appear
  // broken until you happen to click -- which reads as the shortcut being
  // conditional rather than the window being unfocused. Landing in the input
  // is also where you want to be.
  useEffect(() => {
    composerRef.current?.focus()
  }, [])

  return (
    <div className="relative flex h-full flex-col" style={{ ['--accent' as string]: accent }}>
      <TitleStrip />

      <div className="flex min-h-0 flex-1">
        <Rail view={view} onView={setView} />

        <div className="flex min-w-0 flex-1 flex-col">
        <TabBar
          tabs={tabs}
          active={activeTab}
          onSelect={(id) => {
            setActiveTab(id)
            setView('chat')
          }}
          onNew={() => setLauncher({})}
          onHandoff={openHandoff}
        />

        {view === 'chat' ? (
          <Transcript blocks={session.blocks} accent={accent} />
        ) : (
          <Pane view={view} />
        )}

        </div>
      </div>

      <BottomBar>
        <Composer
            ref={composerRef}
            mode={composerMode}
            value={drafts[composerTab] ?? ''}
            onChange={(v) => setDrafts({ ...drafts, [composerTab]: v })}
            onSend={send}
            permission={permission}
            onCyclePermission={() =>
              setPermission(PERMISSION_CYCLE[(PERMISSION_CYCLE.indexOf(permission) + 1) % PERMISSION_CYCLE.length])
            }
        />
      </BottomBar>

      {launcher && (
        <Launcher
          handoff={launcher.handoff}
          onLaunch={launch}
          onClose={() => {
            setLauncher(null)
            composerRef.current?.focus()
          }}
        />
      )}
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
