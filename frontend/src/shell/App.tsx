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
import {
  emptyFold, fold, get, runSession,
  type HistorySession, type HistoryTranscript, type Stats as StatsPayload, type Window,
} from './engine'
import { Launcher, type LaunchRequest } from './Launcher'
import {
  Brief, Inbox, Settings,
  type BriefPayload, type ConfigPayload, type InboxPayload,
} from './Panels'
import { Transcript } from './Transcript'
import {
  EMPTY_SESSION, EMPTY_TAB, MODE_ACCENT, MODE_LABEL, PERMISSION_CYCLE,
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
  const [activeTab, setActiveTab] = useState('t0')
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const [permission, setPermission] = useState<Permission>('manual')

  // Tabs and sessions are state rather than the imported constants now that
  // mode entry can create them. The constants are the seed, not the store.
  const [tabs, setTabs] = useState<Tab[]>([EMPTY_TAB])
  const [sessions, setSessions] = useState<Record<string, SessionState>>({ t0: EMPTY_SESSION })
  const [drafts, setDrafts] = useState<Record<string, string>>({ t0: '' })

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
  const sessionsRef = useRef(sessions)
  const permissionRef = useRef(permission)
  tabsRef.current = tabs
  launcherRef.current = launcher
  sessionsRef.current = sessions
  permissionRef.current = permission

  /* One abort per tab. Closing a tab or quitting has to actually stop the
   * stream: an orphaned reader keeps the connection open and the session
   * keeps burning the 5h window with nothing rendering it. */
  const aborts = useRef<Record<string, AbortController>>({})

  // Newest rolling-window report, for the status bar. Null until a session
  // has reported one -- see the backend's known:false for why that is not
  // the same as zero.
  const [limits, setLimits] = useState<{ five_hour: Window; seven_day: Window } | null>(null)

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

  /* One turn: append what was typed, then stream the engine's reply into
   * the same session.
   *
   * The user block is appended before the request rather than on the first
   * response event -- otherwise a slow or failing backend leaves the screen
   * showing nothing happened, and the most likely reaction is to type it
   * again. */
  const turn = async (tabId: string, prompt: string, seed?: SessionState) => {
    // `seed` is how a just-launched session runs its opening prompt: it does
    // not exist in the ref yet, because that follows a render and this is
    // called before one. Waiting a tick instead would be a race that passes
    // on a fast machine.
    const current = seed ?? sessionsRef.current[tabId]
    if (!current || current.busy) return

    const withUser: SessionState = {
      ...current,
      busy: true,
      thinking: null,
      blocks: [...current.blocks, { kind: 'user', text: prompt, at: now() }],
    }
    setSessions((s) => ({ ...s, [tabId]: withUser }))

    const ctrl = new AbortController()
    aborts.current[tabId] = ctrl

    let state = emptyFold(withUser.blocks)
    try {
      for await (const ev of runSession(
        {
          mode: current.mode,
          prompt,
          cwd: current.cwd,
          permission_mode: permissionRef.current,
          // Absent on the first turn, so the engine starts a session; present
          // afterwards, so the rest continue it instead of forgetting.
          resume_id: current.engineId,
        },
        ctrl.signal,
      )) {
        state = fold(state, ev)
        if (ev.t === 'limits') setLimits(ev)
        // Written on every event rather than batched: the point of streaming
        // is that the transcript moves while the model works.
        setSessions((s) => ({
          ...s,
          [tabId]: {
            ...s[tabId],
            blocks: state.blocks,
            thinking: state.thinking,
            engineId: state.sessionId ?? s[tabId].engineId,
          },
        }))
      }
    } finally {
      // In `finally` so an abort or a throw cannot strand a session as
      // permanently busy, which would lock its composer with no way back.
      delete aborts.current[tabId]
      setSessions((s) => ({ ...s, [tabId]: { ...s[tabId], busy: false, thinking: null } }))
    }
  }

  // Sending from a panel takes you to the conversation it went to. Leaving
  // you on Settings while a reply arrives somewhere unseen would be worse
  // than the extra navigation.
  const send = () => {
    const prompt = (drafts[composerTab] ?? '').trim()
    if (!prompt) return
    setDrafts({ ...drafts, [composerTab]: '' })
    if (!inChat) {
      setActiveTab(composerTab)
      setView('chat')
    }
    void turn(composerTab, prompt)
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
    // The provenance block only; the opening prompt is appended by `turn`,
    // so a launched session and a typed one build their transcript the same
    // way rather than through two paths that can drift.
    setSessions({ ...sessions, [id]: { mode: req.mode, cwd: req.cwd, blocks, draft: '' } })
    setDrafts({ ...drafts, [id]: '' })
    setActiveTab(id)
    setView('chat')
    setLauncher(null)
    composerRef.current?.focus()

    void turn(id, req.prompt, { mode: req.mode, cwd: req.cwd, blocks, draft: '' })
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

  /* Reopen the last few conversations on launch.
   *
   * The engine's process outlives the web view, and the store outlives both,
   * so a closed window should not lose work. Only resumable conversations
   * become tabs -- one that died on spawn is readable history, not somewhere
   * you can type, and a tab you cannot continue is a trap.
   *
   * The empty General tab stays first regardless, so there is always
   * somewhere to start even on a fresh install or with the backend down. */
  useEffect(() => {
    let live = true
    void (async () => {
      const listed = await get<{ sessions: HistorySession[] }>('/v2/sessions/history?limit=6')
      if (!live || !listed) return
      const open = listed.sessions.filter((s) => s.resumable).slice(0, 4)
      const loaded = await Promise.all(
        open.map((s) => get<HistoryTranscript>(`/v2/sessions/history/${s.id}`)),
      )
      if (!live) return

      const nextTabs: Tab[] = []
      const nextSessions: Record<string, SessionState> = {}
      const labels = labelFor(open)
      loaded.forEach((full, i) => {
        if (!full || full.blocks.length === 0) return
        const meta = open[i]
        const id = `h${meta.id}`
        nextTabs.push({ id, mode: meta.mode, label: labels[i] })
        nextSessions[id] = {
          mode: meta.mode,
          blocks: full.blocks,
          draft: '',
          cwd: meta.cwd ?? '~',
          engineId: meta.engine_id ?? undefined,
        }
      })
      if (nextTabs.length === 0) return
      setTabs([EMPTY_TAB, ...nextTabs])
      setSessions((s) => ({ ...s, ...nextSessions }))
      setDrafts((d) => ({ ...d, ...Object.fromEntries(nextTabs.map((t) => [t.id, ''])) }))
    })()
    return () => {
      live = false
    }
  }, [])

  // Focus the composer on mount. Without it the document has no keyboard
  // focus until something is clicked, so window-level shortcuts appear
  // broken until you happen to click -- which reads as the shortcut being
  // conditional rather than the window being unfocused. Landing in the input
  // is also where you want to be.
  useEffect(() => {
    composerRef.current?.focus()
  }, [])

  // Abort every live stream when the shell goes away. Without this the
  // window can close on running readers, which keeps the connections open.
  useEffect(() => {
    const live = aborts.current
    return () => Object.values(live).forEach((c) => c.abort())
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
          <Transcript blocks={session.blocks} accent={accent} thinking={session.thinking} />
        ) : (
          <Pane view={view} limits={limits} />
        )}

        </div>
      </div>

      <BottomBar limits={limits}>
        <Composer
            ref={composerRef}
            mode={composerMode}
            value={drafts[composerTab] ?? ''}
            onChange={(v) => setDrafts({ ...drafts, [composerTab]: v })}
            onSend={send}
            busy={sessions[composerTab].busy}
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
function Pane({ view, limits }: { view: string; limits?: { five_hour: Window; seven_day: Window } | null }) {
  if (view === 'stats') return <Stats limits={limits} />
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[840px] px-8 pb-8 pt-7">
        {view === 'brief' && <Fetched<BriefPayload> path="/v2/brief" what="the brief" render={(d) => <Brief data={d} />} />}
        {view === 'inbox' && <Fetched<InboxPayload> path="/v2/inbox" what="the inbox" render={(d) => <Inbox data={d} />} />}
        {view === 'settings' && <Fetched<ConfigPayload> path="/v2/config" what="settings" render={(d) => <Settings data={d} />} />}
      </div>
    </div>
  )
}

/** Load a route, then render it. Loading, loaded and unreachable are three
 *  states: an empty panel that means "the backend is down" must not look
 *  like one that means "you have nothing waiting". */
function Fetched<T>({
  path,
  what,
  render,
}: {
  path: string
  what: string
  render: (data: T) => React.ReactNode
}) {
  const data = useFetched<T>(path)
  if (data === false) return <Unreachable what={what} />
  if (data === null)
    return (
      <div className="rounded-[3px] border border-line bg-surface px-4 py-[13px] text-[12.5px] text-ink-faint">
        Loading…
      </div>
    )
  return <>{render(data)}</>
}

/** Fetch a route once on mount. `null` while loading, `false` when the
 *  request failed -- three states, because "loading" and "the backend is
 *  down" must not render the same way. */
function useFetched<T>(path: string): T | null | false {
  const [data, setData] = useState<T | null | false>(null)
  useEffect(() => {
    let live = true
    void get<T>(path).then((d) => live && setData(d ?? false))
    return () => {
      live = false
    }
  }, [path])
  return data
}

/** Shown wherever a panel's data could not be loaded. Says what failed and
 *  what to do about it, rather than rendering an empty state that looks like
 *  "you have no data" when it means "nothing was asked". */
function Unreachable({ what }: { what: string }) {
  return (
    <div className="rounded-[3px] border border-line bg-surface px-4 py-[13px] text-[12.5px] text-ink-dim">
      Could not load {what}. The backend is not responding on{' '}
      <code className="font-mono text-[11.5px] text-ink-faint">localhost:8000</code>.
    </div>
  )
}

const fmt = (n: number) => n.toLocaleString()

function Stats({ limits }: { limits?: { five_hour: Window; seven_day: Window } | null }) {
  const stats = useFetched<StatsPayload>('/v2/sessions/stats')
  const bar = (pct: number) => (pct < 60 ? 'var(--color-good)' : pct < 85 ? 'var(--color-noctua)' : 'var(--color-faber)')

  /* The rolling windows are the only numbers here that govern a decision --
   * whether there is room to start another session -- so they are shown only
   * when a session has actually reported them. The engine sends them during
   * a run and not before, so "no sessions yet" genuinely has nothing to
   * show, and inventing a plausible number would be worse than a blank. */
  const windows = limits
    ? [
        { label: '5-hour window', pct: Math.round(limits.five_hour.used * 100),
          sub: `resets ${resetIn(limits.five_hour.resets_at)}` },
        { label: '7-day window', pct: Math.round(limits.seven_day.used * 100),
          sub: `resets ${resetIn(limits.seven_day.resets_at)}` },
      ]
    : null

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[840px] px-8 pb-8 pt-7">
        <h2 className="m-0 mb-[14px] font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">
          Usage
        </h2>

        {windows ? (
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
        ) : (
          <div className="mb-[10px] rounded-[3px] border border-line bg-surface px-4 py-[13px] text-[12.5px] text-ink-dim">
            The engine reports the rolling windows during a session. Run one and they appear here.
          </div>
        )}

        <Activity days={stats ? stats.activity : []} />

        <h2 className="m-0 mb-[14px] mt-7 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">
          Lifetime tokens
        </h2>

        {stats === false ? (
          <Unreachable what="usage history" />
        ) : stats === null ? (
          <div className="rounded-[3px] border border-line bg-surface px-4 py-[13px] text-[12.5px] text-ink-faint">
            Loading…
          </div>
        ) : (
          <>
            <div className="rounded-[3px] border border-line bg-surface px-4 py-[14px]">
              <div className="mb-4 flex items-baseline gap-[9px]">
                <b className="font-mono text-[29px] font-bold tabular-nums tracking-[-0.02em] text-ink">
                  {fmt(stats.lifetime.input + stats.lifetime.output)}
                </b>
                <span className="font-mono text-[11px] text-ink-faint">
                  total{stats.lifetime.since ? ` · since ${stats.lifetime.since.slice(0, 10)}` : ''}
                  {' · '}
                  {fmt(stats.lifetime.turns)} turns
                </span>
              </div>
              <div className="grid grid-cols-[auto_1fr_auto] items-center gap-x-[14px] gap-y-[9px] font-mono text-[11.5px]">
                <Row label="input" value={stats.lifetime.input} tone="var(--color-ink-dim)" />
                <Row label="output" value={stats.lifetime.output} tone="var(--color-faber)" />
                <Row label="cache read" value={stats.lifetime.cached} tone="var(--color-good)" />
              </div>

              {/* Shown rather than folded into the totals above. The CLI runs
                  small background tasks on a cheaper tier, and on a measured
                  turn that was 899 of 901 input tokens -- so a page that
                  reported only the model you chose would be wrong by two
                  orders of magnitude while looking perfectly reasonable. */}
              {stats.lifetime.aux_input > 0 && (
                <div className="mt-[13px] flex items-baseline gap-2 border-t border-line pt-[11px] font-mono text-[11.5px]">
                  <span className="text-ink-dim">of which background tier</span>
                  <span className="tabular-nums text-ink">
                    {fmt(stats.lifetime.aux_input + stats.lifetime.aux_output)}
                  </span>
                  <span className="text-ink-faint">
                    ({Math.round(
                      ((stats.lifetime.aux_input + stats.lifetime.aux_output) /
                        Math.max(1, stats.lifetime.input + stats.lifetime.output)) * 100,
                    )}%)
                  </span>
                </div>
              )}
            </div>

            {stats.by_mode.length > 0 && (
              <>
                <h2 className="m-0 mb-[14px] mt-7 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">
                  By mode
                </h2>
                <div className="rounded-[3px] border border-line bg-surface px-4 py-[6px]">
                  {stats.by_mode.map((m, i) => {
                    const top = Math.max(...stats.by_mode.map((x) => x.input + x.output))
                    const total = m.input + m.output
                    return (
                      <div
                        key={m.mode}
                        className={`grid grid-cols-[minmax(96px,1fr)_minmax(0,2.4fr)_auto] items-center gap-4 py-[11px] ${
                          i ? 'border-t border-line' : ''
                        }`}
                      >
                        <span className="flex items-center gap-[8px] text-[12.5px] text-ink">
                          <span
                            className="h-[8px] w-[8px] shrink-0 rounded-[1px]"
                            style={{ background: MODE_ACCENT[m.mode as Mode] ?? 'var(--color-ink-dim)' }}
                          />
                          {MODE_LABEL[m.mode as Mode] ?? m.mode}
                        </span>
                        <div className="h-[6px] overflow-hidden rounded-sm border border-line bg-ground">
                          <div
                            className="h-full rounded-sm"
                            style={{
                              width: `${Math.round((total / Math.max(1, top)) * 100)}%`,
                              background: MODE_ACCENT[m.mode as Mode] ?? 'var(--color-ink-dim)',
                            }}
                          />
                        </div>
                        <span className="text-right font-mono text-[11.5px] tabular-nums text-ink-dim">
                          {fmt(total)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

/** "in 2h 40m" from a unix timestamp. */
function resetIn(epoch: number): string {
  const mins = Math.max(0, Math.round((epoch * 1000 - Date.now()) / 60000))
  if (mins < 60) return `in ${mins}m`
  const h = Math.floor(mins / 60)
  return `in ${h}h ${mins % 60}m`
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

/** Tab labels for a set of restored conversations.
 *
 * Directory name first, because that is how you actually think about a
 * session ("the noctis-os one"). But several sessions in one project share a
 * directory, and four tabs reading "General · noctis-os" name nothing at
 * all -- so a label is only kept when it is unique, and repeats fall back to
 * the opening prompt, which is what actually tells them apart.
 *
 * Computed over the whole set rather than per session, since uniqueness is
 * not a property any one of them has on its own.
 */
function labelFor(sessions: { mode: Mode; cwd: string | null; title: string }[]): string[] {
  const dirs = sessions.map((s) => s.cwd?.split('/').filter(Boolean).pop() ?? '')
  const seen = new Map<string, number>()
  dirs.forEach((d, i) => seen.set(`${sessions[i].mode}/${d}`, (seen.get(`${sessions[i].mode}/${d}`) ?? 0) + 1))

  return sessions.map((s, i) => {
    const unique = (seen.get(`${s.mode}/${dirs[i]}`) ?? 0) === 1
    const tail = unique && dirs[i] ? dirs[i] : truncate(s.title)
    return `${MODE_LABEL[s.mode]} · ${tail}`
  })
}

const truncate = (s: string) => (s.length > 22 ? `${s.slice(0, 22)}…` : s)
