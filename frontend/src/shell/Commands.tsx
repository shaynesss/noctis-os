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
import { MODE_LABEL, PERMISSION_LABEL, PERMISSION_CYCLE, type Mode, type Permission } from './mock'

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
