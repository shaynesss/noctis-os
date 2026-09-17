/* Noctis shell, terminal-first.
 *
 * A session is a real interactive `claude` in a pseudo-terminal, hosted by
 * `Terminal.tsx` and arranged by `Terminals.tsx`. This file owns the
 * arrangement -- which terminals are open, which is showing -- and the
 * chrome around it: rail, panels, palette, launcher, status bar.
 *
 * What used to be here, and is not: a transcript built from `stream-json`
 * events, a composer that sent turns, a permission dialog, a per-turn effort
 * chip. All of that rebuilt the CLI's interactive loop on top of its
 * scripting mode, and the CLI does its own loop better in a terminal.
 * `PTY-MIGRATION.md` is the record; `DOCUMENTATION.md` §22 is the shape.
 */
import { invoke } from '@tauri-apps/api/core'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity } from './Activity'
import { Unreachable } from './Async'
import { BottomBar, RAIL_VIEWS, Rail, RefusedBanner, TitleStrip, type LiveLimits } from './Chrome'
import { del, get, type HistoryTranscript, type Stats as StatsPayload, type Window } from './engine'
import { Launcher, type LaunchRequest } from './Launcher'
import { Palette } from './Palette'
import {
  Beam, ListPriceFact, Settings,
  type BillingPayload, type InboxPayload, type RepoPayload, type RepoTerminal, Repo,
} from './Panels'
import { Reader } from './Reader'
import { Terminals, newSlot, shortenHome, type Slot } from './Terminals'
import { Transcript } from './Transcript'
import { useFetched } from './useFetched'
import { MODE_ACCENT, MODE_LABEL, PANE_COLUMN, recallDismissedRefusal, recallSlots, recallView, rememberDismissedRefusal, rememberSlots, rememberView, type Mode } from './domain'
import './tokens.css'

/** What a terminal's statusLine reports, the parts the shell reads. */
interface TermReport {
  session_id?: string
  /** The CLI writes the transcript on the first message, not at start. An
   *  id with no transcript resumes to "No conversation found". */
  transcript_exists?: boolean
  model?: { id?: string; display_name?: string }
  context_window?: { used_percentage?: number | null }
  workspace?: { current_dir?: string }
  effort?: { level?: string }
}

/* Where a fresh install starts. The vault-native modes belong at the vault
 * root; the launcher decides per mode after that. */
const HOME_CWD = '~/Developer/second-brain'

/** A group of one is no group: clear any group left with a single member. */
export function ungroupSingles(slots: Slot[]): Slot[] {
  const counts = new Map<string, number>()
  for (const s of slots) if (s.group) counts.set(s.group, (counts.get(s.group) ?? 0) + 1)
  return slots.map((s) => (s.group && (counts.get(s.group) ?? 0) < 2 ? { ...s, group: undefined } : s))
}

