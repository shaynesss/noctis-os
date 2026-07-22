// Profile overlay — mounts over the world without unmounting it. Per-mode
// content layout locked in wiki/Noctis OS/Interface.md's "Profile overlay
// card system" section.
import { useEffect, useRef, useState } from 'react'
import {
  acceptInboxItem,
  createJob,
  getArchivedProposal,
  getInbox,
  getJobLog,
  getModeState,
  getNightshiftHistory,
  launchSession,
  rejectInboxItem,
  updateJob,
  type HistoryEntry,
  type InboxItem,
  type Mode,
  type ModeState,
} from './api'
import { MODE_META } from './modes'

interface ProfileOverlayProps {
  mode: Mode | null
  onClose: () => void
}

interface InboxNotice {
  kind: 'success' | 'error'
  text: string
}

const INBOX_NOTICE_TIMEOUT_MS = 2500

export default function ProfileOverlay({ mode, onClose }: ProfileOverlayProps) {
  const [state, setState] = useState<ModeState | null>(null)
  const [inbox, setInbox] = useState<InboxItem[]>([])
  const [newBuildOpen, setNewBuildOpen] = useState(false)
  const [inboxNotice, setInboxNotice] = useState<InboxNotice | null>(null)
  const inboxNoticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState<HistoryEntry[] | null>(null)
  const [expandedHistorySlug, setExpandedHistorySlug] = useState<string | null>(null)
  const [expandedProposals, setExpandedProposals] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!mode) return
    setState(null)
    getModeState(mode).then(setState)
    if (mode === 'nightshift') {
      getInbox().then(setInbox)
      // History is lazy-loaded on demand (below), not here -- it only
      // grows, and most opens of Echo's card are to review the inbox, not
      // to look back.
      setHistoryOpen(false)
      setHistory(null)
      setExpandedHistorySlug(null)
      setExpandedProposals({})
    }
  }, [mode])

  useEffect(() => {
    return () => {
      if (inboxNoticeTimer.current) clearTimeout(inboxNoticeTimer.current)
    }
  }, [])

  if (!mode) return null
  const meta = MODE_META[mode]

  async function handleLaunch() {
    if (!mode) return
    if (mode === 'dev') {
      setNewBuildOpen(true)
      return
    }
    await launchSession(mode)
  }

  async function handleResumeJob(jobSlug: string) {
    if (!mode) return
    // Resuming is the natural point to clear a flagged job -- staleness.py
    // can set the flag but nothing could ever clear it (found 2026-07-21
    // when noctis-os's own job got flagged since all the real work
    // happened via direct file edits, never a launched session, so the
    // telemetry hooks that would prove it alive never fired).
    await updateJob(mode, jobSlug, { flagged: false })
    await launchSession(mode, jobSlug)
    setState(await getModeState(mode))
  }

  // Nothing could ever create a job before this -- Faber's card stayed
  // idle regardless of real work happening, since "launch stays available
  // even idle, since that's how a new build starts" (Interface.md) had no
  // actual mechanism behind it. Replaced the original window.prompt
  // placeholder with a real designed form (see the new-build-modal render
  // below and NewBuildModal component).
  async function submitNewDevBuild(name: string, projectPath: string) {
    const slug = name
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '')
    if (!slug) return

    await createJob('dev', slug, name, projectPath)
    await launchSession('dev', slug)
    setState(await getModeState('dev'))
    setNewBuildOpen(false)
  }

  function showInboxNotice(notice: InboxNotice) {
    if (inboxNoticeTimer.current) clearTimeout(inboxNoticeTimer.current)
    setInboxNotice(notice)
    inboxNoticeTimer.current = setTimeout(() => setInboxNotice(null), INBOX_NOTICE_TIMEOUT_MS)
  }

  async function handleDecision(itemId: string, decision: 'accept' | 'reject') {
    const action = decision === 'accept' ? acceptInboxItem : rejectInboxItem
    try {
      await action(itemId)
      setInbox((prev) => prev.filter((item) => item.slug !== itemId))
      // Accept/reject never open a session (apply.py's write is a
      // deterministic backend edit, not a launch) -- the row vanishing was
      // the only confirmation, indistinguishable from a silent no-op.
      showInboxNotice({ kind: 'success', text: decision === 'accept' ? 'Accepted and applied.' : 'Rejected.' })
    } catch (err) {
      // Previously unhandled -- a failed request (e.g. accept's diff-apply
      // 422 on a stale/malformed proposal) left the item sitting in the
      // list with zero feedback, indistinguishable from the button doing
      // nothing at all.
      showInboxNotice({
        kind: 'error',
        text: err instanceof Error ? err.message : `Failed to ${decision} ${itemId}`,
      })
      return
    }
    // Keep an already-open history list in sync with the decision that
    // just happened, rather than leaving it stale until the card is
    // reopened.
    if (historyOpen) {
      getNightshiftHistory().then(setHistory)
    }
  }

  async function toggleHistory() {
    if (!historyOpen && history === null) {
      setHistory(await getNightshiftHistory())
    }
    setHistoryOpen((prev) => !prev)
  }

  async function toggleHistoryItem(slug: string) {
    if (expandedHistorySlug === slug) {
      setExpandedHistorySlug(null)
      return
    }
    setExpandedHistorySlug(slug)
    if (!(slug in expandedProposals)) {
      try {
        const { proposal } = await getArchivedProposal(slug)
        setExpandedProposals((prev) => ({ ...prev, [slug]: proposal }))
      } catch {
        setExpandedProposals((prev) => ({ ...prev, [slug]: '(proposal file no longer available)' }))
      }
    }
  }

  // Settings triggers were previously detect-only -- nothing let you launch
  // a session actually scoped to addressing one (or running a
  // completeness check) versus just opening a bare methodology dump.
  // `notes` becomes the job's context.md prose, which is what
  // POST /session/launch actually injects into the launch prompt.
  async function startScopedSettingsTask(taskSlug: string, name: string, notes: string) {
    const slug = `${taskSlug}-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}`
    try {
      await createJob('settings', slug, name, undefined, notes)
    } catch {
      // job for today already exists (re-clicked) -- launch it as-is
    }
    await launchSession('settings', slug)
  }

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div
        className={`overlay${mode === 'nightshift' ? ' overlay-echo' : ''}`}
        role="dialog"
        aria-label={`${meta.name} profile`}
        style={{ ['--accent' as string]: `var(${meta.accentVar})` }}
      >
        <div className="header">
          <h2>
            <Typewriter text={meta.name.toUpperCase()} />
          </h2>
          <button type="button" className="close" aria-label="Close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="body">
          {state &&
            renderBody(
              mode,
              state,
              inbox,
              inboxNotice,
              { open: historyOpen, entries: history, expandedSlug: expandedHistorySlug, expandedProposals },
              handleDecision,
              handleResumeJob,
              startScopedSettingsTask,
              toggleHistory,
              toggleHistoryItem,
            )}
        </div>

        {mode !== 'nightshift' && (
          <div className="launch-row">
            <button type="button" className="launch-btn" onClick={handleLaunch}>
              {mode === 'dev' && (state?.jobs?.length ?? 0) > 0 ? '+ NEW BUILD' : 'LAUNCH SESSION'}
            </button>
          </div>
        )}
      </div>

      {newBuildOpen && (
        <NewBuildModal onCancel={() => setNewBuildOpen(false)} onSubmit={submitNewDevBuild} />
      )}
    </>
  )
}

