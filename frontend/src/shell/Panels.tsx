/* Inbox, Repo and Settings.
 *
 * All read real routes, computed when opened. Nothing here is a file written
 * ahead of time: the morning brief that used to head the rail was one, its
 * scheduler never existed, and it told you about a Thursday for five days.
 * The Inbox now opens with a digest of what happened since you were last
 * here -- counts composed into sentences, no model in the loop -- and then
 * what is waiting on you.
 */
import { useEffect, useState } from 'react'
import { Unreachable } from './Async'
import { Pools, type PoolTone } from './Pools'
import { get, post, put } from './engine'
import { useFetched } from './useFetched'
import { Markdown } from './Markdown'
import { MODE_ACCENT, MODE_LABEL, VAULT_MODE, type Mode } from './domain'
import { ModeMark, Pill, usePill, type PillRect } from './Chrome'
import { gridColumns } from './Terminals'
import { openExternal } from './host'

/** Nightshift's newest run and how many nights in a row ended the same
 *  way; null until it has recorded one. `kind` is what happened: staged
 *  something, quiet, partial failure, or broken (every item failed with one
 *  error, which `error` names). */
export interface NightshiftSummary {
  ran_at: string; staged: number; failed: number; seen: number; error: string | null
  kind: 'staged' | 'quiet' | 'partial' | 'broken'; streak: number
}

export interface InboxPayload {
  items: {
    id: string
    kind: 'proposal' | 'flagged-job' | 'unreadable'
    mode: string
    title: string
    detail: string
    at: string
    confidence?: string | null
    /** Whether accepting would change a file. Many proposals only surface
     *  a status and change nothing, and that is the first thing you need to
     *  know before deciding. */
    changes_files?: boolean
    /** The file the diff edits, if any. */
    target?: string | null
    /** What accepting does to Noctis, in one sentence -- derived from the
     *  diff by the backend, not claimed by the proposal. */
    effect?: string
    /** The whole argument, for the read that a decision deserves. */
    full?: { rationale: string; diff: string; evidence: string; confidence: string }
  }[]
  counts: { proposals: number; flagged: number }
}

export interface RepoInfo {
  root: string
  name: string
  branch: string | null
  upstream: string | null
  ahead: number | null
  behind: number | null
  dirty: string[]
  /** `mode` is the session whose transcript made the commit -- evidence --
   *  falling back to ownership, then to who was live at the time; null for
   *  a commit made by hand. `body` is the record: where the work left
   *  things. `via`, on a Record commit, says whether it is here because it
   *  touches the notes or because its author was inside the project. */
  commits: {
    sha: string; full: string; subject: string; body: string; at: number; pushed: boolean
    mode?: string | null; by?: { session: number; cwd: string | null } | null; via?: 'path' | 'session'
  }[]
  remote: string | null
  /** `owner/name` when the remote is on GitHub; the GitHub half is read
   *  separately by slug, so the local half never waits on the network. */
  slug: string | null
  /** Why there is no slug, when there is none. */
  github_reason: string | null
  /** The open terminals' directories that resolve to this repository. */
  cwds: string[]
  /** For a dev job's project: the vault side -- the job's notes folder and
   *  job folder, read as their own repository state, its commits listed
   *  like the project's. `trails` is how far the newest record commit sits
   *  behind the newest project commit, in seconds. */
  notes?: (RepoInfo & { paths: string[]; trails: RecordTrails | null; vault_ahead: number | null }) | null
  /** On a record: the whole vault's unpushed count, since a push is the
   *  repository's; `ahead` is the record's own. */
  vault_ahead?: number | null
}

export interface RecordTrails { project_at: number; record_at: number; behind: number }

export interface GithubInfo {
  slug: string
  url: string | null
  private: boolean
  default_branch: string | null
  pull_requests: { number: number; title: string; branch: string | null; draft: boolean; mergeable: string | null; url: string | null; checks: 'pass' | 'fail' | 'pending' | null }[]
  issues: { number: number; title: string; url: string | null; labels: string[] }[]
}

export interface GithubPayload {
  github: GithubInfo | null
  reason: string | null
}

export interface RepoPayload {
  repos: RepoInfo[]
  /** Terminal directories that are not inside any repository. */
  outside: string[]
}

/** An open terminal as the Repo view names it: the tab strip's positional
 *  label, and the directory it is in right now. */
export interface RepoTerminal {
  id: string
  mode: Mode
  cwd: string
  /** 1-based position in the strip, the number under ⌘. */
  index: number
  showing: boolean
}

export interface BillingPayload {
  list_cost: number
  turns: number
  /** How many of those turns the figure actually covers. */
  priced_turns: number
  since: string | null
  charged: boolean
  basis: string
}

export function Heading({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <h2 className={`m-0 mb-[14px] font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint ${className}`}>
      {children}
    </h2>
  )
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-card border border-line bg-surface">{children}</div>
}

/** The border beam, as libraries.dev/beam has it at "Pulse · Pulse Outside ·
 *  Mono": soft light pooling at points round the edge and blooming outward,
 *  breathing rather than travelling. `Pools` is that mechanism ported, with
 *  the pools laid out evenly so a card five times wider than the library's
 *  demo has no dark stretch of edge. On the Stats cards only, in silver;
 *  the Repo modules wore it for an afternoon and it looked wrong there.
 *  `radius` must match the card's own. */
