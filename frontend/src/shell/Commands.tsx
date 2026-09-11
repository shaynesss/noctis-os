/* Slash commands, and the model picker one of them opens.
 *
 * Every command here maps to something the shell can already do. That is the
 * rule: a menu of commands is a promise, and one that lists something
 * unimplemented is the same lie as a shortcut that does nothing — which this
 * UI has already been guilty of twice.
 *
 * The menu opens on "/" at the very start of an empty draft. Not on any "/",
 * because paths are typed constantly here and a menu that appears mid-prompt
 * every time you write `src/shell` would be worse than no menu at all.
 */
import { useEffect, useState } from 'react'
import { matching } from './slash'
import { MODE_LABEL, PERMISSION_LABEL, PERMISSION_CYCLE, type Mode, type Permission } from './domain'

/** The list shown above the composer while a command is being typed. */
export function CommandMenu({
  typed,
  cursor,
  onPick,
}: {
  typed: string
  cursor: number
  onPick: (name: string) => void
}) {
  const items = matching(typed)
  if (items.length === 0) return null

  return (
    <div className="mb-[6px] overflow-hidden rounded-[5px] border border-line bg-surface">
      {items.map((c, i) => (
        <button
          key={c.name}
          type="button"
          onMouseDown={(e) => {
            e.preventDefault()   // keep focus in the composer
            onPick(c.name)
          }}
          className={`flex w-full items-baseline gap-[12px] px-[12px] py-[6px] text-left ${
            i === cursor % items.length ? 'bg-elevated' : ''
          }`}
        >
          <span className="w-[104px] shrink-0 font-mono text-[12px] text-noctua">/{c.name}</span>
          <span className="text-[12px] text-ink-faint">{c.summary}</span>
        </button>
      ))}
    </div>
  )
}

export interface ModelOption {
  id: string
  name: string
  blurb: string
}

/* The model picker.
 *
 * Numbered, because the list is short and fixed and a number is faster than
 * an arrow key. The mode's own default is marked rather than hidden: the
 * useful question is not only "what is this set to" but "what would it be if
 * I left it alone", and a picker that only shows the current value cannot
 * answer the second.
 */