function NewBuildModal({
  onCancel,
  onSubmit,
}: {
  onCancel: () => void
  onSubmit: (name: string, projectPath: string) => void
}) {
  const [name, setName] = useState('')
  const [projectPath, setProjectPath] = useState('')
  const canSubmit = name.trim().length > 0 && projectPath.trim().length > 0

  return (
    <>
      <div className="scrim new-build-scrim" onClick={onCancel} />
      <div
        className="new-build-modal"
        role="dialog"
        aria-label="Start a new build"
        style={{ ['--accent' as string]: 'var(--faber)' }}
      >
        <h3>NEW BUILD</h3>
        <label>
          <span>name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Noctis OS"
            autoFocus
          />
        </label>
        <label>
          <span>project path</span>
          <input
            type="text"
            value={projectPath}
            onChange={(e) => setProjectPath(e.target.value)}
            placeholder="/Users/you/Developer/project"
          />
        </label>
        <div className="new-build-actions">
          <button type="button" className="new-build-cancel" onClick={onCancel}>
            cancel
          </button>
          <button
            type="button"
            className="new-build-submit"
            disabled={!canSubmit}
            onClick={() => onSubmit(name.trim(), projectPath.trim())}
          >
            create &amp; launch
          </button>
        </div>
      </div>
    </>
  )
}

