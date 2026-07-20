// Profile overlay — mounts over the world without unmounting it. Per-mode
// content layout locked in wiki/Noctis OS/Interface.md's "Profile overlay
// card system" section.
import { useEffect, useState } from 'react'
import {
  acceptInboxItem,
  getInbox,
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
    await launchSession(mode)
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
          <h2>{meta.name.toUpperCase()}</h2>
          <button type="button" className="close" aria-label="Close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="body">{state && renderBody(mode, state, inbox, handleDecision)}</div>

        {mode !== 'nightshift' && (
          <div className="launch-row">
            <button type="button" className="launch-btn" onClick={handleLaunch}>
              LAUNCH SESSION
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
) {
  switch (mode) {
    case 'dev':
      return <FaberBody state={state} />
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

function FaberBody({ state }: { state: ModeState }) {
  const jobs = state.jobs ?? []
  if (jobs.length === 0) {
    return <p className="idle-note">no dams under construction. the pond is calm.</p>
  }
  return (
    <>
      {jobs.map((job) => (
        <div className="job-row" key={job.slug}>
          <div>
            <span className="name">{job.name}</span>
            <span className="job-status">{job.status}</span>
          </div>
          <span className="phase-badge">{job.stage}</span>
        </div>
      ))}
    </>
  )
}

function NoctuaBody({ state }: { state: ModeState }) {
  const deepDue = typeof state.deep_due === 'number' ? state.deep_due : 0
  const deepRetained = typeof state.deep_retained === 'number' ? state.deep_retained : 0
  const shallowDone = typeof state.shallow_done === 'number' ? state.shallow_done : 0
  return (
    <div className="stat-blocks">
      <div className="stat-block">
        <span className="stat-label">DEEP</span>
        <span className="stat-main">{deepDue} due</span>
        <span className="stat-sub">{deepRetained} retained</span>
      </div>
      <div className="stat-block">
        <span className="stat-label">SHALLOW</span>
        <span className="stat-main">{shallowDone} done</span>
      </div>
    </div>
  )
}

function VesperBody({ state }: { state: ModeState }) {
  const adopt = (state.adopt_counts as Record<string, number> | undefined) ?? {}
  const inquiry = (state.inquiry_counts as Record<string, number> | undefined) ?? {}
  return (
    <div className="stat-blocks">
      <div className="stat-block">
        <span className="stat-label">ADOPT</span>
        <div className="verdict-badges">
          <span className="verdict good">adopt {adopt.adopt ?? 0}</span>
          <span className="verdict bad">reject {adopt.reject ?? 0}</span>
          <span className="verdict neutral">park {adopt.park ?? 0}</span>
        </div>
      </div>
      <div className="stat-block">
        <span className="stat-label">INQUIRY</span>
        <div className="verdict-badges">
          <span className="verdict good">sound {inquiry.sound ?? 0}</span>
          <span className="verdict good">promising {inquiry.promising ?? 0}</span>
          <span className="verdict bad">weak {inquiry.weak ?? 0}</span>
          <span className="verdict bad">hype {inquiry.hype ?? 0}</span>
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
    return <p className="idle-note">nothing to tend. the sett holds.</p>
  }
  return (
    <>
      <div className="trigger-list">
        {(['friction', 'accumulation', 'suspicion'] as const).map((trigger) => (
          <span key={trigger} className={`trigger-badge${triggers[trigger] ? ' lit' : ''}`}>
            {trigger}
          </span>
        ))}
      </div>
      <div className="stat-block">
        <span className="stat-label">DIFFS AWAITING REVIEW</span>
        <span className="stat-main">{diffsAwaiting}</span>
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
    return <p className="idle-note">inbox empty.</p>
  }
  return (
    <>
      {inbox.map((item) => (
        <div className="inbox-row" key={item.slug}>
          <span
            className="origin-tag"
            style={{ ['--accent' as string]: `var(${MODE_META[item.origin_mode].accentVar})` }}
          >
            {MODE_META[item.origin_mode].name}
          </span>
          <span className="inbox-desc">
            {item.description}
            <span className="inbox-rationale">{item.rationale}</span>
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