export function ModelPicker({
  models,
  current,
  modeDefault,
  mode,
  onPick,
  onClose,
}: {
  models: ModelOption[]
  /** The session's override, or null when it follows the mode. */
  current: string | null
  modeDefault: string
  mode: Mode
  onPick: (id: string | null) => void
  onClose: () => void
}) {
  const active = current ?? modeDefault
  const [cursor, setCursor] = useState(() => Math.max(0, models.findIndex((m) => m.id === active)))

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        setCursor((c) => Math.min(models.length - 1, c + 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setCursor((c) => Math.max(0, c - 1))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        onPick(models[cursor].id)
      } else if (/^[1-9]$/.test(e.key) && models[Number(e.key) - 1]) {
        e.preventDefault()
        onPick(models[Number(e.key) - 1].id)
      } else if (e.key.toLowerCase() === 'd') {
        e.preventDefault()
        onPick(null)          // back to whatever the mode says
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [cursor, models, onPick, onClose])

  return (
    <Overlay label="Select model" onClose={onClose}>
      <p className="m-0 mb-[14px] text-[12.5px] leading-[1.6] text-ink-faint">
        For this session only. New sessions use their mode's model —{' '}
        <span className="text-ink-dim">{MODE_LABEL[mode]}</span> defaults to{' '}
        <span className="text-ink-dim">{name(models, modeDefault)}</span>.
      </p>

      <div className="flex flex-col">
        {models.map((m, i) => {
          const selected = i === cursor
          const isActive = m.id === active
          return (
            <button
              key={m.id}
              type="button"
              onMouseEnter={() => setCursor(i)}
              onClick={() => onPick(m.id)}
              className={`flex items-baseline gap-[10px] rounded-[4px] px-[9px] py-[6px] text-left ${
                selected ? 'bg-elevated' : ''
              }`}
            >
              <span className="w-[14px] shrink-0 font-mono text-[11.5px] text-ink-faint">{i + 1}.</span>
              <span className="w-[92px] shrink-0 font-mono text-[12.5px] text-ink">
                {m.name}
                {isActive && <span className="ml-[5px] text-good">✓</span>}
              </span>
              <span className="text-[12px] text-ink-faint">{m.blurb}</span>
              {m.id === modeDefault && (
                <span className="ml-auto shrink-0 font-mono text-[10.5px] text-ink-faint">
                  mode default
                </span>
              )}
            </button>
          )
        })}
      </div>

      <div className="mt-[14px] border-t border-line pt-[10px] font-mono text-[11px] text-ink-faint">
        ↵ or 1–{models.length} to use for this session · d to follow the mode · esc to cancel
      </div>
    </Overlay>
  )
}

/** The permission picker, with what each mode actually means here. */
export function PermissionPicker({
  current,
  promptsAnswerable,
  onPick,
  onClose,
}: {
  current: Permission
  /** False in a hosted session, where nobody can answer a prompt. */
  promptsAnswerable: boolean
  onPick: (p: Permission) => void
  onClose: () => void
}) {
  const meaning: Record<Permission, string> = {
    plan: 'Read and plan only — proposes, changes nothing',
    manual: promptsAnswerable
      ? 'Asks before anything that changes your machine'
      : 'Denies anything not pre-allowed — nobody can answer a prompt here',
    acceptEdits: 'Edits files without asking; still refuses the rest',
    auto: 'Runs its tools without asking',
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      } else if (/^[1-9]$/.test(e.key) && PERMISSION_CYCLE[Number(e.key) - 1]) {
        e.preventDefault()
        onPick(PERMISSION_CYCLE[Number(e.key) - 1])
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onPick, onClose])

  return (
    <Overlay label="Permissions" onClose={onClose}>
      <p className="m-0 mb-[14px] text-[12.5px] leading-[1.6] text-ink-faint">
        What this session may do without asking. ⇧⇥ cycles the same setting.
      </p>
      <div className="flex flex-col">
        {PERMISSION_CYCLE.map((p, i) => (
          <button
            key={p}
            type="button"
            onClick={() => onPick(p)}
            className={`flex items-baseline gap-[10px] rounded-[4px] px-[9px] py-[6px] text-left hover:bg-elevated ${
              p === current ? 'bg-elevated' : ''
            }`}
          >
            <span className="w-[14px] shrink-0 font-mono text-[11.5px] text-ink-faint">{i + 1}.</span>
            <span className="w-[92px] shrink-0 font-mono text-[12.5px] text-ink">
              {PERMISSION_LABEL[p]}
              {p === current && <span className="ml-[5px] text-good">✓</span>}
            </span>
            <span className="text-[12px] text-ink-faint">{meaning[p]}</span>
          </button>
        ))}
      </div>
      <div className="mt-[14px] border-t border-line pt-[10px] font-mono text-[11px] text-ink-faint">
        1–{PERMISSION_CYCLE.length} to set · esc to cancel
      </div>
    </Overlay>
  )
}

function name(models: ModelOption[], id: string): string {
  return models.find((m) => m.id === id)?.name ?? id
}

export interface PendingPermission {
  id: string
  mode: string
  tool: string
  args: Record<string, unknown>
  age: number
}

/** The argument worth reading, not all of them.
 *
 * "Write" is not a question anyone can answer; "Write to bootstrap.sh" is.
 * Tools name their subject differently, so the first match wins and anything
 * unrecognised falls back to the whole payload rather than showing nothing —
 * an unfamiliar tool is exactly when you most want to see what it was given.
 */
function subject(args: Record<string, unknown>): string {
  for (const key of ['command', 'file_path', 'path', 'pattern', 'url', 'query']) {
    const v = args[key]
    if (typeof v === 'string' && v) return v
  }
  const json = JSON.stringify(args ?? {})
  return json === '{}' ? '' : json
}

/** Asks before something changes, and blocks the session until answered.
 *
 * This is what makes the chip a control: with nothing here, a request had
 * nobody to go to, so `manual` silently meant `never`. Deny is the default
 * focus and Escape denies — the safe answer should be the one you can give
 * without reading carefully, since the unsafe one is the one worth a moment.
 */
export type Decide =
  (id: string, decision: 'allow' | 'deny', answers?: Record<string, string>) => void

interface Asked {
  question: string
  header?: string
  multiSelect?: boolean
  options: { label: string; description?: string }[]
}

/** The questions inside an AskUserQuestion call, or null for anything else.
 *
 * Defensive about shape rather than trusting it: this arrives as whatever the
 * engine put in the tool's arguments, and a malformed payload should fall
 * back to the ordinary dialog -- which can still deny -- instead of rendering
 * an empty question nobody can answer or dismiss.
 */
function questionsOf(request: PendingPermission): Asked[] | null {
  if (request.tool !== 'AskUserQuestion') return null
  const raw = (request.args as { questions?: unknown }).questions
  if (!Array.isArray(raw)) return null
  const asked = raw.filter((q): q is Asked =>
    Boolean(q) && typeof (q as Asked).question === 'string' &&
    Array.isArray((q as Asked).options) &&
    (q as Asked).options.every((o) => o && typeof o.label === 'string'),
  )
  return asked.length ? asked : null
}