interface EchoHistoryState {
  open: boolean
  entries: HistoryEntry[] | null
  expandedSlug: string | null
  expandedProposals: Record<string, string>
}

function renderBody(
  mode: Mode,
  state: ModeState,
  inbox: InboxItem[],
  inboxNotice: InboxNotice | null,
  historyState: EchoHistoryState,
  onDecision: (itemId: string, decision: 'accept' | 'reject') => void,
  onResumeJob: (jobSlug: string) => void,
  onStartSettingsTask: (taskSlug: string, name: string, notes: string) => void,
  onToggleHistory: () => void,
  onToggleHistoryItem: (slug: string) => void,
) {
  switch (mode) {
    case 'dev':
      return <FaberBody state={state} onResumeJob={onResumeJob} />
    case 'learn':
      return <NoctuaBody state={state} onResumeJob={onResumeJob} />
    case 'research':
      return <VesperBody state={state} onResumeJob={onResumeJob} />
    case 'settings':
      return <CustosBody state={state} onStartTask={onStartSettingsTask} onResumeJob={onResumeJob} />
    case 'nightshift':
      return (
        <EchoBody
          inbox={inbox}
          notice={inboxNotice}
          onDecision={onDecision}
          history={historyState}
          onToggleHistory={onToggleHistory}
          onToggleHistoryItem={onToggleHistoryItem}
        />
      )
  }
}

const BODY_START_DELAY_MS = 150
const LINE_STAGGER_MS = 220
// Echo's inbox rows carry a full description + rationale sentence, easily
// 3-4x longer than any other card's text -- the default 16ms/char made
// reading a staged proposal feel sluggish, so these get a faster reveal.
const INBOX_TEXT_SPEED_MS = 6

// Shared across every mode that can hold jobs (dev/learn/research/settings —
// the four whose Failure Behavior text promises stale-and-flagged tracking,
// see backend/staleness.py's FLAGGABLE_MODES). Renders nothing when empty so
// modes without an in-flight job look exactly as they did before this
// existed; flagged jobs need to actually be visible somewhere, not just
// tracked server-side, or the backend flag has no interface to land in.
function JobList({
  jobs,
  mode,
  onResumeJob,
}: {
  jobs: ModeState['jobs']
  mode: Mode
  onResumeJob: (jobSlug: string) => void
}) {
  const list = jobs ?? []
  if (list.length === 0) return null
  return (
    <>
      {list.map((job, i) => (
        <div className={`job-row${job.flagged ? ' flagged' : ''}`} key={job.slug}>
          <div>
            <span className="name">
              <Typewriter text={job.name} startDelayMs={BODY_START_DELAY_MS + i * LINE_STAGGER_MS} />
              {job.flagged && <span className="flagged-badge">flagged</span>}
            </span>
            <span className="job-status">
              <Typewriter text={job.status} startDelayMs={BODY_START_DELAY_MS + i * LINE_STAGGER_MS + 80} />
            </span>
            <ActionFeedLine mode={mode} slug={job.slug} />
          </div>
          <div className="job-actions">
            <span className="phase-badge">{job.stage}</span>
            <button type="button" className="resume-btn" onClick={() => onResumeJob(job.slug)}>
              resume
            </button>
          </div>
        </div>
      ))}
    </>
  )
}

function FaberBody({ state, onResumeJob }: { state: ModeState; onResumeJob: (jobSlug: string) => void }) {
  const jobs = state.jobs ?? []
  if (jobs.length === 0) {
    return (
      <p className="idle-note">
        <Typewriter text="no dams under construction. the pond is calm." startDelayMs={BODY_START_DELAY_MS} />
      </p>
    )
  }
  return <JobList jobs={jobs} mode="dev" onResumeJob={onResumeJob} />
}

