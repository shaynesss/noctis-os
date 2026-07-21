// Profile overlay — mounts over the world without unmounting it. Per-mode
// content layout locked in wiki/Noctis OS/Interface.md's "Profile overlay
// card system" section.
import { useEffect, useState } from 'react'
import {
  acceptInboxItem,
  createJob,
  getInbox,
  getJobLog,
  getModeState,
  launchSession,
  rejectInboxItem,
  type InboxItem,
  type Mode,
  type ModeState,
} from './api'
import { MODE_META } from './modes'

interface ProfileOverlayProps {
  mode: Mode | null
  onClose: () => void
}

export default function ProfileOverlay({ mode, onClose }: ProfileOverlayProps) {
  const [state, setState] = useState<ModeState | null>(null)
  const [inbox, setInbox] = useState<InboxItem[]>([])

  useEffect(() => {
    if (!mode) return
    setState(null)
    getModeState(mode).then(setState)
    if (mode === 'nightshift') {
      getInbox().then(setInbox)
    }
  }, [mode])

  if (!mode) return null
  const meta = MODE_META[mode]

  async function handleLaunch() {
    if (!mode) return
    if (mode === 'dev') {
      await startNewDevBuild()
      return
    }
    await launchSession(mode)
  }

  async function handleResumeJob(jobSlug: string) {
    if (!mode) return
    await launchSession(mode, jobSlug)
  }

  // Nothing could ever create a job before this -- Faber's card stayed
  // idle regardless of real work happening, since "launch stays available
  // even idle, since that's how a new build starts" (Interface.md) had no
  // actual mechanism behind it. window.prompt is a placeholder for a real
  // designed input, not the intended final UI -- it exists so starting a
  // build is possible at all.
  async function startNewDevBuild() {
    const name = window.prompt('New build name?')
    if (!name) return
    const projectPath = window.prompt('Project path (absolute)?')
    if (!projectPath) return
    const slug = name
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '')
    if (!slug) return

    await createJob('dev', slug, name, projectPath)
    await launchSession('dev', slug)
    setState(await getModeState('dev'))
  }

  async function handleDecision(itemId: string, decision: 'accept' | 'reject') {
    const action = decision === 'accept' ? acceptInboxItem : rejectInboxItem
    await action(itemId)
    setInbox((prev) => prev.filter((item) => item.slug !== itemId))
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

        <div className="body">{state && renderBody(mode, state, inbox, handleDecision, handleResumeJob)}</div>

        {mode !== 'nightshift' && (
          <div className="launch-row">
            <button type="button" className="launch-btn" onClick={handleLaunch}>
              {mode === 'dev' && (state?.jobs?.length ?? 0) > 0 ? '+ NEW BUILD' : 'LAUNCH SESSION'}
            </button>
          </div>
        )}
      </div>
    </>
  )
}

function renderBody(
  mode: Mode,
  state: ModeState,
  inbox: InboxItem[],
  onDecision: (itemId: string, decision: 'accept' | 'reject') => void,
  onResumeJob: (jobSlug: string) => void,
) {
  switch (mode) {
    case 'dev':
      return <FaberBody state={state} onResumeJob={onResumeJob} />
    case 'learn':
      return <NoctuaBody state={state} />
    case 'research':
      return <VesperBody state={state} />
    case 'settings':
      return <CustosBody state={state} />
    case 'nightshift':
      return <EchoBody inbox={inbox} onDecision={onDecision} />
  }
}

const BODY_START_DELAY_MS = 150
const LINE_STAGGER_MS = 220

function FaberBody({ state, onResumeJob }: { state: ModeState; onResumeJob: (jobSlug: string) => void }) {
  const jobs = state.jobs ?? []
  if (jobs.length === 0) {
    return (
      <p className="idle-note">
        <Typewriter text="no dams under construction. the pond is calm." startDelayMs={BODY_START_DELAY_MS} />
      </p>
    )
  }
  return (
    <>
      {jobs.map((job, i) => (
        <div className={`job-row${job.flagged ? ' flagged' : ''}`} key={job.slug}>
          <div>
            <span className="name">
              <Typewriter text={job.name} startDelayMs={BODY_START_DELAY_MS + i * LINE_STAGGER_MS} />
              {job.flagged && <span className="flagged-badge">flagged</span>}
            </span>
            <span className="job-status">
              <Typewriter text={job.status} startDelayMs={BODY_START_DELAY_MS + i * LINE_STAGGER_MS + 80} />
            </span>
            <ActionFeedLine mode="dev" slug={job.slug} />
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

function NoctuaBody({ state }: { state: ModeState }) {
  const deepDue = typeof state.deep_due === 'number' ? state.deep_due : 0
  const deepRetained = typeof state.deep_retained === 'number' ? state.deep_retained : 0
  const shallowDone = typeof state.shallow_done === 'number' ? state.shallow_done : 0
  return (
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
  )
}

function VesperBody({ state }: { state: ModeState }) {
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
  )
}

function CustosBody({ state }: { state: ModeState }) {
  const triggers = (state.triggers as Record<string, boolean> | undefined) ?? {}
  const diffsAwaiting = typeof state.diffs_awaiting_review === 'number' ? state.diffs_awaiting_review : 0
  const hasTriggers = triggers.friction || triggers.accumulation || triggers.suspicion
  if (!hasTriggers && diffsAwaiting === 0) {
    return (
      <p className="idle-note">
        <Typewriter text="nothing to tend. the sett holds." startDelayMs={BODY_START_DELAY_MS} />
      </p>
    )
  }
  return (
    <>
      <div className="trigger-list">
        {(['friction', 'accumulation', 'suspicion'] as const).map((trigger, i) => (
          <span key={trigger} className={`trigger-badge${triggers[trigger] ? ' lit' : ''}`}>
            <Typewriter text={trigger} startDelayMs={BODY_START_DELAY_MS + i * 90} speedMs={10} />
          </span>
        ))}
      </div>
      <div className="stat-block">
        <span className="stat-label">DIFFS AWAITING REVIEW</span>
        <span className="stat-main">
          <Typewriter text={String(diffsAwaiting)} startDelayMs={BODY_START_DELAY_MS + LINE_STAGGER_MS} />
        </span>
      </div>
    </>
  )
}

function EchoBody({
  inbox,
  onDecision,
}: {
  inbox: InboxItem[]
  onDecision: (itemId: string, decision: 'accept' | 'reject') => void
}) {
  if (inbox.length === 0) {
    return (
      <p className="idle-note">
        <Typewriter text="inbox empty." startDelayMs={BODY_START_DELAY_MS} />
      </p>
    )
  }
  return (
    <>
      {inbox.map((item, i) => (
        <div className="inbox-row" key={item.slug}>
          <span
            className="origin-tag"
            style={{ ['--accent' as string]: `var(${MODE_META[item.origin_mode].accentVar})` }}
          >
            {MODE_META[item.origin_mode].name}
          </span>
          <span className="inbox-desc">
            <Typewriter text={item.description} startDelayMs={BODY_START_DELAY_MS + i * LINE_STAGGER_MS} />
            <span className="inbox-rationale">
              <Typewriter
                text={item.rationale}
                startDelayMs={BODY_START_DELAY_MS + i * LINE_STAGGER_MS + 120}
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
    </>
  )
}
