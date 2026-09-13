/* Several terminals, and the view that holds them stays mounted.
 *
 * The first version rendered one `Terminal` inside `Pane`, keyed by mode and
 * cwd. Two things were wrong with that, and one of them was a real defect:
 * clicking Stats unmounted the pane, and unmounting a terminal kills its
 * session. Reading a number cost you your conversation.
 *
 * So this view is rendered always and hidden when another rail item is
 * showing. Hiding sets `display: none`, which collapses the host to 0×0; the
 * ResizeObserver inside each `Terminal` sees the size come back on show and
 * refits, so nothing here has to know about xterm at all.
 *
 * The strip is deliberately its own thing rather than a fourth kind of Chat
 * tab. Chat tabs are conversations the orchestrator owns -- resumable by
 * engine id, with a composer bound to them. A terminal owns itself. Folding
 * the two into one tab bar would mean every tab-bar code path growing an
 * `if terminal`, and PTY-MIGRATION.md §7 is explicit that the two surfaces
 * run beside each other until one is clearly better, not entangled.
 */
import { useEffect, useState } from 'react'
import { Terminal } from './Terminal'
import { MODE_ACCENT, MODE_LABEL, type Mode } from './domain'

interface Slot {
  id: string
  mode: Mode
  cwd: string
}

/* An id with no counter behind it.
 *
 * The first version numbered slots from a module-level counter, and showed
 * that number as the label. Two things went wrong at once: the counter was
 * bumped inside a `useState` initializer, which StrictMode runs twice, so the
 * first terminal could be "2"; and closing a terminal left a hole, so the
 * strip read "general · 1, general · 4" with nothing in between and no way
 * to tell whether something had gone missing. Ids are random and labels are
 * positional now -- the strip shows 1, 2, 3 for whatever is open. */
const slot = (mode: Mode, cwd: string): Slot =>
  ({ id: `term-${mode}-${crypto.randomUUID().slice(0, 8)}`, mode, cwd })

export function Terminals({ mode, cwd, accent, hidden, onActive }: {
  mode: Mode
  cwd: string
  accent: string
  hidden: boolean
  /** Which terminal is showing, so the status bar can read its report. */
  onActive?: (id: string | null) => void
}) {
  const [slots, setSlots] = useState<Slot[]>(() => [slot(mode, cwd)])
  const [active, setActive] = useState<string>(() => slots[0].id)
  useEffect(() => { onActive?.(active || null) }, [active, onActive])

  const add = () => {
    // Opens in the mode and directory the shell is currently on, which is
    // what the launcher would do too. Switching mode first is the way to get
    // a different one; the strip does not grow its own mode picker.
    const s = slot(mode, cwd)
    setSlots((all) => [...all, s])
    setActive(s.id)
  }

  const close = (id: string) => {
    setSlots((all) => {
      const rest = all.filter((s) => s.id !== id)
      if (active === id) setActive(rest[rest.length - 1]?.id ?? '')
      return rest
    })
  }

  return (
    <div hidden={hidden} className="flex min-h-0 flex-1 flex-col">
      {/* The strip. Same height token as the tab bar above it so the two
          read as one system rather than two bars of nearly equal size. */}
      <div className="flex h-[34px] shrink-0 items-center gap-[2px] border-b border-line px-[8px] font-mono text-[11px]">
        {slots.map((s, i) => {
          const on = s.id === active
          return (
            <div
              key={s.id}
              className={`group flex h-[26px] items-center gap-[7px] rounded-[4px] px-[9px] ${
                on ? 'bg-elevated text-ink' : 'text-ink-dim hover:text-ink'
              }`}
            >
              <button type="button" onClick={() => setActive(s.id)} className="flex items-center gap-[7px]">
                <span className="h-[7px] w-[7px] rounded-[2px]" style={{ background: MODE_ACCENT[s.mode] }} />
                <span>{MODE_LABEL[s.mode].toLowerCase()} · {i + 1}</span>
              </button>
              <button
                type="button"
                aria-label="close terminal"
                onClick={() => close(s.id)}
                className="text-ink-faint opacity-0 hover:text-ink group-hover:opacity-100"
              >
                ×
              </button>
            </div>
          )
        })}
        <button
          type="button"
          onClick={add}
          aria-label="new terminal"
          className="ml-[4px] h-[26px] rounded-[4px] px-[8px] text-ink-faint hover:text-ink"
        >
          +
        </button>
        <span className="ml-auto text-ink-faint">{shortenHome(cwd)}</span>
      </div>

      {slots.length === 0 && (
        <div className="flex flex-1 items-center justify-center font-mono text-[12px] text-ink-faint">
          no terminals — press + to open one
        </div>
      )}
      {slots.map((s) => (
        /* Every slot stays mounted; only the active one is displayed. That is
           what keeps a background terminal's session alive. */
        <div key={s.id} hidden={s.id !== active} className="min-h-0 flex-1">
          <Terminal id={s.id} mode={s.mode} cwd={s.cwd} accent={accent} />
        </div>
      ))}
    </div>
  )
}

const shortenHome = (p: string) => {
  const home = '/Users/'
  const i = p.indexOf(home)
  if (i !== 0) return p
  const rest = p.slice(home.length)
  const slash = rest.indexOf('/')
  return slash === -1 ? '~' : `~${rest.slice(slash)}`
}