export function Beam({ tone = 'silver', radius = 8, children }: { tone?: PoolTone; radius?: number; children: React.ReactNode }) {
  return <Pools tone={tone} radius={radius} strength={0.5}>{children}</Pools>
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/** "since yesterday 23:40" / "since 09:12" / "since Thu 10 Sep 23:40" --
 *  or, with no sitting recorded yet, what the window actually was. */
export function sinceLabel(iso: string | null, now = new Date()): string {
  if (!iso) return 'the last day'
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return 'the last day'
  // Spelled out by hand rather than through the locale, so the label reads
  // the same on every machine and the test can hold it to one string.
  const two = (n: number) => String(n).padStart(2, '0')
  const hm = `${two(t.getHours())}:${two(t.getMinutes())}`
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const gap = Math.round((day(now) - day(t)) / 86_400_000)
  if (gap === 0) return `since ${hm}`
  if (gap === 1) return `since yesterday ${hm}`
  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `since ${DAYS[t.getDay()]} ${t.getDate()} ${MONTHS[t.getMonth()]} ${hm}`
}

/** Nightshift's newest run as one sentence, whatever it did. A run of the
 *  same outcome is counted: "broken, 3 nights running" is the line that six
 *  weeks of "quiet night" in a log never produced. Tested to the string. */
/* When it ran, and nothing else unless something went wrong.
 *
 * It used to report the outcome too ("1 proposal staged", "nothing to
 * stage"), which the list directly underneath already shows: the proposals
 * are right there to be counted, so the sentence was reading them out
 * (2026-09-17). A failure is the exception and stays, in full, because a
 * nightly job that fails quietly is the bug this record exists to prevent:
 * it failed every night for forty-one nights while a log said "quiet".
 */
export function nightshiftLine(n: NightshiftSummary | null): string {
  if (!n) return 'Nightshift has not recorded a run.'
  const at = new Date(n.ran_at)
  const hm = Number.isNaN(at.getTime()) ? '' : ` at ${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`
  const run = n.streak > 1 ? ` (${n.streak} nights running)` : ''
  if (n.kind === 'broken') return `Nightshift failed${hm}: ${n.error}${run}`
  if (n.kind === 'partial') return `Nightshift ran${hm}, ${n.failed} of ${n.seen} failed`
  return `Nightshift ran${hm}`
}

/* A unified diff the conventional way: removed lines red, added lines
 * green, each on its own tinted ground; file headers and hunk marks faint.
 * Strikethrough on the old lines made a long removed paragraph unreadable,
 * and reading the old text is half of judging the change. */
export function Diff({ text }: { text: string }) {
  const kind = (l: string): 'add' | 'del' | 'meta' | 'ctx' =>
    l.startsWith('+++') || l.startsWith('---') || l.startsWith('@@') ? 'meta'
    : l.startsWith('+') ? 'add'
    : l.startsWith('-') ? 'del'
    : 'ctx'
  const style: Record<ReturnType<typeof kind>, React.CSSProperties> = {
    add: { color: 'var(--color-good)', background: 'color-mix(in srgb, var(--color-good) 9%, transparent)' },
    del: { color: 'var(--color-faber)', background: 'color-mix(in srgb, var(--color-faber) 9%, transparent)' },
    meta: { color: 'var(--color-ink-faint)' },
    ctx: { color: 'var(--color-ink-dim)' },
  }
  return (
    <pre className="m-0 overflow-x-auto rounded-card border border-line bg-ground font-mono text-[11.5px] leading-[1.6]">
      {text.split('\n').map((l, k) => {
        const t = kind(l)
        return (
          <div key={k} className="flex whitespace-pre-wrap px-[10px]" style={style[t]}>
            <span className="w-[14px] shrink-0 select-none">{t === 'add' ? '+' : t === 'del' ? '−' : ' '}</span>
            <span className="min-w-0 flex-1">{t === 'add' || t === 'del' ? l.slice(1) : l}</span>
          </div>
        )
      })}
    </pre>
  )
}

const KIND_LABEL: Record<string, string> = {
  proposal: 'proposal',
  'flagged-job': 'flagged',
  unreadable: 'unreadable',
}

export function Inbox({ data, onDecided }: { data: InboxPayload; onDecided?: () => void }) {
  // Decided items disappear at once rather than at the next load: a row
  // that lingers after you dispatch it reads as a decision that failed.
  const [decided, setDecided] = useState<Set<string>>(new Set())
  // A decision that failed says why, under the row it failed on. The first
  // version swallowed the error and left the row as it was, which is
  // indistinguishable from a button that does nothing.
  const [failed, setFailed] = useState<Record<string, string>>({})
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState<string | null>(null)
  const items = data.items.filter((i) => !decided.has(i.id))

  if (items.length === 0) {
    return (
      <>
        <Card>
          <div className="px-4 py-[13px] text-[12.5px] text-ink-dim">
            No proposals waiting. What nightshift stages, and jobs it flags, appear here.
          </div>
        </Card>
      </>
    )
  }

  const decide = async (id: string, decision: 'accept' | 'reject') => {
    setBusy(id)
    const out = await post<{ decision: string; applied_to: string | null }>(`/v2/inbox/${id}/${decision}`, {})
    setBusy(null)
    if ('error' in out) {
      setFailed((f) => ({ ...f, [id]: out.error }))
      return
    }
    setDecided((d) => new Set(d).add(id))
    onDecided?.()
  }

  /* A flag is a statement that a session died mid-build. Saying "I know"
   * is the only thing that was missing: until 2026-09-17 a flag could not
   * be cleared from here, so a job parked on purpose asked the same
   * question every night. The id is `<mode>/<slug>`, the route's shape. */
  const acknowledge = async (id: string) => {
    setBusy(id)
    const out = await post<{ acknowledged: string }>(`/v2/flagged/${id}/acknowledge`, {})
    setBusy(null)
    if ('error' in out) {
      setFailed((f) => ({ ...f, [id]: out.error }))
      return
    }
    setDecided((d) => new Set(d).add(id))
    onDecided?.()
  }
  const toggle = (id: string) =>
    setOpen((o) => { const n = new Set(o); if (n.has(id)) n.delete(id); else n.add(id); return n })

  return (
    <>
      <div className="mb-[8px] font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-faint">
        {data.counts.proposals} proposal{data.counts.proposals === 1 ? '' : 's'} · {data.counts.flagged} flagged
      </div>
      {/* One card per item rather than rows in one card: an item is a
          decision with its own argument under it, and a stack of those reads
          as a queue of packages, which is what it is. */}
      <div className="flex flex-col gap-[10px]">
        {items.map((item) => {
          const mode: Mode = VAULT_MODE[item.mode] ?? 'general'
          const accent = MODE_ACCENT[mode]
          const isOpen = open.has(item.id)
          return (
            <Card key={item.id}>
              {/* The sender's face, the title, what kind of thing it is. */}
              <div className="flex items-center gap-[10px] px-4 pt-[13px]">
                <span className="grid h-[22px] w-[22px] shrink-0 place-items-center rounded-control bg-elevated">
                  <ModeMark mode={mode} size={16} />
                </span>
                <span className="min-w-0 flex-1 text-[13.5px] font-medium leading-[1.4] text-ink">{item.title}</span>
                {/* An unreadable job is its own state, not a flagged one:
                    the file could not be parsed, so nothing about it is
                    known -- including whether it needs attention. */}
                <span
                  className="shrink-0 rounded-control border px-[6px] py-px font-mono text-[10px]"
                  style={
                    item.kind === 'unreadable'
                      ? { borderColor: 'var(--color-faber)', color: 'var(--color-faber)' }
                      : { borderColor: accent, color: accent }
                  }
                >
                  {KIND_LABEL[item.kind] ?? item.kind}
                </span>
              </div>

              {/* Two paragraphs, in the order a decision needs them: what it
                  is, then what saying yes does. The consequence comes from
                  the diff itself, so it cannot be oversold. */}
              <div className="px-4 pl-[48px] pt-[8px] text-[12.5px] leading-[1.6] text-ink-dim">{item.detail}</div>
              {item.effect && (
                <div className="px-4 pl-[48px] pt-[6px] text-[12.5px] leading-[1.6] text-ink">
                  <span style={{ color: accent }}>→ </span>{item.effect}
                </div>
              )}

              {/* Provenance on the left, the decision on the right, on their
                  own band so neither crowds the other. */}
              <div className="mt-[10px] flex items-center gap-[10px] border-t border-line px-4 py-[8px] font-mono text-[10.5px] text-ink-faint">
                <span className="flex min-w-0 items-center gap-[8px]">
                  <span style={{ color: accent }}>{MODE_LABEL[mode]}</span>
                  {item.at && <span>{item.at.slice(0, 10)}</span>}
                  {item.confidence && <span>{item.confidence} confidence</span>}
                  {item.target && <span className="truncate text-ink-dim">{item.target}</span>}
                </span>
                {item.kind === 'flagged-job' && (
                  <span className="ml-auto flex shrink-0 items-center gap-[5px]">
                    <button
                      type="button"
                      disabled={busy === item.id}
                      onClick={() => void acknowledge(item.id)}
                      title="Clear the flag. Only work after this can raise it again."
                      className="rounded-control border border-line px-[9px] py-[3px] text-ink-faint transition-colors hover:bg-elevated hover:text-ink disabled:opacity-40"
                    >
                      acknowledge
                    </button>
                  </span>
                )}
                {item.kind === 'proposal' && (
                  <span className="ml-auto flex shrink-0 items-center gap-[5px]">
                    {item.full && (
                      <button type="button" onClick={() => toggle(item.id)}
                              className="rounded-control border border-line px-[8px] py-[3px] text-ink-faint transition-colors hover:bg-elevated hover:text-ink">
                        {isOpen ? 'close' : 'read'}
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busy === item.id}
                      onClick={() => void decide(item.id, 'reject')}
                      className="rounded-control border border-line px-[8px] py-[3px] text-ink-faint transition-colors hover:bg-elevated hover:text-ink disabled:opacity-40"
                    >
                      reject
                    </button>
                    <button
                      type="button"
                      disabled={busy === item.id}
                      onClick={() => void decide(item.id, 'accept')}
                      className="rounded-control border px-[9px] py-[3px] text-ink transition-colors hover:bg-elevated disabled:opacity-40"
                      style={{ borderColor: accent }}
                    >
                      {item.changes_files ? 'accept · apply' : 'accept'}
                    </button>
                  </span>
                )}
              </div>

              {failed[item.id] && (
                <div className="border-t border-line px-4 py-[8px] font-mono text-[11px]" style={{ color: 'var(--color-faber)' }}>
                  {failed[item.id]}
                </div>
              )}

              {isOpen && item.full && (
                <div className="flex flex-col gap-[14px] border-t border-line px-4 py-[14px] text-[12.5px] leading-[1.65] text-ink-dim">
                  <Section label="rationale"><Markdown src={item.full.rationale} /></Section>
                  {item.full.diff && (
                    <Section label="diff"><Diff text={item.full.diff} /></Section>
                  )}
                  {item.full.evidence && <Section label="evidence"><Markdown src={item.full.evidence} /></Section>}
                  {item.full.confidence && <Section label="confidence"><Markdown src={item.full.confidence} /></Section>}
                </div>
              )}
            </Card>
          )
        })}
      </div>
    </>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-[3px] font-mono text-[10px] uppercase tracking-[0.08em] text-ink-faint">{label}</div>
      {children}
    </div>
  )
}

/* The repositories the open terminals are in, one group per repository.
 *
 * The view follows the arrangement, not the one terminal that is showing:
 * two Faber sessions on one project are one repository with two terminals
 * named under it, and a Vesper session on another project is a second group
 * below. The showing terminal's repository comes first, so what you were
 * just looking at is what you land on. A terminal in no repository is
 * listed at the end, in words.
 *
 * Read-only on purpose. The local half is what you are looking at -- the
 * branch, what is not on GitHub yet, what is dirty, the last twenty commits
 * with the unpushed ones marked. The GitHub half is what you are being told
 * about -- open pull requests with their checks, open issues -- and it can
 * be absent (offline, signed out, a remote elsewhere) without taking the
 * local half with it. The one action this view wants, push, it asks for in
 * words: a session never pushes, and that rule is what keeps a crashed
 * session from half-shipping; a button here would be that power through
 * another door. */
export function Repo({ data, terminals, onChanged }: { data: RepoPayload; terminals: RepoTerminal[]; onChanged?: () => void }) {
  const showingCwd = terminals.find((t) => t.showing)?.cwd
  const groups = [...data.repos].sort((a, b) =>
    Number(b.cwds.includes(showingCwd ?? '')) - Number(a.cwds.includes(showingCwd ?? '')))
  /* One module per repository, laid out like the terminals: a row up to
   * three, a grid after. With more than one on screen the commit lists
   * start folded, so the page reads as repositories first. A terminal in
   * a directory outside any repository (`data.outside`) gets no module:
   * every mode starts in a repository now, and a section saying "not in
   * a repository" told the reader nothing they could act on here. */
  const many = groups.length > 1
  return (
    <div className="grid items-stretch gap-6"
         style={{ gridTemplateColumns: `repeat(${gridColumns(groups.length)}, minmax(0, 1fr))` }}>
      {groups.map((r) => (
        <RepoModule key={r.root} r={r} folded={many} onChanged={onChanged}
                    terminals={terminals.filter((t) => r.cwds.includes(t.cwd))} />
      ))}
    </div>
  )
}

/** A terminal the way the tab strip names it: the mode's colour and its
 *  position, which is the number under ⌘. */
function TerminalChip({ t }: { t: RepoTerminal }) {
  return (
    <span className={`flex shrink-0 items-center gap-[6px] font-mono text-[11px] ${t.showing ? 'text-ink' : 'text-ink-dim'}`}>
      <ModeMark mode={t.mode} dim={!t.showing} />
      {MODE_LABEL[t.mode].toLowerCase()} · {t.index}
    </span>
  )
}

/** A link that leaves the app. */
function Ext({ href, className, children }: { href: string; className?: string; children: React.ReactNode }) {
  return (
    <a href={href} className={className} onClick={(e) => { e.preventDefault(); openExternal(href) }}>
      {children}
    </a>
  )
}

/* The push, as a button. A session never pushes -- permissions deny it to a
 * hosted one and the prompt sends every other one here -- so this is the
 * person's hand, running `git push` as the machine's git identity through
 * the same credential helper a terminal would use. Force is a second,
 * separate click, offered only when origin has commits this branch does
 * not (a rewritten history); a plain push is never turned into a force. The
 * backend also refuses any push whose commits carry an attribution line. */
function PushButton({ r, onPushed }: { r: RepoInfo; onPushed?: () => void }) {
  const [state, setState] = useState<'idle' | 'confirm-force' | 'pushing' | 'done' | 'failed'>('idle')
  const [note, setNote] = useState<string | null>(null)
  const ahead = r.ahead ?? 0, behind = r.behind ?? 0
  const diverged = ahead > 0 && behind > 0
  const nothing = !r.upstream ? false : ahead === 0
  if (nothing && state === 'idle') return null

  const run = async (force: boolean) => {
    setState('pushing'); setNote(null)
    const out = await post<{ pushed: boolean; as: string; force: boolean }>('/v2/repos/push', { cwd: r.cwds[0] ?? r.root, force })
    if ('error' in out) { setState('failed'); setNote(out.error); return }
    setState('done'); setNote(`pushed${out.force ? ' (force)' : ''} as ${out.as || 'you'}`)
    onPushed?.()
  }
  return (
    <span className="flex items-center gap-[8px] font-mono text-[11px]">
      {note && <span className={`max-w-[360px] truncate ${state === 'failed' ? '' : 'text-ink-dim'}`}
                     style={state === 'failed' ? { color: 'var(--color-faber)' } : undefined} title={note}>{note}</span>}
      {state === 'confirm-force' ? (
        <>
          <span className="text-ink-dim">history rewritten — replace origin's {behind}?</span>
          <button type="button" onClick={() => void run(true)}
                  className="rounded-control border px-[8px] py-[2px] text-ink hover:bg-elevated" style={{ borderColor: 'var(--color-faber)' }}>
            force push
          </button>
          <button type="button" onClick={() => setState('idle')} className="rounded-control border border-line px-[8px] py-[2px] text-ink-faint hover:text-ink">cancel</button>
        </>
      ) : state === 'done' ? null : (
        <button type="button" disabled={state === 'pushing'}
                title={r.vault_ahead != null && r.vault_ahead !== ahead ? `a push is the whole repository's: ${r.vault_ahead} commits leave, ${ahead} of them this record's` : undefined}
                onClick={() => (diverged ? setState('confirm-force') : void run(false))}
                className="rounded-control px-[9px] py-[2px] text-ink transition-opacity hover:opacity-90 disabled:opacity-40"
                style={{ background: 'var(--color-sig)', outline: diverged ? '1px solid var(--color-faber)' : undefined }}>
          {state === 'pushing' ? 'pushing…' : !r.upstream ? `publish ${r.branch ?? 'branch'}` : diverged ? 'push · force' : `push ${ahead}`}
        </button>
      )}
    </span>
  )
}

/* A section inside a module: a fold with a title and a count, the body
 * under it. Folded, it says how many; open, it shows them. */
function Fold({ title, meta, open, onToggle, right, empty = false, grow = false, children }: {
  title: string; meta?: React.ReactNode; open: boolean; onToggle: () => void; right?: React.ReactNode
  /** Take the card's spare height, with the header centred in it while closed
   *  (2026-09-16): modules in a row share a height, and the last fold is
   *  where a shorter card's space goes. */
  grow?: boolean
  /** Nothing to open: the row stays, so modules keep the same rows, but it does not fold. */
  empty?: boolean; children?: React.ReactNode
}) {
  /* `right` sits beside the toggle, not inside it: it holds the push
   * button now (2026-09-16), and a button inside a button is invalid and
   * would toggle the fold on every push. */
  return (
    <div className={`border-t border-line ${grow ? 'flex flex-1 flex-col justify-center' : ''}`}>
      <div className="flex items-center">
        <button type="button" onClick={empty ? undefined : onToggle} disabled={empty}
                className="flex min-w-0 flex-1 items-center gap-[8px] px-4 py-[9px] text-left font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink-faint enabled:hover:text-ink disabled:cursor-default">
          <span className="inline-block w-[10px] text-center">{empty ? '·' : open ? '▾' : '▸'}</span>
          <span>{title}</span>
          {meta && <span className="font-normal normal-case tracking-normal text-ink-faint">· {meta}</span>}
        </button>
        {right && <span className="flex shrink-0 flex-col items-center justify-center py-[6px] pr-4 font-mono text-[11px]">{right}</span>}
      </div>
      {open && !empty && children}
    </div>
  )
}

/* Ten commits fit; the other ten scroll. A subject wraps rather than
 * truncates: a line you cannot finish reading is a line you did not read.
 *
 * The body is the record (2026-09-15): a click on a commit opens its body,
 * another closes it, and nothing opens on its own -- the newest opened by
 * default for an evening and pushed Record and GitHub off the bottom of
 * the module. A commit with no body says so, quietly. */
function CommitList({ commits, paths }: { commits: RepoInfo['commits']; paths?: string[] }) {
  const [open, setOpen] = useState<Set<string>>(() => new Set())
  if (commits.length === 0) {
    return <div className="border-t border-line px-4 py-[9px] text-[12px] text-ink-faint">
      {paths ? `no commits touch ${paths.join(' or ')} yet` : 'no commits yet'}
    </div>
  }
  const toggle = (id: string) => setOpen((o) => { const n = new Set(o); if (n.has(id)) n.delete(id); else n.add(id); return n })
  return (
    <div className="max-h-[420px] overflow-y-auto">
      {commits.map((c) => {
        const shown = open.has(c.full)
        return (
          <div key={c.full} className="border-t border-line">
            <button type="button" onClick={() => toggle(c.full)}
                    className="flex w-full items-baseline gap-[10px] px-4 py-[7px] text-left font-mono text-[11.5px] hover:bg-elevated/40">
              <span className="w-[8px] shrink-0 text-center" title={c.pushed ? 'on GitHub' : 'not on GitHub yet'}
                    style={{ color: c.pushed ? 'var(--color-good)' : 'var(--color-faber)' }}>●</span>
              <span className="grid w-[14px] shrink-0 place-items-center self-center">
                {c.mode && c.mode in MODE_LABEL && <ModeMark mode={c.mode as Mode} size={12} />}
              </span>
              <span className="shrink-0 text-ink-faint">{c.sha}</span>
              <span className="min-w-0 flex-1 whitespace-normal break-words leading-[1.45] text-ink">{c.subject}</span>
              {c.via === 'session' && <span className="shrink-0 text-[10px] text-ink-faint" title="here because its author session was inside this project">from here</span>}
              <span className="shrink-0 text-ink-faint">{ago(c.at)}</span>
            </button>
            {shown && (
              <div className="px-4 pb-[10px] pl-[52px] font-mono text-[11.5px] leading-[1.6] text-ink-dim">
                {c.body
                  ? reflow(c.body).map((p, i) => <p key={i} className={`m-0 whitespace-pre-wrap break-words${i ? ' mt-[9px]' : ''}`}>{p}</p>)
                  : <span className="text-ink-faint">no body — a subject alone; the record starts with the next commit</span>}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

/** A commit body arrives hard-wrapped at seventy-two columns, git's own
 * convention, and the module wraps it again at its width -- so a word sat
 * alone on a line wherever the two disagreed. Blank lines are paragraph
 * breaks and stay; the breaks inside a paragraph are the author's editor,
 * not their meaning, and are joined. A paragraph that is a list (every
 * line a bullet, a number, or indented) keeps its lines. */
export function reflow(body: string): string[] {
  const structured = (l: string) => /^(\s+|[-*•] |\d+[.)] )/.test(l)
  return body.replace(/\r\n/g, '\n').trim().split(/\n[ \t]*\n+/).map((para) => {
    const lines = para.split('\n')
    return lines.every(structured) ? lines.map((l) => l.trimEnd()).join('\n') : lines.map((l) => l.trim()).join(' ')
  }).filter(Boolean)
}

const Legend = () => (
  <span className="flex items-center gap-[8px] text-[10.5px] text-ink-faint">
    <span><span style={{ color: 'var(--color-faber)' }}>●</span> local</span>
    <span><span style={{ color: 'var(--color-good)' }}>●</span> on GitHub</span>
  </span>
)

/* One repository as one module: its name and branch on the lid, the
 * terminals in it, where it stands, then its sections -- uncommitted,
 * commits, the record (for a dev job's project), GitHub -- each a fold
 * inside the same border, so the grouping is the box and not the reader's
 * inference. */
/* The lid: name, branch (the branch the repository is on -- a job branch
 * would show here) and the terminals in it on one line, the GitHub link
 * under the title (2026-09-16). No path: that opens the block under it. */
function Lid({ name, branch, slug, chips }: { name: string; branch: string | null; slug: string | null; chips?: React.ReactNode }) {
  return (
    <div className="px-4 py-[10px]">
      <div className="flex flex-wrap items-center gap-x-[10px] gap-y-[4px]">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-ink">{name}</span>
        <span className="font-mono text-[11px] text-ink-faint">· {branch ?? 'detached'}</span>
        {chips}
      </div>
      {slug && <Ext href={`https://github.com/${slug}`} className="mt-[4px] inline-block font-mono text-[11px] text-ink-dim hover:text-ink">{slug} ↗</Ext>}
    </div>
  )
}

/* Where a block stands: the full path of what it is about, and under it
 * the figures -- not on GitHub, behind, uncommitted. One cell, two
 * lines (2026-09-16); the uncommitted files are the cell below. */
function Stand({ path, r }: { path: string; r: RepoInfo }) {
  const unpushed = r.ahead ?? 0
  return (
    <div className="border-t border-line px-4 py-[8px] font-mono">
      <div className="truncate text-[11px] font-bold text-ink" title={path}>{path}</div>
      <div className="mt-[6px] flex flex-wrap items-center gap-x-[14px] gap-y-[4px] text-[11.5px]">
        {r.upstream ? (
          <>
            <span className={unpushed ? 'text-ink' : 'text-ink-faint'}>↑ {unpushed} not on GitHub</span>
            <span className={r.behind ? 'text-ink' : 'text-ink-faint'}>↓ {r.behind ?? 0} behind</span>
          </>
        ) : (
          <span className="text-ink-faint">no upstream</span>
        )}
        <Uncommitted n={r.dirty.length} />
      </div>
    </div>
  )
}

function RepoModule({ r, terminals, folded, onChanged }: { r: RepoInfo; terminals: RepoTerminal[]; folded: boolean; onChanged?: () => void }) {
  // One Commits fold open at a time: opening the record's closes the
  // code's and back (2026-09-16), so the card never holds two long lists.
  const [open, setOpen] = useState<'code' | 'record' | null>(folded ? null : 'code')
  const commitsOpen = open === 'code', recordOpen = open === 'record'
  const toggle = (which: 'code' | 'record') => setOpen((o) => (o === which ? null : which))
  const [githubOpen, setGithubOpen] = useState(false)
  const local = r.commits.filter((c) => !c.pushed).length
  const rec = r.notes
  /* A repository as one thing (2026-09-16): a lid naming it, who is in it
   * and where it is; its figures; its uncommitted files; the fold of what
   * it holds, with the push on the fold's lid. The project and its record
   * are two of these stacked in one module -- the same anatomy twice, so
   * the record reads the way the code does. The record's lid names the
   * vault, its branch and the notes path; its fold is the files. No pools
   * here: tried on the modules 2026-09-15, wrong against the folds. */
  return (
    <section className="flex flex-col rounded-card border border-line bg-surface">
      <Lid name={r.name} branch={r.branch} slug={r.slug} chips={terminals.map((t) => <TerminalChip key={t.id} t={t} />)} />

      <Stand path={r.root} r={r} />
      <Dirty files={r.dirty} />
      <Fold title="Commits" meta={local ? `${local} of ${r.commits.length} not on GitHub` : `${r.commits.length}, all on GitHub`}
            open={commitsOpen} onToggle={() => toggle('code')} grow={!rec}
            right={<><PushButton r={r} onPushed={onChanged} /><span className={commitsOpen ? 'mt-[6px]' : 'invisible h-0 overflow-hidden'}><Legend /></span></>}>
        <CommitList commits={r.commits} />
      </Fold>

      {rec && (
        <>
          {/* The record: the same block, for the notes path. Its figures are
              the record's own -- the vault's whole count beside a fold of
              three read as a contradiction -- and its fold is Commits too,
              with the same meta as the project's: the record's commits,
              shown by the file each last touched. */}
          <Stand path={`${rec.root}/${rec.paths[0]}`} r={rec} />
          <Dirty files={rec.dirty} />
          <Fold title="Commits" meta={rec.ahead ? `${rec.ahead} of ${rec.commits.length} not on GitHub` : `${rec.commits.length}, all on GitHub`}
                open={recordOpen} onToggle={() => toggle('record')} grow
                right={<><PushButton r={rec} onPushed={onChanged} /><span className={recordOpen ? 'mt-[6px]' : 'invisible h-0 overflow-hidden'}><Legend /></span></>}>
            {/* Commits, like the project's (2026-09-16): a list of files
                with the commit that last touched each put twelve unpushed
                commits beside three red rows, because twelve commits had
                touched one file. Rows and figures now count the same thing;
                a session's commit wears "from here". */}
            <CommitList commits={rec.commits} paths={rec.paths} />
          </Fold>
        </>
      )}

      <div>
      <Fold title="GitHub" meta={r.slug ? r.slug : `not available: ${r.github_reason ?? 'unknown'}`}
            open={githubOpen} onToggle={() => setGithubOpen((o) => !o)}>
        {r.slug ? <GithubLive slug={r.slug} /> : <GithubCard gh={null} reason={r.github_reason} />}
      </Fold>
      </div>
    </section>
  )
}

/** The GitHub half, read by slug once the local half is on screen. */
function GithubLive({ slug }: { slug: string }) {
  const data = useFetched<GithubPayload>(`/v2/repos/github?slug=${encodeURIComponent(slug)}`)
  if (data === null) return <GithubCard gh={null} reason={null} pending />
  if (data === false) return <GithubCard gh={null} reason="the backend did not answer" />
  return <GithubCard gh={data.github} reason={data.reason} />
}

export function GithubCard({ gh, reason, pending = false }: { gh: GithubInfo | null; reason: string | null; pending?: boolean }) {
  if (!gh) {
    return (
      <div className="border-t border-line px-4 py-[10px] text-[12.5px] text-ink-dim">
        {pending ? 'Asking GitHub…' : `Not available: ${reason ?? 'unknown'}.`}
      </div>
    )
  }
  return (
      <div>
          <>
            <div className="flex items-center border-t border-line px-4 py-[9px] font-mono text-[11px] text-ink-faint">
              <span>pull requests · {gh.pull_requests.length} open</span>
              <Ext href={gh.url ?? `https://github.com/${gh.slug}`} className="ml-auto text-ink-dim hover:text-ink">
                {gh.slug} · {gh.private ? 'private' : 'public'} ↗
              </Ext>
            </div>
            {gh.pull_requests.map((p) => (
              <div key={p.number} className="flex items-center gap-[10px] border-t border-line px-4 py-[8px] text-[12px]">
                <span className="shrink-0 font-mono text-ink-faint">#{p.number}</span>
                <Ext href={p.url ?? '#'} className="min-w-0 flex-1 truncate text-ink hover:underline">{p.title}</Ext>
                <span className="shrink-0 font-mono text-[10.5px] text-ink-faint">{p.branch}</span>
                {p.draft && <Tag>draft</Tag>}
                {p.checks && <Tag tone={p.checks === 'fail' ? 'bad' : p.checks === 'pass' ? 'good' : undefined}>checks {p.checks}</Tag>}
                {p.mergeable === 'CONFLICTING' && <Tag tone="bad">conflicts</Tag>}
              </div>
            ))}
            {gh.pull_requests.length === 0 && (
              <div className="border-t border-line px-4 py-[8px] text-[12px] text-ink-faint">none — a branch pushed with a PR is how work gets reviewed before it reaches {gh.default_branch ?? 'main'}</div>
            )}
            <div className="border-t border-line px-4 py-[9px] font-mono text-[11px] text-ink-faint">
              issues · {gh.issues.length} open
            </div>
            {gh.issues.map((it) => (
              <div key={it.number} className="flex items-center gap-[10px] border-t border-line px-4 py-[8px] text-[12px]">
                <span className="shrink-0 font-mono text-ink-faint">#{it.number}</span>
                <Ext href={it.url ?? '#'} className="min-w-0 flex-1 truncate text-ink hover:underline">{it.title}</Ext>
                {it.labels.map((l) => <Tag key={l}>{l}</Tag>)}
              </div>
            ))}
            {gh.issues.length === 0 && (
              <div className="border-t border-line px-4 py-[8px] text-[12px] text-ink-faint">none — an issue per piece of work is the backlog a branch and a PR close</div>
            )}
          </>
      </div>
  )
}

/** What to do next, from the numbers -- the sentence a person new to git
 *  needs and a person used to it can skim past. */
/* The uncommitted count and the files it counts wear one colour, ink,
 * like every other non-zero figure, so the eye ties them together across
 * the rule between them (2026-09-16). Zero is faint and lists nothing. The sentence that used
 * to sit between them -- "N files changed and not committed, a session
 * commits as it goes…" -- is gone: the figure and the list are the fact. */
function Uncommitted({ n }: { n: number }) {
  return <span className={n ? 'text-ink' : 'text-ink-faint'}>{n} uncommitted</span>
}

function Dirty({ files }: { files: string[] }) {
  if (files.length === 0) return null
  return (
    <div className="max-h-[160px] overflow-y-auto border-t border-line px-4 py-[7px] font-mono text-[11.5px] leading-[1.7] text-ink">
      {files.map((f) => <div key={f}>{f}</div>)}
    </div>
  )
}

function Tag({ children, tone }: { children: React.ReactNode; tone?: 'good' | 'bad' }) {
  const color = tone === 'bad' ? 'var(--color-faber)' : tone === 'good' ? 'var(--color-noctua)' : 'var(--color-ink-faint)'
  return (
    <span className="shrink-0 rounded-control border px-[6px] py-px font-mono text-[10px]" style={{ borderColor: 'var(--color-line)', color }}>
      {children}
    </span>
  )
}

const ago = (unix: number): string => {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - unix))
  if (s < 60) return 'now'
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

/* Settings is now only things that are true until you change them: the
 * prompts and the regression suite. The models table went because a mode's
 * model does not change unless you change it with /model, so a read-only
 * table of five rows saying "opus" four times was a page telling you what
 * you already set. The Schedule card went 2026-09-15 with the scheduler it
 * was the switchboard for: a section whose content is "nothing lives here"
 * is not a section. */
export function Settings({ onDecided }: { onDecided?: () => void }) {
  return (
    <>
      {/* One block, not two (2026-09-17). The prompts and the cases that
          guard them are halves of one working system: you edit the text
          here and the row underneath says whether the record still speaks
          for it, and what re-proving it would cost. Two headings made them
          look like two things you could attend to separately, which is
          exactly the mistake that let the suite sit unrun for a day. */}
      <Heading>Prompts</Heading>
      <Prompts />

      {/* What arrives (2026-09-15): the one scheduled thing's last run, and
          the proposals it staged, accepted or rejected here. This was the
          Inbox tab; it is maintenance-class, nightly, and belongs with the
          other things that are true until you change them. */}
      <Heading className="mt-7">Maintenance</Heading>
      <Maintenance onDecided={onDecided} />
    </>
  )
}

function Maintenance({ onDecided }: { onDecided?: () => void }) {
  const night = useFetched<{ nightshift: NightshiftSummary | null }>('/v2/nightshift')
  const inbox = useFetched<InboxPayload>('/v2/inbox')
  const broken = Boolean(night) && night !== false && night?.nightshift?.kind === 'broken'
  return (
    <>
      <Card>
        <div className="px-4 py-[13px] text-[12.5px] leading-[1.6]"
             style={{ color: broken ? 'var(--color-faber)' : 'var(--color-ink-dim)' }}>
          {night === false ? 'Could not read nightshift\'s record.' : night === null ? 'Loading…' : nightshiftLine(night.nightshift)}
        </div>
      </Card>
      <div className="mt-[10px]">
        {inbox === false ? <Unreachable what="the proposals" /> : inbox === null ? <Loading /> : <Inbox data={inbox} onDecided={onDecided} />}
      </div>
    </>
  )
}


/* A curiosity, not a setting — which is why it lives on Stats.
 *
 * The engine reports a per-turn figure at API list price. Under a
 * subscription that is not a charge, so it has no business in a settings
 * page where numbers look like things you owe. As a line under the token
 * counts it reads as what it is: what all this would have cost the other
 * way.
 */
export function ListPriceFact({
  data,
  totalTurns,
}: {
  data: BillingPayload
  /** Every turn the token counts above cover. */
  totalTurns: number
}) {
  if (data.list_cost <= 0 || data.priced_turns === 0) return null

  /* Priced from the same transcripts the token counts come from, so the
   * figure normally covers every turn above it. It falls short only by
   * turns whose model the price table does not know -- and then it says
   * so, rather than quietly implying it is the total. (It once covered 120
   * of 8,000 turns and read 20x low against its own tokens.) */
  const partial = data.priced_turns < totalTurns

  return (
    <div className="mt-[13px] flex flex-wrap items-baseline gap-x-[7px] gap-y-[3px] border-t border-line pt-[11px] font-mono text-[11.5px]">
      <span className="text-ink-faint">
        on the API,{' '}
        {partial ? `${data.priced_turns.toLocaleString()} of ${totalTurns.toLocaleString()} turns` : 'this'}{' '}
        would have been
      </span>
      {/* Grouped like the token count above it: $2,427.05, not $2427.05. */}
      <span className="tabular-nums text-ink">
        ${data.list_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
      {/* Short, because a long disclaimer under a number makes the number
          itself look disputed. */}
      <span className="text-ink-faint">· the subscription covered it</span>
    </div>
  )
}


interface PromptFile {
  id: string
  path: string
  markdown: string | null
}

/* The prompt editor.
 *
 * Editing here rather than in the vault is worth it for one reason: saving
 * re-renders the config dirs immediately, so the loop between changing a
 * prompt and running the suite against it is short. Editing the file in
 * Obsidian and waiting for the next launch is the long version of the same
 * thing.
 */
function Prompts() {
  const data = useFetched<{ prompts: PromptFile[] }>('/v2/prompts')
  const [selected, setSelected] = useState('system')
  const [draft, setDraft] = useState<string | null>(null)
  const [saving, setSaving] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle')
  // The same sliding highlight as the rail and the tab strip: the pill in
  // the signature follows the pointer and rests on the selected file.
  const tabs = usePill(selected)

  if (data === false) return <Unreachable what="the prompts" />
  if (data === null) return <Loading />

  const file = data.prompts.find((p) => p.id === selected)
  const text = draft ?? file?.markdown ?? ''
  const dirty = draft !== null && draft !== (file?.markdown ?? '')

  return (
    <Card>
      <div ref={tabs.list} onMouseLeave={tabs.leave}
           className="relative flex items-center gap-[6px] border-b border-line px-[10px] py-[7px]">
        <Pill at={tabs.pill} />
        {data.prompts.map((p) => (
          <button
            key={p.id}
            ref={tabs.row(p.id)}
            type="button"
            onMouseEnter={() => tabs.enter(p.id)}
            onClick={() => {
              setSelected(p.id)
              setDraft(null)          // an unsaved edit is not carried to another file
              setSaving('idle')
            }}
            className={`relative rounded-control px-[8px] py-[3px] font-mono text-[11.5px] transition-colors ${
              p.id === selected || tabs.hover === p.id ? 'text-ink' : 'text-ink-faint'
            }`}
          >
            {p.id}
          </button>
        ))}
        <span className="ml-auto font-mono text-[10.5px] text-ink-faint">{file?.path}</span>
      </div>

      <textarea
        value={text}
        onChange={(e) => setDraft(e.target.value)}
        spellCheck={false}
        className="h-[280px] w-full resize-y border-0 bg-ground px-[12px] py-[10px] font-mono text-[11.5px] leading-[1.65] text-ink-dim outline-none"
      />

      <div className="flex items-center gap-[10px] border-t border-line px-[12px] py-[8px]">
        <span className="font-mono text-[11px] text-ink-faint">
          {/* What saving does, said plainly: the file in the vault is what
              the next session reads. It used to say "re-renders every mode",
              which stopped being true on 2026-09-12 and stayed on the
              screen until 09-15. */}
          {saving === 'saved'
            ? 'Saved to the vault — the next session reads it; running ones do not'
            : saving === 'failed'
              ? 'Could not save'
              : dirty
                ? 'Unsaved changes'
                : 'Saves the file in the vault, uncommitted — commit it from Repo'}
        </span>
        <button
          type="button"
          disabled={!dirty || saving === 'saving'}
          onClick={async () => {
            setSaving('saving')
            const ok = await put(`/v2/prompts/${selected}`, { markdown: text })
            setSaving(ok ? 'saved' : 'failed')
            if (ok) setDraft(null)
          }}
          className="ml-auto rounded-control px-[11px] py-[4px] font-mono text-[11.5px] text-ink transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
          style={{ background: 'var(--color-sig)' }}
        >
          Save
        </button>
      </div>

      {/* The cases that guard what is above, in the same card: editing the
          text and knowing whether the record still speaks for it are one
          motion. */}
      <Regression />
    </Card>
  )
}

interface RegressionCase {
  id: string
  mode: string
  rule: string | null
  prompt: string
  tests: string
  /** The case's last result, and whether it still speaks for the prompt
   *  as it is now -- `stale` when the composed prompt has changed since. */
  last: { passed: boolean; why: string; attempts: number; ran_at: string; reply: string; stale: boolean } | null
}
interface RegressionStatus {
  running: boolean
  scope: string | null
  done: number
  total: number
  started_at?: string
  results: { id: string; mode: string; rule: string | null; passed: boolean; why: string; attempts: number }[]
}

/* An outline that travels, rather than the filled pill.
 *
 * The filled tint is right on the Prompts tabs, where the row is the whole
 * control and the pill is the file you are looking at. Here the row sits
 * inside a sentence, and a block of colour mid-line reads as a second
 * background rather than as a choice: it filled the line it was supposed to
 * annotate. A one-pixel ring marks the same thing and leaves the words on
 * the card's own ground.
 *
 * Moved by transform and sized by width, with a 300ms
 * cubic-bezier(0.33, 0.55, 0.2, 1) -- the marker travels rather than
 * teleporting, and a composited move never relayouts the sentence it sits
 * in. The ring is inset so it adds nothing to the box, and drawn in the
 * signature like every other reading the interface makes about itself.
 */
function ScopeMark({ at }: { at: PillRect | null }) {
  if (!at) return null
  const glide = '300ms cubic-bezier(0.33, 0.55, 0.2, 1)'
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute left-0 top-0 rounded-control"
      style={{
        width: at.width,
        height: at.height,
        transform: `translate(${at.left}px, ${at.top}px)`,
        boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--color-sig) 62%, transparent)',
        transition: `transform ${glide}, width ${glide}, height ${glide}`,
      }}
    />
  )
}

/* The regression suite, scoped and recorded.
 *
 * Reading it is free; running it is one real session per case on production
 * models -- so the button says what it will spend, and the scope is what an
 * edit can affect: `system` is composed into every mode, an overlay into
 * one. Each case keeps its last result with the prompt it ran against, so
 * a green suite is a state that accumulates over small runs rather than a
 * thirteen-session ceremony. A failing case reran once before it counted. */
function Regression() {
  const [open, setOpen] = useState(false)
  const [openCases, setOpenCases] = useState<Set<string>>(new Set())
  const toggleCase = (id: string) =>
    setOpenCases((o) => { const n = new Set(o); if (n.has(id)) n.delete(id); else n.add(id); return n })
  /* `not current` when the record has anything it no longer speaks for:
   * that is the run you want after an edit, and re-proving the cases the
   * edit could not have touched costs sessions to learn nothing. It is
   * only offered when non-empty, so this falls back on a green suite. */
  const [scope, setScope] = useState<string | null>(null)
  const [status, setStatus] = useState<RegressionStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)          // re-read the suite when a run ends
  // Keyed by `tick`, so the record is re-read once a run has landed its
  // results; the query string changes nothing on the server.
  const view = useFetched<{ cases: RegressionCase[]; scopes: Record<string, number>; sessions: number; path: string }>(`/v2/regression?t=${tick}`)
  /* Computed before the loading returns, because the pill below is a hook
     and hooks cannot sit after one. `not current` leads when the payload
     offers it, so an untouched card already points at the cheap run. */
  const effectiveScope = scope ?? (view && 'not current' in view.scopes ? 'not current' : 'system')
  // The same sliding pill as the Prompts tabs, the rail and the tab strip:
  // one highlight that follows the pointer and rests where the choice is.
  const scopes = usePill(effectiveScope)

  /* Ask on mount, not only after clicking Run.
   *
   * The run is the backend's, not this component's: it survives leaving
   * Settings, and this card used to forget it the moment it unmounted. A
   * run started here, then looked at from the Terminal tab and back, showed
   * "run 13" beside a suite that was busy running 13 -- the only way to see
   * progress was to keep reopening the tab and watch the pass count move
   * (2026-09-16). Polled every two seconds while one is going, which is
   * plenty for cases that take twenty each, and once on arrival so the card
   * is right whoever started it. */
  useEffect(() => {
    let alive = true
    let id: ReturnType<typeof setInterval> | undefined
    const read = async () => {
      const s = await get<RegressionStatus>('/v2/regression/status')
      if (!alive || !s) return
      setStatus((was) => {
        // A run that has just ended: re-read the record, which is where the
        // per-case results and their staleness live.
        if (was?.running && !s.running) setTick((n) => n + 1)
        return s
      })
      if (!s.running && id) { clearInterval(id); id = undefined }
      if (s.running && !id) id = setInterval(() => void read(), 2000)
    }
    void read()
    return () => { alive = false; if (id) clearInterval(id) }
  }, [])

  if (view === false) return <div className="border-t border-line"><Unreachable what="the regression suite" /></div>
  if (view === null) return <div className="border-t border-line"><Loading /></div>

  const cost = view.scopes[effectiveScope] ?? 0
  /* The tally counts what has landed, including results from a run that is
   * still going: they are in the status payload before they are in the
   * record, and a number that only moves when the run finishes is how this
   * looked frozen while it was working. */
  const landed = new Map((status?.results ?? []).map((r) => [r.id, r]))
  const tally = (cs: RegressionCase[]) => ({
    passed: cs.filter((c) => landed.get(c.id)?.passed ?? (c.last?.passed && !c.last.stale)).length,
    failed: cs.filter((c) => (landed.has(c.id) ? !landed.get(c.id)!.passed : c.last && !c.last.passed && !c.last.stale)).length,
    stale: cs.filter((c) => !landed.has(c.id) && c.last?.stale).length,
    never: cs.filter((c) => !landed.has(c.id) && !c.last).length,
  })
  const t = tally(view.cases)
  /* When the record last changed, from the cases themselves rather than
   * from the run: a scoped run updates the cases it covered and leaves the
   * rest alone, so the newest case result is the honest answer to "has this
   * been run". */
  const lastRun = view.cases.map((c) => c.last?.ran_at).filter(Boolean).sort().pop()
  /* A date, not just a clock. "last run 22:27" was true yesterday and read
     the same today; "yesterday 22:27" stops meaning anything after a week. */
  const runStamp = lastRun
    ? new Date(lastRun).toLocaleString([], { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
    : null
  const needsRun = t.stale + t.never
  const dot = (c: RegressionCase) =>
    !c.last ? 'var(--color-line)' : c.last.stale ? 'var(--color-ink-faint)' : c.last.passed ? 'var(--color-good)' : 'var(--color-faber)'

  const start = async () => {
    setError(null)
    const out = await post<{ started: string; sessions: number }>('/v2/regression/run', { scope: effectiveScope })
    if ('error' in out) { setError(out.error); return }
    setStatus({ running: true, scope: effectiveScope, done: 0, total: out.sessions, results: [] })
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-[14px] gap-y-[6px] border-t border-line px-4 py-[12px]">
        <span className="text-[13px] text-ink">{plural(view.cases.length, 'case')}</span>
        {/* What the record says, at a glance: current passes, current
            failures, results the prompt has moved past, never run. */}
        <span className="font-mono text-[11px] text-ink-faint">
          <span style={{ color: 'var(--color-good)' }}>{t.passed} pass</span> · <span style={{ color: t.failed ? 'var(--color-faber)' : undefined }}>{t.failed} fail</span> · {t.stale} stale · {t.never} never run
        </span>
        {/* Whether the record speaks for the prompts as they are now. A
            tally alone never answered "do I need to run this", which is the
            only question the card is asked between runs (2026-09-16). */}
        <span className="font-mono text-[11px]"
              style={{ color: needsRun ? 'var(--color-sig-6)' : 'var(--color-ink-faint)' }}>
          {status?.running
            ? 'running now'
            : needsRun
              ? `${plural(needsRun, 'case')} not current`
              : 'every case current'}
          {runStamp && !status?.running && ` · last run ${runStamp}`}
        </span>
        <button type="button" onClick={() => setOpen(!open)}
                className="ml-auto font-mono text-[11px] text-ink-faint underline decoration-line underline-offset-2 hover:text-ink-dim">
          {open ? 'hide cases' : 'show cases'}
        </button>
      </div>

      {open && (
        <div className="border-t border-line">
          {view.cases.map((c) => (
            <div key={c.id} className="flex items-start gap-[10px] border-b border-line px-4 py-[8px] last:border-b-0">
              <span className="mt-[6px] h-[7px] w-[7px] shrink-0 rounded-full" style={{ background: dot(c) }}
                    title={!c.last ? 'never run' : c.last.stale ? 'ran against an earlier prompt' : c.last.passed ? 'passed' : c.last.why} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-[8px] font-mono text-[11px]">
                  <span className="text-ink-faint">{c.id}</span>
                  <span style={{ color: MODE_ACCENT[c.mode as Mode] ?? 'var(--color-ink-dim)' }}>{c.mode}</span>
                  {c.rule && <span className="text-ink-faint">{c.rule}</span>}
                  {c.last && (
                    <span className="ml-auto text-ink-faint">
                      {c.last.stale ? 'stale · ' : ''}{c.last.passed ? 'passed' : 'failed'}{c.last.attempts > 1 ? ` on attempt ${c.last.attempts}` : ''} · {sinceLabel(c.last.ran_at).replace(/^since /, '')}
                    </span>
                  )}
                </div>
                <div className="mt-[2px] text-[12px] leading-[1.5] text-ink-dim">{c.tests}</div>
                {c.last && !c.last.passed && !c.last.stale && (
                  <>
                    <div className="mt-[3px] font-mono text-[11px]" style={{ color: 'var(--color-faber)' }}>{c.last.why}</div>
                    {/* What the session actually said. The assertion names
                        the rule it broke; only the reply says how, and it
                        sat in the payload rendered nowhere. */}
                    {c.last.reply && (
                      <>
                        <button type="button" onClick={() => toggleCase(c.id)}
                                className="mt-[3px] font-mono text-[10.5px] text-ink-faint underline decoration-line underline-offset-2 hover:text-ink-dim">
                          {openCases.has(c.id) ? 'hide the reply' : 'read the reply'}
                        </button>
                        {openCases.has(c.id) && (
                          <pre className="mt-[4px] max-h-[220px] overflow-auto whitespace-pre-wrap rounded-control border border-line bg-ground px-[9px] py-[7px] font-mono text-[11px] leading-[1.6] text-ink-dim">
                            {c.last.reply}
                          </pre>
                        )}
                      </>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Run: the scope is what an edit can affect, and the cost is said
          before the click. */}
      <div className="flex flex-wrap items-center gap-[10px] border-t border-line px-4 py-[9px] font-mono text-[11px]">
        <span className="shrink-0 text-ink-faint">run the cases an edit to</span>
        {/* A row with a sliding pill, not a `select`.
            The scopes are six or seven short words and all of them matter
            to the sentence around them, so a native menu hid the choice
            behind a click, drew macOS's own chrome in the middle of the
            card, and took a red focus ring that belongs to no palette here.
            Hovering one now tells you what it would cost before you commit
            to it, which is the question the row is for. */}
        <div ref={scopes.list} onMouseLeave={scopes.leave}
             className="relative flex items-center gap-[2px]" role="group" aria-label="Scope">
          <ScopeMark at={scopes.pill} />
          {Object.keys(view.scopes).map((s) => (
            <button
              key={s}
              ref={scopes.row(s)}
              type="button"
              onMouseEnter={() => scopes.enter(s)}
              onClick={() => setScope(s)}
              aria-pressed={s === effectiveScope}
              title={`${plural(view.scopes[s] ?? 0, 'session')} on production models`}
              className={`relative rounded-control px-[7px] py-[3px] transition-colors ${
                s === effectiveScope || scopes.hover === s ? 'text-ink' : 'text-ink-faint'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        {/* The selected scope's cost, not the hovered one. Hover moves the
            pill and nothing else, the way the Prompts tabs above do: with
            the sentence following the pointer it read "affects 4 sessions"
            beside a button saying "run 13", and moving to that button ran
            the one the sentence had stopped describing. Each scope carries
            its own cost as a tooltip, which previews without disagreeing. */}
        <span className="shrink-0 text-ink-faint">
          affects {plural(cost, 'session')} on production models
        </span>
        {status?.running ? (
          /* The run, while it is going: which scope, how far, and a bar,
              because a pair of numbers that changes every twenty seconds
              does not read as motion. */
          <span className="ml-auto flex items-center gap-[8px] text-ink-dim">
            <span
              aria-hidden
              className="inline-block h-[3px] w-[70px] overflow-hidden rounded-full"
              style={{ background: 'var(--color-line)' }}
            >
              <span
                className="block h-full transition-[width] duration-500"
                style={{
                  width: `${status.total ? Math.round((status.done / status.total) * 100) : 0}%`,
                  background: 'var(--color-sig)',
                }}
              />
            </span>
            <span role="status">
              running {status.scope} · {status.done}/{status.total}
              {status.results.length > 0 && ` · ${status.results.filter((r) => r.passed).length} pass, ${status.results.filter((r) => !r.passed).length} fail`}
            </span>
          </span>
        ) : (
          <button type="button" onClick={() => void start()} disabled={cost === 0}
                  className="ml-auto rounded-control px-[11px] py-[4px] text-ink transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
                  style={{ background: 'var(--color-sig)' }}>
            run {cost}
          </button>
        )}
        {error && <span className="basis-full text-[11px]" style={{ color: 'var(--color-faber)' }}>{error}</span>}
      </div>
    </>
  )
}

function Loading() {
  return (
    <div className="rounded-card border border-line bg-surface px-4 py-[13px] text-[12.5px] text-ink-faint">
      Loading…
    </div>
  )
}

