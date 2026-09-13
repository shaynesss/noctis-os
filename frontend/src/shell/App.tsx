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
import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity } from './Activity'
import { BottomBar, Composer, OverageBanner, Rail, TabBar, TitleStrip } from './Chrome'
import {
  del, emptyFold, fold, get, post, readImage, runSession,
  type Attachment, type HistorySession, type HistoryTranscript,
  type Stats as StatsPayload, type Window,
} from './engine'
import { Terminal } from './Terminal'
import { Unreachable } from './Async'
import { useFetched } from './useFetched'
import { hasImage } from './clipboard'
import {
  CommandMenu, ModelPicker, PermissionPicker, PermissionRequest, PromotePicker,
  type ModelOption, type PendingPermission,
} from './Commands'
import { matching } from './slash'
import { Launcher, type LaunchRequest } from './Launcher'
import { turnFinished } from './notify'
import { Palette } from './Palette'
import { Reader } from './Reader'
import {
  Brief, Inbox, ListPriceFact, Settings,
  type BillingPayload, type BriefPayload, type InboxPayload,
} from './Panels'
import { Transcript } from './Transcript'
import {
  EMPTY_SESSION, EMPTY_TAB, MODE_ACCENT, MODE_INFO, MODE_LABEL,
  DEFAULT_EFFORT, EFFORT_CYCLE, patchEntry, recallOpenTabs, rememberOpenTabs, uniqueLabel,
  type RememberedTab,
  type Effort, type Mode, type Permission, type SessionState, type Tab,
} from './domain'
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
  /* What the composer's chip cycles, per tab. dev.md's default, finally
   * applied: nothing passed --effort before, so every session ran at the
   * CLI's.
   *
   * Keyed by tab, like `drafts` and unlike the single value this used to be.
   * One global dial was wrong in a way that was invisible: the chip sits in
   * the composer, which is per-tab furniture, so everything about its
   * placement says "this session's effort" -- while moving it on any tab
   * silently moved it on all of them. That pinned a research session to
   * whatever the last General question happened to want, which is the
   * opposite of the per-mode effort routing dev.md asks for. */
  const [efforts, setEfforts] = useState<Record<string, Effort>>({})
  const effortOf = (id: string): Effort => efforts[id] ?? DEFAULT_EFFORT

  // Tabs and sessions are state rather than the imported constants now that
  // mode entry can create them. The constants are the seed, not the store.
  const [tabs, setTabs] = useState<Tab[]>([EMPTY_TAB])
  const [sessions, setSessions] = useState<Record<string, SessionState>>({ t0: EMPTY_SESSION })
  /* Drafts survive a reload.
   *
   * A half-written message is work, and the window reloads for reasons that
   * have nothing to do with you -- a dev-server restart, a crash, closing it
   * by habit. Losing the text you were composing to any of those is the kind
   * of small betrayal that makes an app feel unsafe to type into.
   *
   * Text only. Pasted images are deliberately not persisted: they are base64
   * and would fill the store, and re-pasting is one keystroke. */
  const [drafts, setDrafts] = useState<Record<string, string>>(() => loadDrafts())

  /* Pasted images, per draft. Kept beside the draft rather than on the
   * session, because they belong to a message not yet sent -- switching tabs
   * and coming back should find the same half-written message with the same
   * pictures attached. */
  const [attachments, setAttachments] = useState<Record<string, Attachment[]>>({})
  // Read when deciding the next image's number, so the decision does not
  // have to happen inside a state updater.
  const attachmentsRef = useRef(attachments)
  attachmentsRef.current = attachments

  // `null` closed; otherwise a launch, carrying its handoff source if any.
  const [launcher, setLauncher] = useState<null | { handoff?: HandoffSource }>(null)
  const [palette, setPalette] = useState(false)
  const [doc, setDoc] = useState<string | null>(null)

  /* The key listener is registered once, so its closure would otherwise hold
   * the first render's tabs forever -- Cmd+3 would keep selecting the third
   * tab as it was at mount, not as it is. Refs give the handler the current
   * values without re-registering a capture-phase listener on every state
   * change, which would drop keystrokes during the swap. */
  const tabsRef = useRef(tabs)
  const launcherRef = useRef(launcher)
  const paletteRef = useRef(palette)
  const docRef = useRef(doc)
  const commandRef = useRef<string | null>(null)
  const handoffRef = useRef(() => {})
  const sessionsRef = useRef(sessions)
  const permissionRef = useRef(permission)
  const effortsRef = useRef(efforts)
  // The tab the composer is bound to, which is what Escape should stop --
  // the same rule the composer itself follows, kept in one place.
  const composerTabRef = useRef('t0')
  const activeTabRef = useRef(activeTab)
  const closeRef = useRef((_id: string) => {})
  tabsRef.current = tabs
  launcherRef.current = launcher
  paletteRef.current = palette
  docRef.current = doc
  sessionsRef.current = sessions
  permissionRef.current = permission
  effortsRef.current = efforts

  /* One abort per tab. Closing a tab or quitting has to actually stop the
   * stream: an orphaned reader keeps the connection open and the session
   * keeps burning the 5h window with nothing rendering it. */
  const aborts = useRef<Record<string, AbortController>>({})

  /* Where each conversation was left. A ref rather than state: it changes on
   * every scroll event, and re-rendering the transcript while someone is
   * scrolling it is the one thing that must not happen. */
  const scrollTops = useRef<Record<string, number>>({})

  // Newest rolling-window report, for the status bar. Null until a session
  // has reported one -- see the backend's known:false for why that is not
  // the same as zero.
  const [limits, setLimits] = useState<
    { five_hour: Window; seven_day: Window; using_overage?: boolean } | null
  >(null)

  /* Seed it from the backend, which has been remembering this all along.
   *
   * The only writer used to be the stream event below, so the windows read
   * `—` until the first turn of each page load and then stayed right for as
   * long as the window lived. That looked permanent because the window
   * lived for days; restarting to pick up a backend change is now routine,
   * and the bar went blank every time -- for state that is a property of
   * the account, not of this page load.
   *
   * Only ever a seed. A stream event is newer by definition, and the fetch
   * resolving late must not overwrite one, so the write is guarded on the
   * slot still being empty. */
  useEffect(() => {
    let live = true
    void get<{ known: boolean; five_hour: Window; seven_day: Window
               using_overage: boolean }>('/v2/sessions/limits').then((d) => {
      if (!live || !d?.known) return
      setLimits((prev) => prev ?? d)
    })
    return () => { live = false }
  }, [])

  /* Dismissed for this window only, and re-armed if overage clears and
   * returns. Persisting the dismissal would mean a later, real overage
   * arriving silently because of a click made days ago. */
  const [overageDismissed, setOverageDismissed] = useState(false)
  useEffect(() => {
    if (!limits?.using_overage) setOverageDismissed(false)
  }, [limits?.using_overage])

  // The panels are not conversations. While one is open the composer binds
  // to General rather than to whichever tab you happened to leave behind --
  // typing into a Faber-labelled box from the Settings page would send to a
  // session you are not looking at, which is the kind of thing you only
  // notice after it has happened.
  const generalTab = tabs.find((t) => t.mode === 'general')!.id
  const inChat = view === 'chat'
  const composerTab = inChat ? activeTab : generalTab

  /* The menu shows only while the whole draft is a command being typed --
   * not on any "/", because paths are typed constantly here and a menu
   * appearing every time you write `src/shell` would be worse than none. */
  const draft = drafts[composerTab] ?? ''
  const commandTyped = /^\/[a-z]*$/i.test(draft) ? draft : null

  composerTabRef.current = composerTab
  activeTabRef.current = activeTab
  commandRef.current = commandTyped

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
  /* Update one tab's session, or do nothing if the tab is gone.
   *
   * Every updater below spreads `...s[tabId]`, and a tab can be closed while
   * its turn is still unwinding: `closeTab` deletes the session and aborts
   * the stream, but the abort resolves a tick later, so the stream's own
   * updaters and its `finally` both still run against an entry that no
   * longer exists. That threw `undefined is not an object (evaluating
   * 's[tabId].lastTurn')` and took the window down.
   *
   * TypeScript cannot catch this: indexing a `Record<string, T>` is typed as
   * always present unless `noUncheckedIndexedAccess` is on, so `[tsc]`
   * reports zero errors on it. The guard has to be written, not inferred.
   *
   * Dropping the update is correct rather than merely safe -- the tab it
   * described is closed, so there is nothing left for it to say. */
  const patchSession = (
    tabId: string,
    patch: (prev: SessionState) => SessionState,
  ) => setSessions((s) => patchEntry(s, tabId, patch))

  const turn = async (
    tabId: string,
    prompt: string,
    seed?: SessionState,
    images: Attachment[] = [],
    /* An opener the person did not type. Sent to the engine, kept out of the
     * transcript — showing it would put words in your mouth, and the reply
     * reads as unprompted, which is what it should look like. */
    hidden = false,
  ) => {
    // `seed` is how a just-launched session runs its opening prompt: it does
    // not exist in the ref yet, because that follows a render and this is
    // called before one. Waiting a tick instead would be a race that passes
    // on a fast machine.
    const current = seed ?? sessionsRef.current[tabId]
    if (!current || current.busy) return
    if (!prompt.trim() && !hidden) return

    const withUser: SessionState = {
      ...current,
      busy: true,
      thinking: null,
      // Stamped once here rather than derived from `busy`, so the elapsed
      // timer measures the turn and not the moment the component mounted.
      startedAt: Date.now(),
      blocks: hidden
        ? current.blocks
        : [...current.blocks, { kind: 'user', text: prompt, at: now() }],
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
          // Read at send time and keyed by the tab that is sending, so the
          // chip governs this turn on this session -- not whatever another
          // tab's chip was last set to.
          effort: effortsRef.current[tabId] ?? DEFAULT_EFFORT,
          // Bytes, not a path: the picture is part of what was said.
          images: images.map(({ media_type, data }) => ({ media_type, data })),
          // The server owns the opener's text, so it can title the
          // conversation for what it is instead of with the prompt.
          opener: hidden,
          model: current.model ?? undefined,
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
        patchSession(tabId, (prev) => ({
          ...prev,
          blocks: state.blocks,
          thinking: state.thinking,
          context: state.context,
          ranModel: state.model ?? prev.ranModel,
          engineId: state.sessionId ?? prev.engineId,
        }))
      }
    } catch (e) {
      /* Belt to `runSession`'s braces, and not redundant: this catches the
       * class of fault that never reaches the stream at all -- a throw in
       * `fold`, in `patchSession`, in a render triggered by them.
       *
       * Without it those became an unhandled rejection, because every caller
       * of `turn` uses `void turn(...)`. The `finally` below then cleared
       * `busy`, so the interface looked idle and finished while the
       * transcript had simply stopped. A turn that fails has to leave
       * something behind saying so -- the same rule the session prompt puts
       * on a model, applied to the surface hosting it. */
      if (!ctrl.signal.aborted) {
        state = fold(state, {
          t: 'error',
          message: `the interface dropped this turn: ${(e as Error).message}`,
          fatal: true,
        })
        patchSession(tabId, (prev) => ({ ...prev, blocks: state.blocks }))
      }
    } finally {
      // In `finally` so an abort or a throw cannot strand a session as
      // permanently busy, which would lock its composer with no way back.
      const stopped = ctrl.signal.aborted

      /* Tell you it landed, if you are not looking. Skipped when the turn
       * was stopped: you were there, you stopped it, and being notified
       * about your own action is the definition of noise. */
      if (!stopped) {
        const last = [...state.blocks].reverse().find((b) => b.kind === 'text')
        void turnFinished({
          mode: current.mode,
          text: last && last.kind === 'text' ? last.text : '',
          seconds: (Date.now() - (withUser.startedAt ?? Date.now())) / 1000,
          failed: state.blocks.some((b) => b.kind === 'error' && b.fatal),
        })
      }

      delete aborts.current[tabId]
      patchSession(tabId, (prev) => ({
        ...prev,
        busy: false,
        thinking: null,
        startedAt: null,
        // Only for a turn that ran to completion: a stopped one already
        // says "Stopped." and does not need a duration beside it.
        lastTurn: stopped
          ? prev.lastTurn
          : { seconds: (Date.now() - (withUser.startedAt ?? Date.now())) / 1000, at: Date.now() },
        // Recorded in the transcript rather than left silent. A reply that
        // simply stops mid-sentence is indistinguishable from one that
        // finished badly, and you would not know whether to retry.
        blocks: stopped
          ? [...prev.blocks, { kind: 'error', message: 'Stopped.', fatal: false }]
          : prev.blocks,
      }))
    }
  }

  /* Close a tab.
   *
   * The running turn is aborted first: a closed tab has nowhere to render,
   * and leaving the stream open would keep spending the 5h window on output
   * nobody can see. Selection moves to the neighbour rather than to the
   * start, which is where you were looking. */
  const closeTab = (id: string) => {
    // The pinned General tab is the one that must always exist -- it is
    // where you land with the backend down or on a fresh install, so there
    // is always somewhere to type. It has no close control either; this is
    // the same rule enforced where the keyboard can also reach it.
    const i = tabs.findIndex((t) => t.id === id)
    if (i === -1 || tabs[i].pinned) return
    aborts.current[id]?.abort()
    const remaining = tabs.filter((t) => t.id !== id)
    if (remaining.length === 0) return
    setTabs(remaining)
    setSessions((s) => {
      const next = { ...s }
      delete next[id]
      return next
    })
    if (activeTab === id) setActiveTab(remaining[Math.max(0, i - 1)].id)
  }

  /** Abort the active session's turn. The stream unwinds, the backend closes
   *  its row as cancelled, and the engine process is killed with it. */
  const stop = (tabId: string) => aborts.current[tabId]?.abort()

  /* Paste an image: upload it, then write its reference into the draft.
   *
   * The reference goes into the text at the caret's end rather than being
   * held separately, because it is what the model is actually told to look
   * at -- the lines under the composer only describe what the text already
   * says. */
  const attach = async (tabId: string, blob: Blob) => {
    const image = await readImage(blob)
    if (!image) return

    /* Both updates are computed from one number decided here, rather than
     * one state updater calling another. Nesting them put the reference in
     * the draft twice -- React invokes updaters more than once in
     * development, and anything with a side effect inside runs twice with
     * it. That is what produced "[Image #1] [Image #1]". */
    const n = (attachmentsRef.current[tabId]?.length ?? 0) + 1
    setAttachments((prev) => ({ ...prev, [tabId]: [...(prev[tabId] ?? []), { ...image, n }] }))
    setDrafts((d) => {
      const text = d[tabId] ?? ''
      const sep = text && !text.endsWith(' ') ? ' ' : ''
      return { ...d, [tabId]: `${text}${sep}[Image #${n}] ` }
    })
  }

  /* Removing an attachment takes its reference out of the text too, or the
   * prompt would tell the model to look at something no longer attached. */
  const removeAttachment = (tabId: string, n: number) => {
    setAttachments((prev) => ({ ...prev, [tabId]: (prev[tabId] ?? []).filter((a) => a.n !== n) }))
    setDrafts((d) => ({
      ...d,
      [tabId]: (d[tabId] ?? '').replace(new RegExp(`\\[Image #${n}\\]\\s*`), ''),
    }))
  }

  // Sending from a panel takes you to the conversation it went to. Leaving
  // you on Settings while a reply arrives somewhere unseen would be worse
  // than the extra navigation.
  /** Run a command, or return false if the draft is not one. */
  const runCommand = (name: string): boolean => {
    setDrafts((d) => ({ ...d, [composerTab]: '' }))
    setCmdCursor(0)
    switch (name) {
      case 'model':
      case 'permissions':
        setPicker(name)
        return true
      case 'promote':
        /* Only a conversation with history has anything to promote: the
         * route reads the stored transcript, and a tab that has never been
         * recorded has none. Saying so beats a dialog that fails on submit. */
        if (!composerTab.startsWith('h')) {
          setSessions((prev) => ({
            ...prev,
            [composerTab]: {
              ...prev[composerTab],
              blocks: [...prev[composerTab].blocks, {
                kind: 'error', fatal: false,
                message: 'Nothing to promote yet — send a message first, then this conversation can go to the vault.',
              }],
            },
          }))
          return true
        }
        setPicker('promote')
        return true
      case 'handoff':
        openHandoff()
        return true
      case 'search':
        setPalette(true)
        return true
      case 'clear':
        /* A fresh conversation in the same tab: the transcript and the
         * engine id both go, or the next turn would resume the conversation
         * you just asked to leave. What was said is still in history. */
        setSessions((prev) => ({
          ...prev,
          [composerTab]: { ...prev[composerTab], blocks: [], engineId: undefined, recap: null },
        }))
        return true
      default:
        return false
    }
  }

  const send = () => {
    const typed = (drafts[composerTab] ?? '').trim()
    if (!typed) return

    // A command runs instead of being sent as a message.
    if (commandTyped) {
      const items = matching(commandTyped)
      const chosen = items[cmdCursor % Math.max(1, items.length)]
      if (chosen && runCommand(chosen.name)) return
    }
    const files = attachments[composerTab] ?? []
    const prompt = typed
    setDrafts({ ...drafts, [composerTab]: '' })
    setAttachments((prev) => ({ ...prev, [composerTab]: [] }))
    if (!inChat) {
      setActiveTab(composerTab)
      setView('chat')
    }
    void turn(composerTab, prompt, undefined, files)
  }

  /* A launch always lands in a new tab, whether it came from + or from a
   * handoff. The opening prompt is written into the transcript as a user
   * turn rather than left in the composer, because the session has already
   * been given it -- showing it as an unsent draft would misreport state. */
  const launch = (req: LaunchRequest) => {
    const id = `t${Date.now()}`
    const label = uniqueLabel(
      `${MODE_LABEL[req.mode]} · ${req.cwd.split('/').pop()}`,
      tabs.map((t) => t.label),
    )
    const blocks: SessionState['blocks'] = []
    if (req.from) {
      blocks.push({
        kind: 'handoff',
        from: req.from.mode,
        fromLabel: req.from.label,
        carried: req.from.carried,
      })
    }
    // Only when there is one. An empty launch opens the tab and waits.
    if (req.prompt.trim()) blocks.push({ kind: 'user', text: req.prompt, at: now() })

    // Appended, not replacing. This kept exactly one tab beside General,
    // reasoning that the engine's cap of two made a third unrunnable anyway.
    // Both halves of that are gone: the cap is a budget rather than a limit
    // and is settable, and same-mode concurrency stopped being a hazard when
    // per-mode config dirs did -- there is no shared file left to race on.
    //
    // Two sessions of one mode is an ordinary thing to want: two Faber tabs
    // on two repositories, or two angles on the same one. The tab bar already
    // scrolls rather than wraps, so more of them costs nothing in layout.
    setTabs((ts) => [...ts, { id, mode: req.mode, label }])
    // The provenance block only; the opening prompt is appended by `turn`,
    // so a launched session and a typed one build their transcript the same
    // way rather than through two paths that can drift.
    setSessions({ ...sessions, [id]: { mode: req.mode, cwd: req.cwd, blocks, draft: '' } })
    setDrafts({ ...drafts, [id]: '' })
    setActiveTab(id)
    setView('chat')
    setLauncher(null)
    composerRef.current?.focus()

    const seed: SessionState = { mode: req.mode, cwd: req.cwd, blocks, draft: '' }
    if (req.prompt.trim()) {
      void turn(id, req.prompt, seed)
    } else {
      /* A mode session opens by speaking first.
       *
       * Left empty it just sat there and you had to guess what to say — a
       * "?" to get it going got a confused reply, which is a fair reaction
       * to being handed a "?". Each mode has a session-start routine in its
       * methodology (Faber's Patch/Overhaul question, due recall items,
       * parked triggers); this is what makes it run. General has no routine
       * and no methodology file, so it is left alone. */
      if (req.mode !== 'general') void turn(id, '', seed, [], true)
    }
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
        /* A label with no project half would otherwise hand over
           `~/Developer/`, which exists, so nothing rejects it and the
           session simply starts in the wrong place. */
        cwd: tab.label.split(' · ')[1]
          ? `~/Developer/${tab.label.split(' · ')[1]}`
          : EMPTY_SESSION.cwd,
        carried: lastText && lastText.kind === 'text' ? lastText.text.slice(0, 240) : '',
      },
    })
  }

  handoffRef.current = openHandoff
  closeRef.current = closeTab

  /* Open a conversation found by search, or focus it if already open.
   *
   * Reusing the tab matters: opening a second copy of a live conversation
   * would give two tabs the same engine id, and a turn sent from either
   * would append to a transcript the other is also showing. */
  const openSession = async (id: number) => {
    const tabId = `h${id}`
    if (sessionsRef.current[tabId]) {
      setActiveTab(tabId)
      setView('chat')
      return
    }
    const full = await get<HistoryTranscript>(`/v2/sessions/history/${id}`)
    if (!full) return
    setTabs((ts) => [ts[0], {
      id: tabId, mode: full.mode,
      label: `${MODE_LABEL[full.mode]} · ${truncate(full.title)}`,
    }])
    setSessions((s) => ({ ...s, [tabId]: {
      mode: full.mode, blocks: full.blocks, draft: '',
      /* The project, not the home directory. A stored cwd of '~' makes
         every filesystem search sweep the whole home folder, which times
         out rather than failing -- so it reads as a broken tool instead
         of a bad working directory. EMPTY_SESSION holds the one default
         worth falling back to; '~' was never it. */
      cwd: full.cwd ?? EMPTY_SESSION.cwd, engineId: full.engine_id ?? undefined,
    } }))
    setDrafts((d) => ({ ...d, [tabId]: '' }))
    setActiveTab(tabId)
    setView('chat')

    /* Same rule as the General restore below: fetched after the transcript,
     * never with it, so the conversation you asked for is not held behind the
     * sentence describing it. Without this, a recap only ever appeared on the
     * one conversation restored at launch -- every conversation opened from
     * search, which is all of them, silently had none. */
    const r = await get<{ recap: string | null }>(`/v2/sessions/history/${id}/recap`)
    if (r?.recap) {
      setSessions((s) => (s[tabId] ? { ...s, [tabId]: { ...s[tabId], recap: r.recap } } : s))
    }
  }

  // Cmd+1/2/3 switches tab. Implemented rather than merely labelled: a
  // shortcut shown in the UI that does nothing is a worse lie than the
  // explanatory text it sits next to.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // While the launcher is open it owns the keyboard: its own Cmd+1-5
      // picks a mode, and cycling permission for a session you are not
      // looking at would change something you cannot see.
      if (launcherRef.current || paletteRef.current || docRef.current || pickerRef.current) return

      // Shift+Tab cycles effort, the affordance carried over from the CLI's
      // TUI. It cycled the permission mode until every mode came to spawn
      // with the same tools, at which point it changed almost nothing a
      // person would notice. Wrapping past the end returns to `low`.
      if (e.key === 'Tab' && e.shiftKey && !e.metaKey) {
        e.preventDefault()
        e.stopPropagation()
        // The composer's tab, not the active one: they differ when the
        // composer is bound to General from another view, and the chip you
        // can see is the one this should move.
        const id = composerTabRef.current
        setEfforts((m) => {
          const now = m[id] ?? DEFAULT_EFFORT
          return { ...m, [id]: EFFORT_CYCLE[(EFFORT_CYCLE.indexOf(now) + 1) % EFFORT_CYCLE.length] }
        })
        return
      }
      /* Arrows move the command menu's selection. Handled here rather than
       * in the composer's own keydown so the textarea's caret does not also
       * move, which would leave the visible selection and the caret
       * disagreeing about what Enter will do. */
      if (commandRef.current && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault()
        const n = matching(commandRef.current).length
        if (n > 0) setCmdCursor((c) => (c + (e.key === 'ArrowDown' ? 1 : n - 1)) % n)
        return
      }

      // Escape stops the running turn. Checked before the Cmd guard below
      // because it carries no modifier, and placed after the launcher/palette
      // check above so Escape still closes those first.
      if (e.key === 'Escape') {
        const tab = composerTabRef.current
        if (aborts.current[tab]) {
          e.preventDefault()
          stop(tab)
        }
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

      // Cmd+W closes the active tab, as every tabbed app on the machine
      // does. Not bound to the pinned General tab, which closeTab refuses.
      if (e.key.toLowerCase() === 'w') {
        e.preventDefault()
        closeRef.current(activeTabRef.current)
        return
      }

      // Cmd+K searches. Implemented at last: this shortcut was labelled in
      // the UI early on and then removed, because a shortcut shown and not
      // wired is worse than one that is simply absent.
      if (e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPalette(true)
        return
      }

      // Cmd+T starts a session, matching every tabbed app on the machine.
      if (e.key.toLowerCase() === 't') {
        e.preventDefault()
        setLauncher({})
        return
      }

      /* Cmd+1..9 selects a tab.
       *
       * Matched on `code` as well as `key`. `code` is the physical key and
       * does not change with modifiers, layout or an input method, whereas
       * `key` can arrive as something else entirely on a non-US layout --
       * and these were reported not working on a machine where the handler
       * itself is provably correct.
       */
      const digit = e.code?.startsWith('Digit')
        ? Number(e.code.slice(5))
        : Number(e.key)
      if (!Number.isInteger(digit) || digit < 1 || digit > 9) return
      const target = tabsRef.current[digit - 1]
      if (!target) return
      e.preventDefault()
      setActiveTab(target.id)
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

  /* What was open last time, read once during the first render.
   *
   * Captured here rather than inside the restore effect, and this is the
   * whole reason the arrangement survives a crash: effects run in
   * declaration order, so the writer below fires before the restorer. On a
   * remount -- which is exactly what the error boundary does after a crash
   * -- `tabs` is the bare General seed, so the writer would persist an empty
   * list and the restorer would then read it back and find nothing. The
   * arrangement would be destroyed by the very recovery meant to preserve
   * it. Reading during render happens before any effect at all. */
  const rememberedAtBoot = useRef<RememberedTab[] | null>(null)
  if (rememberedAtBoot.current === null) rememberedAtBoot.current = recallOpenTabs()

  /* Open once the *arrangement* is settled -- not once the whole restore
   * has finished. Until then the writer stays quiet, so a slow transcript
   * fetch is not overtaken by a write describing the half-built arrangement
   * it is still assembling.
   *
   * State rather than a ref, and in the writer's dependencies, for two
   * reasons. A ref cannot wake the writer, so an arrangement that stopped
   * changing before the gate opened would never be recorded at all. And
   * flipping state flushes once immediately, which is what makes the tabs
   * you opened *during* the restore survive rather than being skipped. */
  const [restored, setRestored] = useState(false)

  /* Remember which tabs are open, so a reload brings them all back.
   *
   * Written on every change rather than on unload: a crash, a force-quit or
   * a killed backend never fires unload, and those are exactly the cases
   * where losing the arrangement hurts. By the time anything goes wrong the
   * record is already on disk. */
  useEffect(() => {
    if (!restored) return
    rememberOpenTabs(
      tabs
        .filter((t) => !t.pinned)
        .map((t) => ({
          mode: t.mode,
          label: t.label,
          engineId: sessions[t.id]?.engineId,
        })),
    )
  }, [tabs, sessions, restored])

  /* Reopen what was open: the General session, and every other tab.
   *
   * One long-running General session that carries many tasks, not a tab per
   * conversation. Restoring four made the strip a graveyard of every prompt
   * ever typed, and none of them were the one you meant to continue.
   *
   * So General is continuous: it reopens the most recent General
   * conversation and keeps going, which is what makes it the front door
   * rather than a scratch pad that resets. Everything else comes back from
   * the remembered arrangement -- the tabs you actually had -- and anything
   * else stays in history, reachable by search.
   */
  useEffect(() => {
    let live = true
    void (async () => {
      try {
      /* Asked for by mode and resumability rather than filtered here.
       *
       * A page of the twenty newest rows, searched afterwards for the newest
       * resumable General session, answers the wrong question: the limit has
       * already chosen the rows, so twenty newer rows of another shape hide
       * a session that is still there. On this machine they were exactly
       * that -- unresumable `general` rows the test suite had written into
       * the live database -- and General came back empty with nothing
       * anywhere saying why. */
      const general = await get<{ sessions: HistorySession[] }>(
        '/v2/sessions/history?mode=general&resumable=true&limit=1',
      )
      if (!live) return

      /* General first, and in its own block.
       *
       * Its own block because it used to be the same one: three `return`s
       * covering "no resumable General session" and "its transcript is
       * empty" sat above the loop that restores every other tab, so a
       * machine whose General history was missing or unreadable came back
       * with *nothing* -- not General-minus-one, no tabs at all. The thing
       * that actually made it happen was debris: the backend test suite ran
       * against the live history database and filled the recent rows with
       * unresumable `general` launches, so the search above found none, and
       * five real sessions went with it. The debris is fixed where it was
       * made; this is the coupling that turned it into total loss, and it is
       * wrong whatever puts General out of reach.
       */
      const latest = general?.sessions[0]
      if (latest) {
        const full = await get<HistoryTranscript>(`/v2/sessions/history/${latest.id}`)
        if (!live) return
        if (full && full.blocks.length > 0) {
          setSessions((prev) => ({
            ...prev,
            t0: {
              ...prev.t0,
              blocks: full.blocks,
              cwd: latest.cwd ?? prev.t0.cwd,
              engineId: latest.engine_id ?? undefined,
            },
          }))
        }
      }

      /* And every other tab that was open, not just one.
       *
       * This restored exactly one -- "General plus one", which was the
       * shell's own cap at the time and so was exactly right. The cap is
       * gone, and this was not updated with it: open five sessions, reload,
       * get two back and lose three.
       *
       * Restoring from the remembered arrangement rather than from "the most
       * recent resumable rows" is the difference between reopening what you
       * had and reopening a graveyard of everything ever typed -- which is
       * the failure the single-tab version was itself a reaction to. A
       * machine with nothing remembered still gets the old behaviour, one
       * conversation beside General, so a fresh install is unchanged.
       *
       * Looked up by engine id rather than matched against the history page
       * fetched above. Matching meant a tab whose conversation had fallen
       * past the twentieth most recent row could not be found at all, and
       * was dropped silently -- the window is a display limit and had no
       * business deciding what comes back.
       */
      const remembered = rememberedAtBoot.current ?? []
      let paths: string[] = remembered.map(
        (t) => `/v2/sessions/history/by-engine/${t.engineId}`,
      )
      if (!remembered.length) {
        // Nothing remembered: a fresh install, or a window that has never
        // been reloaded. The old behaviour, one conversation beside General.
        const recent = await get<{ sessions: HistorySession[] }>(
          '/v2/sessions/history?resumable=true&limit=20',
        )
        if (!live) return
        const fallback = recent?.sessions.find((h) => h.mode !== 'general')
        paths = fallback ? [`/v2/sessions/history/${fallback.id}`] : []
      }

      const restoredIds: number[] = []
      for (const path of paths) {
        if (!live) return
        const asideFull = await get<HistoryTranscript>(path)
        if (!live) return
        if (!asideFull || asideFull.blocks.length === 0) continue

        const tabId = `h${asideFull.id}`
        restoredIds.push(asideFull.id)
        setTabs((ts) => (ts.some((t) => t.id === tabId) ? ts : [...ts, {
          id: tabId, mode: asideFull.mode,
          label: `${MODE_LABEL[asideFull.mode]} · ${truncate(asideFull.title)}`,
        }]))
        setSessions((prev) => (prev[tabId] ? prev : {
          ...prev,
          [tabId]: {
            mode: asideFull.mode,
            blocks: asideFull.blocks,
            draft: '',
            cwd: asideFull.cwd ?? EMPTY_SESSION.cwd,
            engineId: asideFull.engine_id ?? undefined,
          },
        }))
        setDrafts((d) => (tabId in d ? d : { ...d, [tabId]: '' }))
      }

      /* The arrangement is settled here, so recording starts here.
       *
       * Not in the `finally` below, which was the bug: that runs after one
       * recap engine call per restored tab, each taking seconds. For that
       * whole window -- tens of seconds, or forever if a recap hangs -- every
       * write was skipped, so tabs opened while the app was warming up were
       * never recorded and a reload brought back nothing. Recaps only patch
       * a line of text onto a tab that already exists; they cannot change
       * which tabs there are. */
      setRestored(true)

      /* Recaps last, one request per restored tab, General included.
       *
       * After the transcripts rather than interleaved with them: a recap
       * costs an engine call and takes seconds, and blocking the thing you
       * came back for on the sentence describing it is the wrong trade.
       * General's used to be fetched between its own transcript and the
       * other tabs', which put exactly that wait in front of every other
       * conversation you had open. */
      const recaps: [string, number][] = latest ? [['t0', latest.id]] : []
      for (const id of restoredIds) recaps.push([`h${id}`, id])
      for (const [tabId, id] of recaps) {
        if (!live) return
        const ar = await get<{ recap: string | null }>(`/v2/sessions/history/${id}/recap`)
        if (live && ar?.recap) {
          setSessions((prev) => patchEntry(prev, tabId, (p) => ({ ...p, recap: ar.recap })))
        }
      }
      } finally {
        /* On every path, including the early returns above.
         *
         * This body returns early for a backend that is down and for a
         * window that closed mid-restore. If the flag only set on the happy
         * path, the writer would stay silent forever on exactly those
         * launches -- and the arrangement would stop being recorded from
         * then on, which is the failure this whole mechanism exists to
         * prevent, arrived at from the other side. */
        setRestored(true)
      }
    })()
    return () => {
      live = false
    }
  }, [])

  /* The branch for the active session's directory.
   *
   * Its own fetch rather than a field on session state: it changes when you
   * switch branches in a terminal, not when a session does anything, so
   * carrying it on session state would show a branch you left. Re-read when
   * the directory changes, and on window focus, which is when returning from
   * that terminal actually happens.
   */
  const [branch, setBranch] = useState<string | null>(null)
  const activeCwd = sessions[activeTab]?.cwd ?? ''
  useEffect(() => {
    if (!activeCwd) return
    let live = true
    const read = () =>
      void get<{ branch: string | null }>(`/v2/git?cwd=${encodeURIComponent(activeCwd)}`)
        .then((d) => live && setBranch(d?.branch ?? null))
    read()
    window.addEventListener('focus', read)
    return () => {
      live = false
      window.removeEventListener('focus', read)
    }
  }, [activeCwd])

  /* Whether the clipboard holds an image, checked when the window becomes
   * active rather than on a timer. Copying happens in another app, so
   * returning here is exactly when the answer can have changed — and a poll
   * would be reading your clipboard on a schedule, for a hint. */
  const [clipboardImage, setClipboardImage] = useState(false)

  /* What the orchestrator is running right now.
   *
   * Polled rather than streamed: it changes only when a turn starts or ends,
   * both of which this shell already knows about locally — the poll is for
   * sessions started elsewhere, and a few seconds of staleness on that
   * costs nothing. A socket for two integers would be the expensive way to
   * be no more correct.
   */
  const [live, setLive] = useState<{ running: number; max: number } | null>(null)
  useEffect(() => {
    let alive = true
    const read = () =>
      void get<{ running: number; max_concurrent: number }>('/v2/sessions').then((d) => {
        if (alive && d) setLive({ running: d.running, max: d.max_concurrent })
      })
    read()
    const id = setInterval(read, 4000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  /* Permission requests waiting on you.
   *
   * Polled fast and unconditionally. A session is *blocked* while one of
   * these is outstanding — it is sitting inside a tool call waiting for the
   * answer — so latency here is latency you watch, unlike the live counter
   * next door where a few seconds of staleness costs nothing. The request
   * expires server-side, so a missed poll costs a denial rather than a hang.
   */
  const [permissionRequests, setPermissionRequests] = useState<PendingPermission[]>([])
  useEffect(() => {
    let alive = true
    const read = () =>
      void get<{ pending: PendingPermission[] }>('/v2/sessions/permissions/pending').then((d) => {
        if (alive && d) setPermissionRequests(d.pending ?? [])
      })
    read()
    const id = setInterval(read, 900)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const decidePermission = useCallback((
    id: string,
    decision: 'allow' | 'deny',
    // Present only for AskUserQuestion, where the choice *is* the answer and
    // allowing the call without it would return an empty reply.
    answers?: Record<string, string>,
  ) => {
    // Dropped from local state first: the dialog must go the instant you
    // click, not one poll later, or it reads as not having registered and
    // invites a second click on a question that is already answered.
    // Captured inside the updater rather than read from state: this callback
    // has an empty dependency list, so a closed-over `permissionRequests`
    // would be whatever it was on first render.
    let dropped: PendingPermission | undefined
    setPermissionRequests((prev) => {
      dropped = prev.find((r) => r.id === id)
      return prev.filter((r) => r.id !== id)
    })
    /* ...and put back if the decision never lands.
     *
     * The optimistic drop above is right, but it used to be the whole story:
     * `void post(...)` with nothing reading the result. So a failed request
     * -- the backend restarting under the click is the documented case --
     * closed the dialog, dropped the answer, and left the session waiting on
     * a decision that no longer existed anywhere. The session looks frozen
     * and the one control that would unfreeze it is gone from the screen.
     *
     * Restoring is the honest recovery: the question is genuinely still
     * open, so it belongs back on screen. Re-inserted only if it has not
     * already returned on its own -- the pending poll may have re-added it
     * first, and two copies of one question is its own confusion. */
    void post(`/v2/sessions/permissions/${id}/decide`, { decision, answers })
      .then((res) => {
        const failed = res && typeof res === 'object' && 'error' in res
        const back = dropped
        if (!failed || !back) return
        setPermissionRequests((prev) =>
          prev.some((r) => r.id === id) ? prev : [...prev, back])
      })
  }, [])

  /* Slash commands.
   *
   * `picker` is whichever overlay a command opened. `model` is the session's
   * override, kept per tab because it is a property of this conversation and
   * not of the app. */
  const [picker, setPicker] = useState<null | 'model' | 'permissions' | 'promote'>(null)
  const [models, setModels] = useState<ModelOption[]>([])
  const [modeDefaults, setModeDefaults] = useState<Record<string, string>>({})
  const [promptsAnswerable, setPromptsAnswerable] = useState(false)
  const [cmdCursor, setCmdCursor] = useState(0)
  // Declared after the state it tracks: a ref initialised from a `useState`
  // above it reads the variable before assignment.
  const pickerRef = useRef(picker)
  pickerRef.current = picker

  useEffect(() => {
    void get<{
      models: ModelOption[]
      modes: { mode: string; model: string }[]
      prompts_answerable: boolean
    }>('/v2/config').then((c) => {
      if (!c) return
      setModels(c.models ?? [])
      setModeDefaults(Object.fromEntries(c.modes.map((m) => [m.mode, m.model])))
      setPromptsAnswerable(Boolean(c.prompts_answerable))
    })
  }, [])
  useEffect(() => {
    let live = true
    const check = () => void hasImage().then((v) => live && setClipboardImage(v))
    check()
    window.addEventListener('focus', check)
    return () => {
      live = false
      window.removeEventListener('focus', check)
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

  // Written on change rather than on unload: a crashed or force-quit window
  // never runs an unload handler, and those are exactly the cases this is
  // for.
  useEffect(() => {
    try {
      localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts))
    } catch {
      // A full or unavailable store must not break typing.
    }
  }, [drafts])

  // Abort every live stream when the shell goes away. Without this the
  // window can close on running readers, which keeps the connections open.
  useEffect(() => {
    const live = aborts.current
    return () => Object.values(live).forEach((c) => c.abort())
  }, [])

  return (
    <div className="relative flex h-full flex-col" style={{ ['--accent' as string]: accent }}>
      <TitleStrip />
      {limits?.using_overage && !overageDismissed && (
        <OverageBanner onDismiss={() => setOverageDismissed(true)} />
      )}

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
          onClose={closeTab}
          onNew={() => setLauncher({})}
          onHandoff={openHandoff}
          onSearch={() => setPalette(true)}
        />

        {view === 'chat' ? (
          <Transcript
            blocks={session.blocks}
            accent={accent}
            thinking={session.thinking}
            mode={session.mode}
            startedAt={session.startedAt}
            recap={session.recap}
            lastTurn={session.lastTurn}
            scrollKey={activeTab}
            initialScroll={scrollTops.current[activeTab]}
            onScroll={(key, top) => {
              scrollTops.current[key] = top
            }}
            streaming={Boolean(session.busy)}
            historyId={activeTab.startsWith('h') ? Number(activeTab.slice(1)) : null}
            onOpenDoc={setDoc}
            onEdit={(text) => {
              // Into the composer rather than an inline field: the composer
              // is where messages are written, has the attach and permission
              // controls, and already grows to fit.
              setDrafts((d) => ({ ...d, [activeTab]: text }))
              composerRef.current?.focus()
            }}
            onRetry={(text) => void turn(activeTab, text)}
          />
        ) : (
          <Pane view={view} limits={limits} mode={session.mode}
                cwd={activeCwd} accent={accent} />
        )}

        </div>
      </div>

      <BottomBar
        limits={limits}
        working={tabs.filter((t) => sessions[t.id]?.busy).map((t) => sessions[t.id].mode)}
        /* A conversation exists once the engine has given it an id — that is
           what makes it resumable, and so what makes the mode genuinely
           "open" rather than merely selected. */
        open={tabs.filter((t) => sessions[t.id]?.engineId).map((t) => sessions[t.id].mode)}
        state={{
          live: live ?? undefined,
          cwd: shortenHome(activeCwd),
          /* The session's override if it has one, else the mode's default
             as the backend reports it. This read MODE_INFO, a frontend
             constant, so switching model with /model changed what the engine
             ran and not what the bar said -- the bar claimed opus while the
             session answered on sonnet. */
          /* What the engine said it ran, when it has said. Falls back to
             what was requested before the first turn — but once a turn has
             happened, this is reported rather than assumed. */
          model: session.ranModel ?? session.model ?? modeDefaults[session.mode]
            ?? MODE_INFO[session.mode].model,
          branch,
          context: session.context ?? null,
        }}
      >
        <Composer
            ref={composerRef}
            mode={composerMode}
            value={drafts[composerTab] ?? ''}
            onChange={(v) => setDrafts({ ...drafts, [composerTab]: v })}
            onSend={send}
            attachments={attachments[composerTab] ?? []}
            onAttach={(blob) => void attach(composerTab, blob)}
            onRemoveAttachment={(n) => removeAttachment(composerTab, n)}
            clipboardHasImage={clipboardImage}
            commandMenu={
              commandTyped && (
                <CommandMenu
                  typed={commandTyped}
                  cursor={cmdCursor}
                  onPick={(n: string) => runCommand(n)}
                />
              )
            }
            busy={sessions[composerTab].busy}
            onStop={() => stop(composerTab)}
            effort={effortOf(composerTab)}
            onCycleEffort={() =>
              setEfforts((m) => {
                const now = m[composerTab] ?? DEFAULT_EFFORT
                return {
                  ...m,
                  [composerTab]: EFFORT_CYCLE[(EFFORT_CYCLE.indexOf(now) + 1) % EFFORT_CYCLE.length],
                }
              })
            }
        />
      </BottomBar>

      {picker === 'model' && (
        <ModelPicker
          models={models}
          current={sessions[composerTab].model ?? null}
          modeDefault={modeDefaults[sessions[composerTab].mode] ?? ''}
          mode={sessions[composerTab].mode}
          onPick={(id: string | null) => {
            setSessions((prev) => ({
              ...prev,
              [composerTab]: { ...prev[composerTab], model: id ?? undefined },
            }))
            setPicker(null)
            composerRef.current?.focus()
          }}
          onClose={() => {
            setPicker(null)
            composerRef.current?.focus()
          }}
        />
      )}

      {picker === 'promote' && (
        <PromotePicker
          /* The opening prompt makes a better title than anything derivable
             from the reply: it is what you came to the conversation for. */
          suggestedTitle={promoteTitle(sessions[composerTab])}
          onPromote={async ({ rel_path, title, note }) => {
            const id = Number(composerTab.slice(1))
            const out = await post<{ path: string }>(
              `/v2/sessions/history/${id}/promote`, { rel_path, title, note },
            )
            if ('error' in out) return out.error
            setPicker(null)
            setSessions((prev) => ({
              ...prev,
              [composerTab]: {
                ...prev[composerTab],
                blocks: [...prev[composerTab].blocks, {
                  kind: 'error', fatal: false,
                  message: `Promoted to ${out.path} — the vault has it now.`,
                }],
              },
            }))
            return null
          }}
          onClose={() => {
            setPicker(null)
            composerRef.current?.focus()
          }}
        />
      )}

      {picker === 'permissions' && (
        <PermissionPicker
          current={permission}
          promptsAnswerable={promptsAnswerable}
          onPick={(p: Permission) => {
            setPermission(p)
            setPicker(null)
            composerRef.current?.focus()
          }}
          onClose={() => {
            setPicker(null)
            composerRef.current?.focus()
          }}
        />
      )}

      {palette && (
        <Palette
          onOpenSession={(id) => void openSession(id)}
          onOpenDoc={setDoc}
          onDelete={(id) => {
            // Close the tab too if it happens to be open, so the app never
            // shows a conversation the store no longer has.
            closeTab(`h${id}`)
            /* A delete that fails has to be visible, because the optimistic
             * close makes it look like it worked: the row leaves the palette
             * and comes back on the next reload, which reads as the app
             * losing track rather than as a request that never landed.
             * Nothing else here can carry the message -- the palette has
             * already closed -- so it goes where a failure is durable. */
            void del(`/v2/sessions/history/${id}`).then((ok) => {
              if (!ok) console.error(`[noctis] could not delete session ${id};`
                                   + ' it is still in history')
            })
          }}
          onClose={() => setPalette(false)}
        />
      )}

      {doc && <Reader path={doc} onClose={() => setDoc(null)} />}

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

      {/* Last in the stack, so it paints above every other overlay: the
          session is blocked inside a tool call until this is answered, which
          makes it the one question that must not sit behind a picker you
          happened to leave open. Only the oldest is shown -- answering it
          reveals the next, so what you are reading is always the request that
          has been waiting longest rather than a pile of them at once. */}
      {permissionRequests.length > 0 && (
        <PermissionRequest request={permissionRequests[0]} onDecide={decidePermission} />
      )}
    </div>
  )
}

/* The non-chat views are stubs at this stage. They exist so the rail is
 * honest -- a nav item that goes nowhere is worse than one that says "not
 * built yet" -- and so the shell's layout is exercised at every width. */
function Pane({ view, limits, mode, cwd, accent }: {
  view: string
  limits?: { five_hour: Window; seven_day: Window } | null
  mode: Mode
  cwd: string
  accent: string
}) {
  if (view === 'stats') return <Stats limits={limits} />
  /* Full-bleed, not inside the 840px reading column: a terminal is sized in
     rows and columns, and boxing it would waste half the width the CLI is
     laying its own output out against.

     Keyed by mode and cwd so switching either opens a new session rather
     than pointing an existing one somewhere it was not started. */
  if (view === 'terminal') {
    return (
      <div className="min-h-0 flex-1">
        <Terminal key={`${mode}:${cwd}`} id={`${mode}:${cwd}`}
                  mode={mode} cwd={cwd} accent={accent} />
      </div>
    )
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[840px] px-8 pb-8 pt-7">
        {view === 'brief' && <Fetched<BriefPayload> path="/v2/brief" what="the brief" render={(d) => <Brief data={d} />} />}
        {view === 'inbox' && <Fetched<InboxPayload> path="/v2/inbox" what="the inbox" render={(d) => <Inbox data={d} />} />}
        {view === 'settings' && <Settings />}
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

        <Activity days={stats === null || stats === false ? stats : stats.activity} />

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
              <div className="grid grid-cols-[auto_1fr_auto] items-center gap-x-[14px] gap-y-[9px] font-mono text-[11.5px]">
                {(() => {
                  // The three bars compare with each other, so they share
                  // one scale rather than each inventing its own.
                  const max = Math.max(
                    stats.lifetime.input, stats.lifetime.output,
                    stats.lifetime.cached, stats.lifetime.cache_write,
                  )
                  return (
                    <>
                      <Row label="input" value={stats.lifetime.input} max={max} tone="var(--color-ink-dim)" />
                      <Row label="output" value={stats.lifetime.output} max={max} tone="var(--color-faber)" />
                      <Row label="cache read" value={stats.lifetime.cached} max={max} tone="var(--color-good)" />
                      {/* Was missing entirely, and is routinely the largest
                          of the four — leaving it out is why the totals could
                          not be reconciled against the cost beside them. */}
                      <Row label="cache write" value={stats.lifetime.cache_write} max={max} tone="var(--color-noctua)" />
                    </>
                  )
                })()}
              </div>

              {/* Shown rather than folded into the totals above. The CLI runs
                  small background tasks on a cheaper tier, and on a measured
                  turn that was 899 of 901 input tokens -- so a page that
                  reported only the model you chose would be wrong by two
                  orders of magnitude while looking perfectly reasonable. */}
              <ListPrice turns={stats.lifetime.turns} />
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

/* One token count with a bar.
 *
 * Both halves of this were wrong once the data became real. The suffix was a
 * hardcoded "M" — true of the mock values, which were in millions, and a
 * six-orders-of-magnitude overstatement of a raw count. And the bar divided
 * by 950.5, the mock's own largest value, so every real number pegged it at
 * 100% and the three bars conveyed nothing at all.
 *
 * The bar is now relative to the largest value beside it, which is the only
 * comparison it can honestly make.
 */
function Row({
  label,
  value,
  max,
  tone,
}: {
  label: string
  value: number
  max: number
  tone: string
}) {
  const pct = max > 0 ? Math.max(0.5, (value / max) * 100) : 0
  return (
    <>
      <span className="text-ink-dim">{label}</span>
      <span className="h-[5px] min-w-[60px] overflow-hidden rounded-sm border border-line bg-ground">
        <span className="block h-full" style={{ width: `${pct}%`, background: tone }} />
      </span>
      <span className="text-right tabular-nums text-ink" title={value.toLocaleString()}>
        {compact(value)}
      </span>
    </>
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

const truncate = (s: string) => (s.length > 22 ? `${s.slice(0, 22)}…` : s)

/** `/Users/me/Developer/x` → `~/Developer/x`. The home prefix is the least
 *  informative part of a path and the bar has one line for it. */
function shortenHome(path: string): string {
  const m = path.match(/^\/Users\/[^/]+(\/.*)?$/)
  return m ? `~${m[1] ?? ''}` : path
}

const DRAFTS_KEY = 'noctis.drafts'

/** Drafts from the last session, or an empty General draft. */
function loadDrafts(): Record<string, string> {
  try {
    const raw = localStorage.getItem(DRAFTS_KEY)
    if (!raw) return { t0: '' }
    const parsed = JSON.parse(raw) as Record<string, string>
    // Only strings: anything else means the shape changed under us, and a
    // draft is not worth trusting a stale format for.
    const clean = Object.fromEntries(
      Object.entries(parsed).filter(([, v]) => typeof v === 'string'),
    )
    return { t0: '', ...clean }
  } catch {
    return { t0: '' }
  }
}

/** The list-price line under Stats' lifetime tokens. Its own fetch, so a
 *  slow or absent billing route cannot hold up the counts above it. */
function ListPrice({ turns }: { turns: number }) {
  const data = useFetched<BillingPayload>('/v2/billing')
  return data ? <ListPriceFact data={data} totalTurns={turns} /> : null
}


/** A title from the conversation's first real question — what you came to it
 *  for, which beats anything derivable from the reply. */
function promoteTitle(session: SessionState): string {
  const first = session.blocks.find((b) => b.kind === 'user')
  if (!first || first.kind !== 'user') return 'Untitled conversation'
  const line = first.text.trim().split('\n')[0].replace(/[?.!]+$/, '')
  return line.length > 60 ? `${line.slice(0, 60).trimEnd()}…` : line
}
