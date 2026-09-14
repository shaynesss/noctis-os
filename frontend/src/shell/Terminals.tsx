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
 *
 * Split: slots that share a `group` are shown side by side, each in its own
 * column, and the strip brackets their tabs together so the split is
 * visible from the tab bar. Selecting a grouped tab shows the whole group
 * with that one focused; selecting an ungrouped tab shows it alone. The
 * group travels with the arrangement across a reload.
 */
import { useRef } from 'react'
import { Terminal } from './Terminal'
import { MODE_LABEL, type Mode } from './domain'
import { ModeMark } from './Chrome'

export interface Slot {
  id: string
  mode: Mode
  cwd: string
  /** Engine session id to `--resume`, for a slot coming back after a reload
   *  or a history row reopened to continue. */
  resumeId?: string
  /** A first message, submitted as the session opens -- a handoff's carry. */
  prompt?: string
  /** Slots sharing a group are shown side by side. Never a group of one:
   *  the shell clears a group the moment it has a single member. */
  group?: string
}

/* An id with no counter behind it. The first version numbered slots from a
 * module-level counter and showed that as the label; StrictMode double-ran
 * the initializer and closing one left a hole, so the strip read
 * "general · 1, general · 4" with nothing between. Ids are random, labels
 * are positional. */
export const newSlot = (mode: Mode, cwd: string, extra: Partial<Slot> = {}): Slot =>
  ({ id: `term-${mode}-${crypto.randomUUID().slice(0, 8)}`, mode, cwd, ...extra })

/** The slots shown together with `shown`: its group, or itself. */
export const visibleWith = (slots: readonly Slot[], shown: Slot | undefined): Slot[] =>
  !shown ? [] : shown.group ? slots.filter((s) => s.group === shown.group) : [shown]

