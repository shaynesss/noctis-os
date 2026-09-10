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
import { BottomBar, Composer, OverageBanner, Rail, TabBar, TitleStrip } from './Chrome'
import {
  del, emptyFold, fold, get, post, readImage, runSession,
  type Attachment, type HistorySession, type HistoryTranscript,
  type Stats as StatsPayload, type Window,
} from './engine'
import { Unreachable } from './Async'
import { useFetched } from './useFetched'
import { hasImage } from './clipboard'
import {
  CommandMenu, ModelPicker, PermissionPicker, PromotePicker, type ModelOption,
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
  EMPTY_SESSION, EMPTY_TAB, MODE_ACCENT, MODE_INFO, MODE_LABEL, PERMISSION_CYCLE,
  type Mode, type Permission, type SessionState, type Tab,
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

  /* One abort per tab. Closing a tab or quitting has to actually stop the
   * stream: an orphaned reader keeps the connection open and the session
   * keeps burning the 5h window with nothing rendering it. */
  const aborts = useRef<Record<string, AbortController>>({})

  // Newest rolling-window report, for the status bar. Null until a session
  // has reported one -- see the backend's known:false for why that is not
  // the same as zero.
  const [limits, setLimits] = useState<
    { five_hour: Window; seven_day: Window; using_overage?: boolean } | null
  >(null)

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
        setSessions((s) => ({
          ...s,
          [tabId]: {
            ...s[tabId],
            blocks: state.blocks,
            thinking: state.thinking,
            context: state.context,
            ranModel: state.model ?? s[tabId].ranModel,
            engineId: state.sessionId ?? s[tabId].engineId,
          },
        }))
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
      setSessions((s) => ({
        ...s,
        [tabId]: {
          ...s[tabId],
          busy: false,
          thinking: null,
          startedAt: null,
          // Only for a turn that ran to completion: a stopped one already
          // says "Stopped." and does not need a duration beside it.
          lastTurn: stopped
            ? s[tabId].lastTurn
            : { seconds: (Date.now() - (withUser.startedAt ?? Date.now())) / 1000, at: Date.now() },
          // Recorded in the transcript rather than left silent. A reply that
          // simply stops mid-sentence is indistinguishable from one that
          // finished badly, and you would not know whether to retry.
          blocks: stopped
            ? [...s[tabId].blocks, { kind: 'error', message: 'Stopped.', fatal: false }]
            : s[tabId].blocks,
        },
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
    // Only when there is one. An empty launch opens the tab and waits.
    if (req.prompt.trim()) blocks.push({ kind: 'user', text: req.prompt, at: now() })

    // At most one session beside General. The engine's own cap is two
    // concurrent, so a third tab could not run anyway -- and the point of
    // the second is overflow, for when one task is too much to hold in the
    // main thread of work, not a filing system.
    setTabs((ts) => [ts[0], { id, mode: req.mode, label }])
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
        cwd: `~/Developer/${tab.label.split(' · ')[1] ?? ''}`,
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
      cwd: full.cwd ?? '~', engineId: full.engine_id ?? undefined,
    } }))
    setDrafts((d) => ({ ...d, [tabId]: '' }))
    setActiveTab(tabId)
    setView('chat')
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

      // Shift+Tab cycles permission, the affordance carried over from the
      // CLI's TUI. Wrapping past the end returns to `plan`, so the cycle
      // never strands you at the permissive end.
      if (e.key === 'Tab' && e.shiftKey && !e.metaKey) {
        e.preventDefault()
        e.stopPropagation()
        setPermission((p) => PERMISSION_CYCLE[(PERMISSION_CYCLE.indexOf(p) + 1) % PERMISSION_CYCLE.length])
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

  /* Resume the General session on launch.
   *
   * One long-running General session that carries many tasks, not a tab per
   * conversation. Restoring four made the strip a graveyard of every prompt
   * ever typed, and none of them were the one you meant to continue.
   *
   * So General is continuous: it reopens the most recent General
   * conversation and keeps going, which is what makes it the front door
   * rather than a scratch pad that resets. Everything else stays in history,
   * reachable by search.
   */
  useEffect(() => {
    let live = true
    void (async () => {
      const listed = await get<{ sessions: HistorySession[] }>('/v2/sessions/history?limit=20')
      if (!live || !listed) return
      const latest = listed.sessions.find((s) => s.mode === 'general' && s.resumable)
      if (!latest) return
      const full = await get<HistoryTranscript>(`/v2/sessions/history/${latest.id}`)
      if (!live || !full || full.blocks.length === 0) return
      setSessions((prev) => ({
        ...prev,
        t0: {
          ...prev.t0,
          blocks: full.blocks,
          cwd: latest.cwd ?? prev.t0.cwd,
          engineId: latest.engine_id ?? undefined,
        },
      }))

      /* Fetched after the transcript, not with it. Generating a recap costs
       * an engine call and takes seconds; blocking the restored conversation
       * on it would trade the thing you came back for against the sentence
       * describing it. */
      const r = await get<{ recap: string | null }>(`/v2/sessions/history/${latest.id}/recap`)
      if (live && r?.recap) {
        setSessions((prev) => ({ ...prev, t0: { ...prev.t0, recap: r.recap } }))
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
          <Pane view={view} limits={limits} />
        )}

        </div>
      </div>

      <BottomBar
        limits={limits}
        working={tabs.filter((t) => sessions[t.id]?.busy).map((t) => sessions[t.id].mode)}
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
            permission={permission}
            onCyclePermission={() =>
              setPermission(PERMISSION_CYCLE[(PERMISSION_CYCLE.indexOf(permission) + 1) % PERMISSION_CYCLE.length])
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
            void del(`/v2/sessions/history/${id}`)
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