// The locked entrance style from card-design mockup iteration (Interface.md
// "typewriter reveal... won out over three other animation styles"): card
// *content* types in character by character, not just the card container
// fading/scaling in. speedMs is per-character; startDelayMs staggers
// multiple lines so they type in sequence rather than all at once.
function Typewriter({
  text,
  speedMs = 16,
  startDelayMs = 0,
}: {
  text: string
  speedMs?: number
  startDelayMs?: number
}) {
  const [count, setCount] = useState(0)

  useEffect(() => {
    setCount(0)
    if (!text) return
    let interval: ReturnType<typeof setInterval> | undefined
    const timeout = setTimeout(() => {
      interval = setInterval(() => {
        setCount((c) => {
          if (c >= text.length) {
            if (interval) clearInterval(interval)
            return c
          }
          return c + 1
        })
      }, speedMs)
    }, startDelayMs)
    return () => {
      clearTimeout(timeout)
      if (interval) clearInterval(interval)
    }
  }, [text, speedMs, startDelayMs])

  return <>{text.slice(0, count)}</>
}

// Polls this job's runtime action log (backend/hooks/log_action.py, one
// line per tool call) and shows the most recent line — a live pulse under
// the job row rather than a full feed, to hold the card's fixed height.
function ActionFeedLine({ mode, slug }: { mode: Mode; slug: string }) {
  const [lastLine, setLastLine] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const poll = () => {
      getJobLog(mode, slug, 1)
        .then(({ lines }) => {
          if (!cancelled) setLastLine(lines[0] ?? null)
        })
        .catch(() => {})
    }
    poll()
    const interval = setInterval(poll, 5000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [mode, slug])

  if (!lastLine) return null
  return <span className="action-feed-line">{lastLine}</span>
}

function NoctuaBody({ state, onResumeJob }: { state: ModeState; onResumeJob: (jobSlug: string) => void }) {
  const deepDue = typeof state.deep_due === 'number' ? state.deep_due : 0
  const deepRetained = typeof state.deep_retained === 'number' ? state.deep_retained : 0
  const shallowDone = typeof state.shallow_done === 'number' ? state.shallow_done : 0
  return (
    <>
      <JobList jobs={state.jobs} mode="learn" onResumeJob={onResumeJob} />
      <div className="stat-blocks">
        <div className="stat-block">
          <span className="stat-label">DEEP</span>
          <span className="stat-main">
            <Typewriter text={`${deepDue} due`} startDelayMs={BODY_START_DELAY_MS} />
          </span>
          <span className="stat-sub">
            <Typewriter text={`${deepRetained} retained`} startDelayMs={BODY_START_DELAY_MS + LINE_STAGGER_MS} />
          </span>
        </div>
        <div className="stat-block">
          <span className="stat-label">SHALLOW</span>
          <span className="stat-main">
            <Typewriter text={`${shallowDone} done`} startDelayMs={BODY_START_DELAY_MS + LINE_STAGGER_MS * 2} />
          </span>
        </div>
      </div>
    </>
  )
}