export function Terminals({ slots, active, accent, hidden, onSelect, onClose, onAdd, onReorder, onSplit }: {
  slots: Slot[]
  active: string | null
  accent: string
  hidden: boolean
  onSelect: (id: string) => void
  onClose: (id: string) => void
  onAdd: () => void
  /** Drop `id` into the position `before` holds (or at the end). */
  onReorder: (id: string, before: string | null) => void
  /** Toggle `id` into or out of a split with the showing terminal. */
  onSplit: (id: string) => void
}) {
  const shown = slots.find((s) => s.id === active) ?? slots[0]
  const visible = visibleWith(slots, shown).map((s) => s.id)
  /* Tabs move by dragging, the way a browser's do. Labels are positional
   * and so are ⌘1–9, so the order on screen is the order under the keys;
   * moving a tab is how you put the one you reach for most under ⌘1. The
   * id travels on the drag itself rather than in state -- there is nothing
   * to clean up if the drop lands outside. */
  const dragging = useRef<string | null>(null)

  /* Consecutive tabs of one group are drawn inside one bracket. The shell
   * keeps a group's members adjacent when it forms one, so a run is the
   * whole group. */
  const runs: Slot[][] = []
  for (const s of slots) {
    const last = runs[runs.length - 1]
    if (last && s.group && last[0].group === s.group) last.push(s)
    else runs.push([s])
  }

  const tab = (s: Slot) => {
    const i = slots.indexOf(s)
    const on = s.id === shown?.id
    const inSplit = visible.length > 1 && visible.includes(s.id)
    return (
      <div
        key={s.id}
        draggable
        onDragStart={(e) => { dragging.current = s.id; e.dataTransfer.effectAllowed = 'move' }}
        onDragEnd={() => { dragging.current = null }}
        onDragOver={(e) => { if (dragging.current && dragging.current !== s.id) e.preventDefault() }}
        onDrop={(e) => {
          e.preventDefault()
          e.stopPropagation()
          if (dragging.current && dragging.current !== s.id) onReorder(dragging.current, s.id)
          dragging.current = null
        }}
        className={`group flex h-[26px] cursor-default items-center gap-[7px] rounded-[4px] px-[9px] ${
          on ? 'bg-elevated text-ink' : inSplit ? 'text-ink' : 'text-ink-dim hover:text-ink'
        }`}
      >
        <button type="button" onClick={() => onSelect(s.id)} className="flex items-center gap-[7px]">
          <ModeMark mode={s.mode} dim={!on && !inSplit} />
          <span>{MODE_LABEL[s.mode].toLowerCase()} · {i + 1}</span>
        </button>
        {/* Split with the showing terminal, or leave the split it is in.
            Not on the showing tab itself: a terminal cannot split with
            itself, and the one you are looking at leaves a split by the
            other member's button or ⌘⇧-number. */}
        {!on && (
          <button
            type="button"
            aria-label={s.group && s.group === shown?.group ? 'unsplit' : 'split with the showing terminal'}
            title={s.group && s.group === shown?.group ? `Unsplit (⌘⇧${i + 1})` : `Split beside the showing terminal (⌘⇧${i + 1})`}
            onClick={() => onSplit(s.id)}
            className="text-ink-faint opacity-0 hover:text-ink group-hover:opacity-100"
          >
            {s.group && s.group === shown?.group ? '⊟' : '⊞'}
          </button>
        )}
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
  }

  return (
    <div hidden={hidden} className="flex min-h-0 flex-1 flex-col">
      {/* The same height as the rail's title band beside it, from the same
          token, so the two bottom rules meet as one line across the window
          -- a strip eight pixels shorter than the band left a step at the
          rail's edge. The strip's empty space drags the window: the title
          bar is an overlay with nothing in it, so this is the top edge you
          would reach for. */}
      <div data-tauri-drag-region
           className="flex h-[var(--head-band)] shrink-0 items-center gap-[2px] border-b border-line px-[8px] font-mono text-[11px]"
           onDragOver={(e) => { if (dragging.current) e.preventDefault() }}
           onDrop={(e) => {
             e.preventDefault()
             if (dragging.current) onReorder(dragging.current, null)
             dragging.current = null
           }}>
        {runs.map((run) =>
          run.length === 1 ? tab(run[0]) : (
            /* One bracket around a split's tabs, with a rule between them:
               the strip says which terminals share the screen. */
            <div key={run[0].group} className="flex h-[26px] items-center rounded-[5px] border border-line px-[2px]"
                 title="shown side by side">
              {run.map((s, k) => (
                <div key={s.id} className="flex items-center">
                  {k > 0 && <span className="mx-[1px] h-[14px] w-px bg-line" />}
                  {tab(s)}
                </div>
              ))}
            </div>
          ))}
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
      {/* Every slot is mounted; the visible ones share the row as equal
          columns. Display is set inline rather than through `hidden`: a
          column needs `display: flex` for its focus rule, and a utility
          class would win over the attribute. */}
      <div className="flex min-h-0 flex-1">
        {slots.map((s) => {
          const at = visible.indexOf(s.id)
          const focused = s.id === shown?.id
          return (
            <div key={s.id}
                 style={{ display: at < 0 ? 'none' : 'flex' }}
                 className={`min-h-0 min-w-0 flex-1 flex-col ${at > 0 ? 'border-l border-line' : ''}`}
                 onMouseDown={() => { if (at >= 0 && !focused) onSelect(s.id) }}>
              {/* Which column has the keyboard, when there is more than one:
                  a rule in the mode's accent along its top, nothing on the
                  others. */}
              {visible.length > 1 && (
                <div className="h-[2px] shrink-0" style={{ background: focused ? accent : 'transparent' }} />
              )}
              <div className="min-h-0 flex-1">
                <Terminal id={s.id} mode={s.mode} cwd={s.cwd} accent={accent}
                          resumeId={s.resumeId} prompt={s.prompt} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** `/Users/me/Developer/x` → `~/Developer/x`. */
export const shortenHome = (p: string) => {
  const m = p.match(/^\/Users\/[^/]+(\/.*)?$/)
  return m ? `~${m[1] ?? ''}` : p
}
