/* The strip of terminals, and the panes behind it.
 *
 * Presentational: the shell owns the slots, because the shell is what opens
 * them -- from the launcher, from a handoff, from a history row being
 * resumed, from the remembered arrangement at boot -- and a component that
 * owned its own list would need a second door for every one of those.
 *
 * Every slot stays mounted whichever is showing, and the whole view stays
 * mounted whichever rail item is showing. A terminal's session dies with
 * its component, so hiding is the only kind of "not showing" it can
 * survive. Hiding collapses the host to 0x0; the ResizeObserver inside each
 * Terminal sees the size come back and refits, so nothing here knows about
 * xterm at all.
 */
import { Terminal } from './Terminal'
import { MODE_ACCENT, MODE_LABEL, type Mode } from './domain'

export interface Slot {
  id: string
  mode: Mode
  cwd: string
  /** Engine session id to `--resume`, for a slot coming back after a reload
   *  or a history row reopened to continue. */
  resumeId?: string
  /** A first message, submitted as the session opens -- a handoff's carry. */
  prompt?: string
}

/* An id with no counter behind it. The first version numbered slots from a
 * module-level counter and showed that as the label; StrictMode double-ran
 * the initializer and closing one left a hole, so the strip read
 * "general · 1, general · 4" with nothing between. Ids are random, labels
 * are positional. */
export const newSlot = (mode: Mode, cwd: string, extra: Partial<Slot> = {}): Slot =>
  ({ id: `term-${mode}-${crypto.randomUUID().slice(0, 8)}`, mode, cwd, ...extra })

export function Terminals({ slots, active, accent, hidden, onSelect, onClose, onAdd }: {
  slots: Slot[]
  active: string | null
  accent: string
  hidden: boolean
  onSelect: (id: string) => void
  onClose: (id: string) => void
  onAdd: () => void
}) {
  const shown = slots.find((s) => s.id === active) ?? slots[0]
  return (
    <div hidden={hidden} className="flex min-h-0 flex-1 flex-col">
      {/* Same height token as the head band above it, so the two read as one
          system rather than two bars of nearly equal size. */}
      <div className="flex h-[34px] shrink-0 items-center gap-[2px] border-b border-line px-[8px] font-mono text-[11px]">
        {slots.map((s, i) => {
          const on = s.id === shown?.id
          return (
            <div
              key={s.id}
              className={`group flex h-[26px] items-center gap-[7px] rounded-[4px] px-[9px] ${
                on ? 'bg-elevated text-ink' : 'text-ink-dim hover:text-ink'
              }`}
            >
              <button type="button" onClick={() => onSelect(s.id)} className="flex items-center gap-[7px]">
                <span className="h-[7px] w-[7px] rounded-[2px]" style={{ background: MODE_ACCENT[s.mode] }} />
                <span>{MODE_LABEL[s.mode].toLowerCase()} · {i + 1}</span>
              </button>
              <button
                type="button"
                aria-label="close terminal"
                onClick={() => onClose(s.id)}
                className="text-ink-faint opacity-0 hover:text-ink group-hover:opacity-100"
              >
                ×
              </button>
            </div>
          )
        })}
        <button
          type="button"
          onClick={onAdd}
          aria-label="new terminal"
          title="New session (⌘T)"
          className="ml-[4px] h-[26px] rounded-[4px] px-[8px] text-ink-faint hover:text-ink"
        >
          +
        </button>
        {shown && <span className="ml-auto text-ink-faint">{shortenHome(shown.cwd)}</span>}
      </div>

      {slots.length === 0 && (
        <div className="flex flex-1 items-center justify-center font-mono text-[12px] text-ink-faint">
          no sessions — ⌘T to start one
        </div>
      )}
      {slots.map((s) => (
        <div key={s.id} hidden={s.id !== shown?.id} className="min-h-0 flex-1">
          <Terminal id={s.id} mode={s.mode} cwd={s.cwd} accent={accent}
                    resumeId={s.resumeId} prompt={s.prompt} />
        </div>
      ))}
    </div>
  )
}

/** `/Users/me/Developer/x` → `~/Developer/x`. */
export const shortenHome = (p: string) => {
  const m = p.match(/^\/Users\/[^/]+(\/.*)?$/)
  return m ? `~${m[1] ?? ''}` : p
}