/** The dialog that answers rather than permits.
 *
 * Every question must be answered before this can be sent: a partial reply
 * would come back as a question the session asked and did not get an answer
 * to, which is indistinguishable from not asking. Escape still declines
 * outright -- that is a real outcome and stays available, distinct from
 * answering badly.
 */
function QuestionRequest({
  request,
  questions,
  onDecide,
}: {
  request: PendingPermission
  questions: Asked[]
  onDecide: Decide
}) {
  const [picked, setPicked] = useState<Record<string, string>>({})
  const complete = questions.every((q) => picked[q.question])

  const send = () => {
    if (complete) onDecide(request.id, 'allow', picked)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onDecide(request.id, 'deny')
      } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && complete) {
        e.preventDefault()
        onDecide(request.id, 'allow', picked)
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [request.id, onDecide, complete, picked])

  return (
    <Overlay label={`${request.mode} is asking`} onClose={() => onDecide(request.id, 'deny')}>
      {questions.map((q) => (
        <div key={q.question} className="mb-[15px]">
          {q.header && (
            <div className="mb-[5px] font-mono text-[10.5px] uppercase tracking-[0.11em] text-ink-faint">
              {q.header}
            </div>
          )}
          <div className="mb-[9px] text-[13.5px] leading-[1.55] text-ink">{q.question}</div>
          <div className="flex flex-col gap-[5px]">
            {q.options.map((o) => {
              const on = picked[q.question] === o.label
              return (
                <button
                  key={o.label}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setPicked((p) => ({ ...p, [q.question]: o.label }))}
                  className={`rounded-[4px] border px-[10px] py-[7px] text-left transition-colors ${
                    on ? 'border-ink-faint bg-elevated' : 'border-line hover:bg-elevated'
                  }`}
                >
                  <div className="text-[12.5px] leading-[1.4] text-ink">{o.label}</div>
                  {o.description && (
                    <div className="mt-[3px] text-[11.5px] leading-[1.5] text-ink-dim">
                      {o.description}
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      ))}
      <div className="flex items-center gap-[8px]">
        <button
          type="button"
          disabled={!complete}
          onClick={send}
          className="rounded-[4px] border border-line px-[12px] py-[5px] font-mono text-[12px] text-ink hover:bg-elevated disabled:cursor-not-allowed disabled:text-ink-faint disabled:hover:bg-transparent"
        >
          Send
        </button>
        <button
          type="button"
          onClick={() => onDecide(request.id, 'deny')}
          className="rounded-[4px] border border-line px-[12px] py-[5px] font-mono text-[12px] text-ink hover:bg-elevated"
        >
          Decline
        </button>
        <span className="ml-auto font-mono text-[11px] text-ink-faint">
          {complete ? '⌘⏎ send · esc decline' : 'pick an answer · esc decline'}
        </span>
      </div>
    </Overlay>
  )
}

/** Dispatch, so neither branch renders the other's shape.
 *
 * A question is not a permission request wearing a different name. The
 * generic dialog showed one as raw JSON above an Allow button, which could
 * grant the call but could not answer it -- so the session got its own
 * question handed back with no reply in it. Split here rather than branched
 * inside one component, because the two have different hooks. */
export function PermissionRequest({ request, onDecide }: {
  request: PendingPermission
  onDecide: Decide
}) {
  const asked = questionsOf(request)
  return asked
    ? <QuestionRequest request={request} questions={asked} onDecide={onDecide} />
    : <ToolRequest request={request} onDecide={onDecide} />
}

function ToolRequest({
  request,
  onDecide,
}: {
  request: PendingPermission
  onDecide: Decide
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onDecide(request.id, 'deny')
      } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        onDecide(request.id, 'allow')
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [request.id, onDecide])

  const detail = subject(request.args)
  return (
    <Overlay label={`${request.mode} wants permission`} onClose={() => onDecide(request.id, 'deny')}>
      <div className="mb-[13px]">
        <div className="font-mono text-[13px] text-ink">{request.tool}</div>
        {detail && (
          <div className="mt-[6px] max-h-[180px] overflow-auto whitespace-pre-wrap break-all rounded-[4px] border border-line bg-elevated px-[9px] py-[7px] font-mono text-[12px] leading-[1.55] text-ink-dim">
            {detail}
          </div>
        )}
      </div>
      <div className="flex items-center gap-[8px]">
        <button
          type="button"
          onClick={() => onDecide(request.id, 'allow')}
          className="rounded-[4px] border border-line px-[12px] py-[5px] font-mono text-[12px] text-ink hover:bg-elevated"
        >
          Allow
        </button>
        <button
          type="button"
          autoFocus
          onClick={() => onDecide(request.id, 'deny')}
          className="rounded-[4px] border border-line px-[12px] py-[5px] font-mono text-[12px] text-ink hover:bg-elevated"
        >
          Deny
        </button>
        <span className="ml-auto font-mono text-[11px] text-ink-faint">
          ⌘⏎ allow · esc deny
        </span>
      </div>
    </Overlay>
  )
}

function Overlay({
  label,
  children,
  onClose,
}: {
  label: string
  children: React.ReactNode
  onClose: () => void
}) {
  return (
    <div
      className="absolute inset-0 z-[65] flex items-start justify-center bg-black/55 pt-[13vh]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={label}
        className="w-[620px] max-w-[calc(100%-32px)] overflow-hidden rounded-[6px] border border-line bg-surface p-[16px] shadow-[0_18px_50px_rgba(0,0,0,0.55)]"
      >
        <div className="mb-[10px] font-mono text-[11px] font-bold uppercase tracking-[0.13em] text-ink-faint">
          {label}
        </div>
        {children}
      </div>
    </div>
  )
}


/* Promoting a conversation into the vault.
 *
 * The deliberate half of "SQLite with promotion": the store is a cache of
 * what was said, the vault is what was decided, and only a person can tell
 * those apart. So this asks rather than inferring — a title, where it goes,
 * and optionally the point of it, which is the part worth writing while you
 * still remember why the conversation mattered.
 */
export function PromotePicker({
  suggestedTitle,
  onPromote,
  onClose,
}: {
  suggestedTitle: string
  onPromote: (req: { rel_path: string; title: string; note: string }) => Promise<string | null>
  onClose: () => void
}) {
  const [title, setTitle] = useState(suggestedTitle)
  const [folder, setFolder] = useState('wiki')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Derived rather than a second field to keep in step. Slashes out, because
  // a title containing one would silently become a directory.
  const relPath = `${folder}/${title.replace(/[\\/]/g, '-').trim() || 'Untitled'}.md`

  return (
    <Overlay label="Promote to vault" onClose={onClose}>
      <p className="m-0 mb-[14px] text-[12.5px] leading-[1.6] text-ink-faint">
        Writes this conversation into the vault as a note. The transcript stays in the store —
        this is the curated copy, and nothing overwrites an existing file.
      </p>

      <label className="mb-[10px] block">
        <span className="mb-[4px] block font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-faint">
          Title
        </span>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          autoFocus
          className="w-full rounded-[4px] border border-line bg-ground px-[10px] py-[6px] font-mono text-[12px] text-ink outline-none focus:border-[var(--color-noctua)]"
        />
      </label>

      <label className="mb-[10px] block">
        <span className="mb-[4px] block font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-faint">
          Folder
        </span>
        <input
          value={folder}
          onChange={(e) => setFolder(e.target.value.replace(/^\/+|\/+$/g, ''))}
          spellCheck={false}
          className="w-full rounded-[4px] border border-line bg-ground px-[10px] py-[6px] font-mono text-[12px] text-ink outline-none focus:border-[var(--color-noctua)]"
        />
      </label>

      <label className="mb-[12px] block">
        <span className="mb-[4px] block font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-faint">
          Why it matters <span className="normal-case tracking-normal">— optional, sits above the transcript</span>
        </span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          className="w-full resize-none rounded-[4px] border border-line bg-ground px-[10px] py-[8px] text-[12.5px] leading-[1.6] text-ink-dim outline-none focus:border-[var(--color-noctua)]"
        />
      </label>

      <div className="flex items-center gap-[10px] border-t border-line pt-[11px]">
        <span className="min-w-0 flex-1 truncate font-mono text-[11px]">
          {error ? (
            <span className="text-faber">{error}</span>
          ) : (
            <span className="text-ink-faint">{relPath}</span>
          )}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-[4px] px-[11px] py-[5px] font-mono text-[11.5px] text-ink-dim hover:bg-elevated"
        >
          Cancel
        </button>
        <button
          type="button"
          disabled={busy || !title.trim()}
          onClick={async () => {
            setBusy(true)
            setError(await onPromote({ rel_path: relPath, title: title.trim(), note }))
            setBusy(false)
          }}
          className="rounded-[4px] px-[11px] py-[5px] font-mono text-[11.5px] text-ground transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
          style={{ background: 'var(--color-noctua)' }}
        >
          {busy ? 'Writing…' : 'Promote'}
        </button>
      </div>
    </Overlay>
  )
}