export function App() {
  // The app opens on Repo (2026-09-15): the commit log is where a piece of
  // work was left, so it is what you open the app to read.
  /* Opens where you left it (2026-09-17). Repo was the landing view while
   * the commit log was new, then Terminal; both were a guess about what you
   * would want next, and what you want next is what you were doing.
   * Terminal is the fallback for a first run or a window that cannot read
   * its storage. */
  const [view, setView] = useState(() => recallView(RAIL_VIEWS, 'terminal'))
  useEffect(() => { rememberView(view) }, [view])

  /* The arrangement. Seeded from what was open last time, each entry
   * carrying the engine session id its terminal reported, so it comes back
   * *resumed* rather than blank. A machine with nothing remembered gets one
   * General terminal, which is the front door. */
  const [slots, setSlots] = useState<Slot[]>(() => {
    const remembered = recallSlots()
    if (remembered.length === 0) return [newSlot('general', HOME_CWD)]
    return remembered.map((r) => newSlot(r.mode, r.cwd, {
      ...(r.id ? { id: r.id } : {}),
      ...(r.group ? { group: r.group } : {}),
      resumeId: r.sessionId,
    }))
  })
  const [active, setActive] = useState<string | null>(() => slots[0]?.id ?? null)
  const slotsRef = useRef(slots)
  const activeRef = useRef(active)
  slotsRef.current = slots
  activeRef.current = active

  const shown = slots.find((s) => s.id === active) ?? slots[0] ?? null
  const mode: Mode = shown?.mode ?? 'general'
  const accent = MODE_ACCENT[mode]

  // Read by `open` without being a dependency of it: the callback identity
  // is what every ⌘-shortcut effect below hangs on.
  const slotCount = useRef(0)
  const maxSlotsRef = useRef(9)

  /* Split: toggle a terminal into or out of the showing terminal's group.
   * Joining moves the tab next to the group so the strip's bracket is one
   * run; leaving clears the group if that leaves it with one member. */
  const split = useCallback((id: string) => {
    setSlots((all) => {
      const anchor = all.find((s) => s.id === activeRef.current) ?? all[0]
      const other = all.find((s) => s.id === id)
      if (!anchor || !other || anchor.id === other.id) return all
      if (anchor.group && anchor.group === other.group) {
        return ungroupSingles(all.map((s) => (s.id === id ? { ...s, group: undefined } : s)))
      }
      const group = anchor.group ?? `g-${anchor.id}`
      const rest = all
        .filter((s) => s.id !== id)
        .map((s) => (s.id === anchor.id ? { ...s, group } : s))
      const after = rest.reduce((last, s, i) => (s.group === group ? i : last), -1)
      const joined = { ...other, group }
      return ungroupSingles([...rest.slice(0, after + 1), joined, ...rest.slice(after + 1)])
    })
    setView('terminal')
  }, [])

  const open = useCallback((slot: Slot) => {
    // The ceiling, kept here too: the launcher and the history view say why
    // before it is reached, and this is what makes "why" never a lie.
    if (slotCount.current >= maxSlotsRef.current) return
    setSlots((all) => [...all, slot])
    setActive(slot.id)
    setView('terminal')
  }, [])

  const close = useCallback((id: string) => {
    /* Closing the slot is what ends the session -- not the terminal's
     * unmount, which also happens on StrictMode's double mount and on a hot
     * reload, neither of which means "stop". Leaving the process would keep
     * a session burning the 5h window with nothing reading it, and counted
     * live under a slot name nothing shows. */
    void invoke('pty_kill', { id }).catch(() => {
      // Killing a session that already exited is not a failure.
    })
    void del(`/v2/sessions/statusline/${encodeURIComponent(id)}`)
    setSlots((all) => {
      const rest = ungroupSingles(all.filter((s) => s.id !== id))
      if (activeRef.current === id) setActive(rest[rest.length - 1]?.id ?? null)
      return rest
    })
  }, [])

  /* Every terminal's newest status-line report, one poll for all of them.
   *
   * Two things read this. The status bar reads the showing terminal's
   * model, context and directory -- what the CLI itself last said, so
   * `/model` inside the terminal moves the bar. And the arrangement writer
   * reads each terminal's session id, which is what a remembered slot
   * needs to come back resumed. The rolling windows ride along on the same
   * cadence: four seconds is the staleness the live counter beside them
   * already accepts. */
  const [reports, setReports] = useState<Record<string, TermReport>>({})
  const [limits, setLimits] = useState<LiveLimits | null>(null)
  const [maxSlots, setMaxSlots] = useState(9)
  maxSlotsRef.current = maxSlots
  slotCount.current = slots.length
  useEffect(() => {
    let alive = true
    const read = () => {
      void get<{ slots: Record<string, TermReport> }>('/v2/sessions/statusline/all')
        .then((d) => { if (alive && d) setReports(d.slots) })
      void get<LiveLimits & { known: boolean }>('/v2/sessions/limits')
        .then((d) => { if (alive && d?.known) setLimits(d) })
      void get<{ max_concurrent: number }>('/v2/sessions')
        .then((d) => { if (alive && d) setMaxSlots(d.max_concurrent) })
    }
    read()
    const id = setInterval(read, 4000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  /* What the inbox holds, for the rail's badge: proposals waiting on a
   * decision. Read on a slow cadence -- Custos stages overnight and a
   * session stages rarely -- and again the moment a decision is made here,
   * so the badge never shows an item that was just dispatched. */
  const [inboxCount, setInboxCount] = useState(0)
  const [inboxTick, setInboxTick] = useState(0)
  useEffect(() => {
    let alive = true
    const read = () => {
      void get<InboxPayload>('/v2/inbox').then((d) => {
        if (alive && d) setInboxCount(d.counts.proposals)
      })
    }
    read()
    const id = setInterval(read, 30_000)
    return () => { alive = false; clearInterval(id) }
  }, [inboxTick])

  /* Strays from before a reload.
   *
   * The PTY registry lives in the Rust process, and a reload of the web
   * view -- ⌘R in development, a recovery from a crashed page -- does not
   * touch it. Slots keep their ids across a reload precisely so their
   * terminals can reattach to the sessions still running under them (see
   * Terminal.tsx). Anything registered under an id no slot came back with
   * is a session nothing will ever show again: 300MB, reporting to the
   * backend under a name nothing displays, counted live, eating the cap.
   * Killed and closed out of the live count here, once, before the
   * four-second poll can count it. */
  const slotsAtMount = useRef(slots)
  useEffect(() => {
    const keep = new Set(slotsAtMount.current.map((s) => s.id))
    void invoke<string[]>('pty_list').then((ids) => {
      for (const id of ids) {
        if (keep.has(id)) continue
        void invoke('pty_kill', { id }).catch(() => {})
        void del(`/v2/sessions/statusline/${encodeURIComponent(id)}`)
      }
    }).catch(() => {
      // Not under Tauri (a browser tab in development): nothing to reap.
    })
  }, [])

  /* Remember the arrangement on every change, not on unload: a crash or a
   * force-quit never fires unload, and those are exactly when losing it
   * hurts. The session id comes from the terminal's own report once it has
   * made one; until then the slot's resume id, if it had one, is the best
   * known. */
  useEffect(() => {
    rememberSlots(slots.map((s) => ({
      id: s.id,
      mode: s.mode,
      cwd: s.cwd,
      ...(s.group ? { group: s.group } : {}),
      /* Only an id that resumes to something. A terminal opened and never
         spoken to has an id and no transcript; remembering it brought the
         slot back to "No conversation found" instead of a fresh session. */
      sessionId: reports[s.id]?.transcript_exists
        ? reports[s.id]?.session_id
        : s.resumeId,
    })))
  }, [slots, reports])

  /* Overlays. Each owns the keyboard while it is open. */
  const [palette, setPalette] = useState(false)
  const [doc, setDoc] = useState<string | null>(null)
  const [launcher, setLauncher] = useState<null | {
    handoff?: { mode: Mode; label: string; cwd: string; carried: string }
  }>(null)
  const [viewing, setViewing] = useState<HistoryTranscript | null>(null)
  const overlayRef = useRef(false)
  overlayRef.current = palette || doc !== null || launcher !== null || viewing !== null

  /* The ceiling is ⌘1–9 and the backend's concurrency cap, whichever is
   * lower. Past it a tenth terminal would exist with no key to reach it and
   * a status bar reading "10 / 9". Every way in -- the launcher, a handoff,
   * resuming from history -- shows this instead of a button that does
   * nothing. */
  const full = slots.length >= maxSlots
    ? `${slots.length} of ${maxSlots} terminals open · ⌘W closes one`
    : undefined

  const launch = useCallback((req: LaunchRequest) => {
    /* A handoff carries a summary the person wrote in the launcher; it
       arrives as the new session's first message rather than through a
       clipboard. An empty launch just opens the terminal and waits. */
    // Only a handoff carries a first message now: the launcher's own
    // opening-prompt box went on 2026-09-16, and a fresh session opens on
    // the backend's prompt instead.
    const prompt = req.from?.carried.trim() || undefined
    open(newSlot(req.mode, req.cwd, { prompt, effort: req.effort, model: req.model }))
    setLauncher(null)
  }, [open])

  const openHistory = useCallback(async (id: number) => {
    const full = await get<HistoryTranscript>(`/v2/sessions/history/${id}`)
    if (full) setViewing(full)
    setPalette(false)
  }, [])

  const resumeHistory = useCallback((t: HistoryTranscript) => {
    if (!t.engine_id) return
    open(newSlot(t.mode, t.cwd ?? HOME_CWD, { resumeId: t.engine_id }))
    setViewing(null)
  }, [open])

  /* Keys.
   *
   * Capture phase, so this sees every key before xterm does -- which is why
   * the first check is whether the key belongs to a terminal. Inside one,
   * everything without ⌘ passes through: Claude Code's TUI uses Shift+Tab,
   * Escape and the arrows for its own menus, and the shell used to steal
   * all three. The reserved set is every ⌘-chord, because those are about
   * the app and not about what is in the terminal. VS Code's split. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (overlayRef.current) {
        // The overlay owns the keyboard; Escape is the one thing handled
        // here, so every overlay closes the same way.
        if (e.key === 'Escape') {
          e.preventDefault()
          setPalette(false); setDoc(null); setLauncher(null); setViewing(null)
        }
        return
      }
      if (!e.metaKey && (e.target as Element | null)?.closest?.('[data-terminal]')) return
      if (!e.metaKey || e.altKey) return

      if (e.shiftKey && e.key.toLowerCase() === 'h') {
        e.preventDefault()
        const s = slotsRef.current.find((x) => x.id === activeRef.current)
        if (s) setLauncher({ handoff: {
          mode: s.mode, label: `${MODE_LABEL[s.mode]} · ${shortenHome(s.cwd)}`,
          cwd: s.cwd, carried: '',
        } })
        return
      }
      if (e.shiftKey) {
        // ⌘⇧-number: split the showing terminal with that one, or unsplit.
        const digit = Number(e.code.replace('Digit', ''))
        if (Number.isInteger(digit) && digit >= 1 && digit <= 9) {
          const target = slotsRef.current[digit - 1]
          if (target) { e.preventDefault(); split(target.id) }
        }
        return
      }
      const k = e.key.toLowerCase()
      /* ⌘R reloads the page, the way it does in a browser.
       *
       * Safe here, and deliberately so: the PTY registry belongs to the Rust
       * process, so a reload does not touch a single running session. Each
       * terminal remounts and `pty_attach` hands it its scrollback and the
       * number of the last frame it already has. That is the same path a
       * crash or a hot reload takes, tested since the PTY migration.
       *
       * It is also the only way to pick up a change to the terminal palette:
       * the theme is built when a terminal is constructed and never updated
       * after, so an open pane keeps the colours it was born with.
       *
       * Bound because a hand reaches for it. Tauri's webview gives no reload
       * of its own in a bundled app, so ⌘R did nothing at all until now. */
      if (k === 'r') { e.preventDefault(); window.location.reload(); return }
      if (k === 'k') { e.preventDefault(); setPalette(true); return }
      if (k === 't') { e.preventDefault(); setLauncher({}); return }
      if (k === 'w') {
        e.preventDefault()
        if (activeRef.current) close(activeRef.current)
        return
      }
      const digit = Number(e.key)
      if (Number.isInteger(digit) && digit >= 1 && digit <= 9) {
        const target = slotsRef.current[digit - 1]
        if (target) { e.preventDefault(); setActive(target.id); setView('terminal') }
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [close, split])

  /* Branch of the showing terminal's directory. Omitted from the bar when
   * the directory is not a repository, which plenty of useful ones are not. */
  const [branch, setBranch] = useState<string | null>(null)
  const cwd = reports[shown?.id ?? '']?.workspace?.current_dir ?? shown?.cwd ?? HOME_CWD
  useEffect(() => {
    let alive = true
    void get<{ branch: string | null }>(`/v2/git?cwd=${encodeURIComponent(cwd)}`)
      .then((d) => { if (alive) setBranch(d?.branch ?? null) })
    return () => { alive = false }
  }, [cwd])

  /* Every open terminal, where it is right now, for the Repo view to group
   * by repository. The directory is the one the CLI last reported -- a
   * session that cd'd is in the directory it cd'd to -- falling back to the
   * one the slot opened in before the first report. */
  const terminals: RepoTerminal[] = slots.map((s, i) => ({
    id: s.id, mode: s.mode, index: i + 1, showing: s.id === shown?.id,
    cwd: reports[s.id]?.workspace?.current_dir ?? s.cwd,
  }))

  /* Overage is the one number that can mean money, and the only thing that
   * raises a banner. Dismissed for this window only, re-armed if it clears
   * and returns. */
  /* One banner at a time, newest first: two models refusing at once is a
   * list nobody reads, and the newest is the one the work just hit. */
  const refused = limits?.refused?.[0] ?? null
  const [dismissedRefusal, setDismissedRefusal] = useState<string | null>(() => recallDismissedRefusal())
  useEffect(() => {
    // A new refusal re-arms the banner: dismissing Fable's says nothing
    // about the next model to stop. The dismissal itself is remembered
    // across reloads, so the same event does not come back every refresh.
    if (refused && dismissedRefusal && dismissedRefusal !== refused.at) setDismissedRefusal(null)
  }, [refused, dismissedRefusal])

  const report = shown ? reports[shown.id] : undefined

  return (
    <div className="relative flex h-full flex-col" style={{ ['--accent' as string]: accent }}>
      <TitleStrip />
      {refused && dismissedRefusal !== refused.at && (
        <RefusedBanner
          refused={refused}
          onDismiss={() => { setDismissedRefusal(refused.at); rememberDismissedRefusal(refused.at) }}
        />
      )}

      <div className="flex min-h-0 flex-1">
        <Rail view={view} onView={setView} badges={{ settings: inboxCount }} />

        <div className="flex min-w-0 flex-1 flex-col">
          {view !== 'terminal' && <Pane view={view} limits={limits} terminals={terminals} onInboxDecided={() => setInboxTick((t) => t + 1)} />}
          {/* Always mounted, shown only on its rail item: a terminal's
              session dies with its component, so it cannot live inside a
              conditional the way the panels do. */}
          <Terminals
            slots={slots}
            active={active}
            accent={accent}
            shownCwd={shortenHome(cwd)}
            hidden={view !== 'terminal'}
            onSelect={(id) => { setActive(id); setView('terminal') }}
            onClose={close}
            onAdd={() => setLauncher({})}
            onReorder={(ids, before) => setSlots((all) => {
              // A block -- one tab or a whole bracket -- keeps its order.
              const moving = all.filter((s) => ids.includes(s.id))
              if (!moving.length || (before && ids.includes(before))) return all
              const rest = all.filter((s) => !ids.includes(s.id))
              const at = before ? rest.findIndex((s) => s.id === before) : -1
              return at < 0 ? [...rest, ...moving] : [...rest.slice(0, at), ...moving, ...rest.slice(at)]
            })}
            onSplit={split}
          />
        </div>
      </div>

      <BottomBar
        limits={limits}
        open={slots.map((s) => s.mode)}
        state={{
          live: { running: slots.length, max: maxSlots },
          cwd: shortenHome(cwd),
          /* What the CLI itself last reported, once it has. Falls back to
             the mode's name for the frame before the first report. */
          model: report?.model?.id ?? report?.model?.display_name ?? MODE_LABEL[mode],
          branch,
          context: report?.context_window?.used_percentage == null
            ? null
            : report.context_window.used_percentage / 100,
        }}
      >
        {null}
      </BottomBar>

      {palette && (
        <Palette
          onOpenSession={(id) => void openHistory(id)}
          onOpenDoc={(p) => { setDoc(p); setPalette(false) }}
          onDelete={(id) => {
            void del(`/v2/sessions/history/${id}`).then((ok) => {
              if (!ok) console.error(`[noctis] could not delete session ${id}; it is still in history`)
            })
          }}
          onClose={() => setPalette(false)}
        />
      )}

      {doc && <Reader path={doc} onClose={() => setDoc(null)} />}

      {launcher && (
        <Launcher
          handoff={launcher.handoff}
          full={full}
          onLaunch={launch}
          onClose={() => setLauncher(null)}
        />
      )}

      {viewing && (
        <HistoryView transcript={viewing} full={full} onResume={resumeHistory} onClose={() => setViewing(null)}
                     onOpenDoc={setDoc} />
      )}
    </div>
  )
}

/* A past conversation, read from history.
 *
 * Read-only: the transcript component renders the stored blocks, and the
 * one action is to continue the session in a terminal, which `--resume`
 * does with the engine id the row kept. */
function HistoryView({ transcript, full, onResume, onClose, onOpenDoc }: {
  transcript: HistoryTranscript
  /** Every terminal slot is taken; the reason resuming is not on offer. */
  full?: string
  onResume: (t: HistoryTranscript) => void
  onClose: () => void
  onOpenDoc: (path: string) => void
}) {
  return (
    <div className="absolute inset-0 z-20 flex flex-col bg-ground/95">
      <div className="flex h-[var(--head-band)] shrink-0 items-center gap-[10px] border-b border-line bg-surface px-[14px] font-mono text-[11.5px]">
        <span className="h-[7px] w-[7px] rounded-[2px]" style={{ background: MODE_ACCENT[transcript.mode] }} />
        <span className="text-ink">{MODE_LABEL[transcript.mode]}</span>
        <span className="min-w-0 truncate text-ink-dim">· {transcript.title}</span>
        <span className="ml-auto flex items-center gap-[8px]">
          {transcript.resumable && transcript.engine_id && (full ? (
            <span className="text-ink-dim">{full}</span>
          ) : (
            <button type="button" onClick={() => onResume(transcript)}
                    className="rounded-control px-[10px] py-[4px] text-ground"
                    style={{ background: MODE_ACCENT[transcript.mode] }}>
              resume in a terminal
            </button>
          ))}
          <button type="button" onClick={onClose} className="px-[8px] text-ink-faint hover:text-ink" aria-label="close">
            esc
          </button>
        </span>
      </div>
      <Transcript blocks={transcript.blocks} historyId={transcript.id}
                  scrollKey={`h${transcript.id}`} onOpenDoc={onOpenDoc} />
    </div>
  )
}

function Pane({ view, limits, terminals, onInboxDecided }: {
  view: string
  limits?: { five_hour: Window; seven_day: Window } | null
  /** The open terminals and where each is: what the Repo view groups. */
  terminals: RepoTerminal[]
  /** A proposal was just accepted or rejected in Settings; the rail's badge re-reads. */
  onInboxDecided?: () => void
}) {
  // Re-read when the set of directories changes, not when a terminal is
  // merely selected -- and after a push from the view itself.
  const [repoTick, setRepoTick] = useState(0)
  if (view === 'stats') return <Stats limits={limits} />
  const cwds = terminals.map((t) => `cwd=${encodeURIComponent(t.cwd)}`).join('&')
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      {/* Every view sits in the middle of the pane: auto vertical margins
          inside a flex column centre a short page and let a tall one flow
          from the top, which justify-content would clip. Settings keeps the
          reading column. Repo's pane is uncapped because its grid caps
          itself: a column per repository, each the width of a card in this
          column (2026-09-17), so one open repository is a card and not a
          screen-wide banner, and three still get a wide window's room. */}
      <div className="my-auto w-full px-8 pb-8 pt-7"
           style={view === 'repo' ? undefined : { marginInline: 'auto', maxWidth: PANE_COLUMN }}>
        {view === 'repo' && <Fetched<RepoPayload> key={`${cwds}#${repoTick}`} path={`/v2/repos?${cwds}`} what="the repositories" render={(d) => <Repo data={d} terminals={terminals} onChanged={() => setRepoTick((t) => t + 1)} />} />}
        {view === 'settings' && <Settings onDecided={onInboxDecided} />}
      </div>
    </div>
  )
}

/** Load a route, then render it. Loading, loaded and unreachable are three
 *  states: an empty panel that means "the backend is down" must not look
 *  like one that means "you have nothing waiting". */
function Fetched<T>({ path, what, render }: {
  path: string
  what: string
  render: (data: T) => React.ReactNode
}) {
  const data = useFetched<T>(path)
  if (data === false) return <Unreachable what={what} />
  if (data === null)
    return (
      <div className="rounded-card border border-line bg-surface px-4 py-[13px] text-[12.5px] text-ink-faint">
        Loading…
      </div>
    )
  return <>{render(data)}</>
}

const fmt = (n: number) => n.toLocaleString()

function Stats({ limits }: { limits?: { five_hour: Window; seven_day: Window } | null }) {
  const stats = useFetched<StatsPayload>('/v2/sessions/stats')
  // The signature, brightening as a window fills: the reading's own hue at
  // three steps rather than a traffic light. A fuller bar is a brighter
  // bar, which is the warning, without borrowing a character's colour.
  const bar = (pct: number) => (pct < 60 ? 'var(--sig-fill)' : pct < 85 ? 'var(--sig-fill-hot)' : 'var(--sig-fill-max)')

  const windows = limits
    ? [
        { label: '5-hour window', pct: Math.round(limits.five_hour.used * 100),
          sub: `resets ${resetIn(limits.five_hour.resets_at)}` },
        { label: '7-day window', pct: Math.round(limits.seven_day.used * 100),
          sub: `resets ${resetIn(limits.seven_day.resets_at)}` },
      ]
    : null

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      {/* Centred the same way the Repo view is: auto vertical margins in a
          flex column sit the page in the middle when it is shorter than the
          window and let it scroll from the top when it is not. */}
      <div className="mx-auto my-auto w-full px-8 pb-8 pt-7" style={{ maxWidth: PANE_COLUMN }}>
        <h2 className="m-0 mb-[14px] font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">
          Usage
        </h2>

        {windows ? (
          <Beam><div className="mb-[10px] rounded-card border border-line bg-surface px-4 pb-[6px] pt-1">
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
                <div className="text-right font-mono text-[12px] tabular-nums" style={{ color: 'var(--sig-text)' }}>
                  {w.pct}%
                </div>
              </div>
            ))}
          </div></Beam>
        ) : (
          <div className="mb-[10px] rounded-card border border-line bg-surface px-4 py-[13px] text-[12.5px] text-ink-dim">
            A session reports the rolling windows once it has spoken to the API. Run one and they appear here.
          </div>
        )}

        <Activity days={stats === null || stats === false ? stats : stats.activity} />

        <h2 className="m-0 mb-[14px] mt-7 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint">
          Lifetime tokens
        </h2>

        {stats === false ? (
          <Unreachable what="usage history" />
        ) : stats === null ? (
          <div className="rounded-card border border-line bg-surface px-4 py-[13px] text-[12.5px] text-ink-faint">
            Loading…
          </div>
        ) : (
          <Beam><div className="rounded-card border border-line bg-surface px-4 py-[14px]">
            <div className="mb-4 flex items-baseline gap-[9px]">
              <b className="font-mono text-[29px] font-bold tabular-nums tracking-[-0.02em] text-ink">
                {fmt(
                  stats.lifetime.input + stats.lifetime.output +
                  stats.lifetime.cached + stats.lifetime.cache_write,
                )}
              </b>
              <span className="font-mono text-[11px] text-ink-faint">
                total{stats.lifetime.since ? ` · since ${stats.lifetime.since.slice(0, 10)}` : ''}
                {' · '}
                {fmt(stats.lifetime.turns)} turns
              </span>
            </div>
            <Stacked parts={[
              { label: 'input', value: stats.lifetime.input, tone: 'var(--sig-share-1)' },
              { label: 'output', value: stats.lifetime.output, tone: 'var(--sig-share-2)' },
              { label: 'cache read', value: stats.lifetime.cached, tone: 'var(--sig-share-3)' },
              { label: 'cache write', value: stats.lifetime.cache_write, tone: 'var(--sig-share-4)' },
            ]} />
            {/* One number, no tiers. Read from the CLI's own transcripts, so
                it counts every session on this machine, not only the ones
                Noctis hosted -- and the background tier that used to be
                split out here was 0.178% of the total. */}
            <ListPrice turns={stats.lifetime.turns} />
          </div></Beam>
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

/* The four token kinds as one stacked bar -- each a share of the same
 * total, which is the only comparison that puts them on one line -- with a
 * dot-and-figure legend under it. Four steps of the signature, lightest to
 * darkest, in the order the legend reads. Cache reads are three thousand
 * times the input, so the small kinds are slivers: each keeps a 2px minimum
 * so it exists on the bar at all, and the legend carries the number the bar
 * cannot. */
function Stacked({ parts }: { parts: { label: string; value: number; tone: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0)
  return (
    <div className="font-mono text-[11.5px]">
      <div className="flex h-[7px] overflow-hidden rounded-full bg-line">
        {parts.map((p) => (
          <span key={p.label} title={`${p.label} ${p.value.toLocaleString()}`}
                className="block h-full min-w-[2px]"
                style={{ flex: `${total > 0 ? p.value / total : 0} 0 0`, background: p.tone }} />
        ))}
      </div>
      <div className="mt-[9px] flex flex-wrap gap-x-[16px] gap-y-[4px]">
        {parts.map((p) => (
          <span key={p.label} className="flex items-center gap-[6px] text-ink-dim">
            <span className="h-[7px] w-[7px] rounded-full" style={{ background: p.tone }} />
            {p.label}{' '}
            <span className="tabular-nums text-ink" title={p.value.toLocaleString()}>{compact(p.value)}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

/** 19216 → "19.2k". Scaled to the number's own size rather than a fixed
 *  unit, and the exact figure stays in the title for when it matters. */
function compact(n: number): string {
  if (n < 1_000) return String(n)
  if (n < 1_000_000) return `${(n / 1_000).toFixed(1)}k`
  if (n < 1_000_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  return `${(n / 1_000_000_000).toFixed(1)}B`
}

/** The list-price line under Stats' lifetime tokens. Its own fetch, so a
 *  slow or absent billing route cannot hold up the counts above it. */
function ListPrice({ turns }: { turns: number }) {
  const data = useFetched<BillingPayload>('/v2/billing')
  return data ? <ListPriceFact data={data} totalTurns={turns} /> : null
}

export default App