function VesperBody({ state, onResumeJob }: { state: ModeState; onResumeJob: (jobSlug: string) => void }) {
  const adopt = (state.adopt_counts as Record<string, number> | undefined) ?? {}
  const inquiry = (state.inquiry_counts as Record<string, number> | undefined) ?? {}
  const adoptBadges = [
    { cls: 'good', text: `adopt ${adopt.adopt ?? 0}` },
    { cls: 'bad', text: `reject ${adopt.reject ?? 0}` },
    { cls: 'neutral', text: `park ${adopt.park ?? 0}` },
  ]
  const inquiryBadges = [
    { cls: 'good', text: `sound ${inquiry.sound ?? 0}` },
    { cls: 'good', text: `promising ${inquiry.promising ?? 0}` },
    { cls: 'bad', text: `weak ${inquiry.weak ?? 0}` },
    { cls: 'bad', text: `hype ${inquiry.hype ?? 0}` },
  ]
  return (
    <>
      <JobList jobs={state.jobs} mode="research" onResumeJob={onResumeJob} />
      <div className="stat-blocks">
        <div className="stat-block">
          <span className="stat-label">ADOPT</span>
          <div className="verdict-badges">
            {adoptBadges.map((badge, i) => (
              <span className={`verdict ${badge.cls}`} key={badge.text}>
                <Typewriter text={badge.text} startDelayMs={BODY_START_DELAY_MS + i * 90} speedMs={10} />
              </span>
            ))}
          </div>
        </div>
        <div className="stat-block">
          <span className="stat-label">INQUIRY</span>
          <div className="verdict-badges">
            {inquiryBadges.map((badge, i) => (
              <span className={`verdict ${badge.cls}`} key={badge.text}>
                <Typewriter
                  text={badge.text}
                  startDelayMs={BODY_START_DELAY_MS + LINE_STAGGER_MS + i * 90}
                  speedMs={10}
                />
              </span>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}

// What "address this trigger" actually means, per settings.md's own
// definitions -- the session reads the real specifics itself (it has vault
// Read access once launched); this is the starting instruction, not a
// pre-digested summary the interface would have to keep in sync separately.
const TRIGGER_TASK_NOTES: Record<string, string> = {
  friction:
    "Address Custos's friction trigger: read modes/*/lessons.md for entries tagged FRICTION: since the last distillation pass (modes/settings/state.md's lessons_distilled_through cursor). Propose a methodology diff per settings.md's Propose stage, citing the specific entries as evidence.",
  accumulation:
    "Address Custos's accumulation trigger: modes/*/lessons.md have grown past their lessons_distilled_through cursor. Distill the new entries into proposed methodology diffs per settings.md's Propose stage.",
  suspicion:
    "Address Custos's suspicion trigger: at least one mode's state.md hasn't been modified in 7+ days. Audit for drift, staleness, or a vault smell per settings.md's Audit stage.",
}

const COMPLETENESS_CHECK_NOTES =
  "Run a spec-completeness audit on Noctis OS itself: diff noctis-os/SPEC.md and noctis-os/CLAUDE.md against second-brain/wiki/Noctis OS/*.md. Flag anything discussed and locked in the wiki but never pulled into SPEC.md, and vice versa, per settings.md's Audit stage."

function CustosBody({
  state,
  onStartTask,
  onResumeJob,
}: {
  state: ModeState
  onStartTask: (taskSlug: string, name: string, notes: string) => void
  onResumeJob: (jobSlug: string) => void
}) {
  const triggers = (state.triggers as Record<string, boolean> | undefined) ?? {}
  const diffsAwaiting = typeof state.diffs_awaiting_review === 'number' ? state.diffs_awaiting_review : 0
  const jobs = state.jobs ?? []
  const hasTriggers = triggers.friction || triggers.accumulation || triggers.suspicion

  const completenessCheckRow = (
    <button
      type="button"
      className="resume-btn completeness-check-btn"
      onClick={() => onStartTask('completeness-check', 'Completeness check', COMPLETENESS_CHECK_NOTES)}
    >
      run completeness check
    </button>
  )

  if (!hasTriggers && diffsAwaiting === 0 && jobs.length === 0) {
    return (
      <>
        <p className="idle-note">
          <Typewriter text="nothing to tend. the sett holds." startDelayMs={BODY_START_DELAY_MS} />
        </p>
        <div className="settings-actions">{completenessCheckRow}</div>
      </>
    )
  }
  return (
    <>
      <JobList jobs={jobs} mode="settings" onResumeJob={onResumeJob} />
      <div className="trigger-list">
        {(['friction', 'accumulation', 'suspicion'] as const).map((trigger, i) => (
          <div className="trigger-row" key={trigger}>
            <span className={`trigger-badge${triggers[trigger] ? ' lit' : ''}`}>
              <Typewriter text={trigger} startDelayMs={BODY_START_DELAY_MS + i * 90} speedMs={10} />
            </span>
            {triggers[trigger] && (
              <button
                type="button"
                className="resume-btn"
                onClick={() => onStartTask(`address-${trigger}`, `Address ${trigger}`, TRIGGER_TASK_NOTES[trigger])}
              >
                address
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="stat-block">
        <span className="stat-label">DIFFS AWAITING REVIEW</span>
        <span className="stat-main">
          <Typewriter text={String(diffsAwaiting)} startDelayMs={BODY_START_DELAY_MS + LINE_STAGGER_MS} />
        </span>
      </div>
      <div className="settings-actions">{completenessCheckRow}</div>
    </>
  )
}

function EchoBody({
  inbox,
  notice,
  onDecision,
  history,
  onToggleHistory,
  onToggleHistoryItem,
}: {
  inbox: InboxItem[]
  notice: InboxNotice | null
  onDecision: (itemId: string, decision: 'accept' | 'reject') => void
  history: EchoHistoryState
  onToggleHistory: () => void
  onToggleHistoryItem: (slug: string) => void
}) {
  const noticeRow = notice && <p className={`inbox-notice ${notice.kind}`}>{notice.text}</p>
  const historySection = (
    <EchoHistorySection history={history} onToggle={onToggleHistory} onToggleItem={onToggleHistoryItem} />
  )
  if (inbox.length === 0) {
    // Notice still needs to render here -- accepting/rejecting the last
    // remaining item drops inbox to empty in the same render, and this
    // branch used to bail before the confirmation ever showed.
    return (
      <>
        {noticeRow}
        <p className="idle-note">
          <Typewriter text="inbox empty." startDelayMs={BODY_START_DELAY_MS} />
        </p>
        {historySection}
      </>
    )
  }
  return (
    <>
      {noticeRow}
      {inbox.map((item, i) => (
        <div className="inbox-row" key={item.slug}>
          <span
            className="origin-tag"
            style={{ ['--accent' as string]: `var(${MODE_META[item.origin_mode].accentVar})` }}
          >
            {MODE_META[item.origin_mode].name}
          </span>
          <span className="inbox-desc">
            <Typewriter
              text={item.description}
              startDelayMs={BODY_START_DELAY_MS + i * LINE_STAGGER_MS}
              speedMs={INBOX_TEXT_SPEED_MS}
            />
            <span className="inbox-rationale">
              <Typewriter
                text={item.rationale}
                startDelayMs={BODY_START_DELAY_MS + i * LINE_STAGGER_MS + 120}
                speedMs={INBOX_TEXT_SPEED_MS}
              />
            </span>
          </span>
          {item.confidence && <span className={`confidence ${item.confidence}`}>{item.confidence}</span>}
          <span className="inbox-actions">
            <button type="button" onClick={() => onDecision(item.slug, 'accept')}>
              Accept
            </button>
            <button type="button" onClick={() => onDecision(item.slug, 'reject')}>
              Reject
            </button>
          </span>
        </div>
      ))}
      {historySection}
    </>
  )
}

function EchoHistorySection({
  history,
  onToggle,
  onToggleItem,
}: {
  history: EchoHistoryState
  onToggle: () => void
  onToggleItem: (slug: string) => void
}) {
  return (
    <div className="history-section">
      <button type="button" className="history-toggle" onClick={onToggle}>
        {history.open ? '▾ Hide history' : '▸ History'}
      </button>
      {history.open && (
        <div className="history-list">
          {history.entries === null || history.entries.length === 0 ? (
            <p className="idle-note">
              {history.entries === null ? 'loading…' : 'no past decisions yet.'}
            </p>
          ) : (
            history.entries.map((entry) => (
              <div className="history-row" key={`${entry.slug}-${entry.timestamp}`}>
                <div className="history-row-summary" onClick={() => onToggleItem(entry.slug)}>
                  <span
                    className="origin-tag"
                    style={{ ['--accent' as string]: `var(${MODE_META[entry.origin_mode].accentVar})` }}
                  >
                    {MODE_META[entry.origin_mode].name}
                  </span>
                  <span className={`decision-badge ${entry.decision}`}>{entry.decision}</span>
                  <span className="history-desc">{entry.description}</span>
                  <span className="history-timestamp">{entry.timestamp}</span>
                </div>
                {history.expandedSlug === entry.slug && (
                  <pre className="history-proposal">
                    {history.expandedProposals[entry.slug] ?? 'loading…'}
                  </pre>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
