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
import { ModeMark, Pill, usePill } from './Chrome'

export interface Slot {
  id: string
  mode: Mode
  cwd: string
  /** Engine session id to `--resume`, for a slot coming back after a reload
   *  or a history row reopened to continue. */
  resumeId?: string
  /** A first message, submitted as the session opens -- a handoff's carry. */
  prompt?: string
  /** How hard it thinks, from the launcher. Omitted leaves the engine's own
   *  configured level alone. Not remembered across a reload: a slot coming
   *  back reattaches to a live session or resumes one, and neither respawns. */
  effort?: string
  /** The model, when the launcher chose one other than the mode's own. */
  model?: string
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

/** Columns for `n` terminals on screen: a row up to three, a square-ish
 *  grid after -- 2 for 4, 3 for 5–9. */
export const gridColumns = (n: number): number => (n <= 3 ? Math.max(1, n) : Math.ceil(Math.sqrt(n)))

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
  /** Drop `ids` -- one tab, or a whole group -- into the position `before`
   *  holds (or at the end), keeping their order. */
  onReorder: (ids: string[], before: string | null) => void
  /** Toggle `id` into or out of a split with the showing terminal. */
  onSplit: (id: string) => void
}) {
  const shown = slots.find((s) => s.id === active) ?? slots[0]
  const visible = visibleWith(slots, shown).map((s) => s.id)
  /* Tabs move by dragging, the way a browser's do. Labels are positional
   * and so are ⌘1–9, so the order on screen is the order under the keys;
   * moving a tab is how you put the one you reach for most under ⌘1. What
   * travels on the drag is the ids being moved -- one tab, or a whole
   * bracket -- rather than state: there is nothing to clean up if the drop
   * lands outside. A grouped tab is not draggable on its own; its bracket
   * is, and moves as one module, because a group pulled apart tab by tab
   * read as a mess. */
  const dragging = useRef<string[] | null>(null)

  /* Consecutive tabs of one group are drawn inside one bracket. The shell
   * keeps a group's members adjacent when it forms one, so a run is the
   * whole group. */
  const runs: Slot[][] = []
  for (const s of slots) {
    const last = runs[runs.length - 1]
    if (last && s.group && last[0].group === s.group) last.push(s)
    else runs.push([s])
  }
  const runOf = (s: Slot) => runs.find((r) => r.includes(s)) ?? [s]
  /* Dropping onto a grouped tab lands before its whole bracket: a module
   * cannot be split by something landing inside it. */
  const dropBefore = (target: Slot) => runOf(target)[0].id
  const startDrag = (ids: string[]) => (e: React.DragEvent) => {
    dragging.current = ids
    e.dataTransfer.effectAllowed = 'move'
  }
  const dropOn = (target: Slot) => (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const ids = dragging.current
    dragging.current = null
    if (ids && !ids.includes(target.id)) onReorder(ids, dropBefore(target))
  }
  const canDropOn = (target: Slot) => (e: React.DragEvent) => {
    if (dragging.current && !dragging.current.includes(target.id)) e.preventDefault()
  }

  // The strip's one sliding highlight, as the rail's: it follows the
  // pointer and rests on the showing tab. The pill is the signature, so it
  // is the active mark as well as the hover; the tab carries no ring.
  const strip = usePill(shown?.id ?? null)

  const tab = (s: Slot, grouped: boolean) => {
    const i = slots.indexOf(s)
    const on = s.id === shown?.id
    const inSplit = visible.length > 1 && visible.includes(s.id)
    return (
      <div
        key={s.id}
        ref={strip.row(s.id)}
        draggable={!grouped}
        onDragStart={grouped ? undefined : startDrag([s.id])}
        onDragEnd={() => { dragging.current = null }}
        onDragOver={canDropOn(s)}
        onDrop={dropOn(s)}
        onMouseEnter={() => strip.enter(s.id)}
        className={`group relative flex h-[26px] cursor-default items-center gap-[7px] rounded-control px-[9px] transition-colors duration-150 ${
          on || inSplit || strip.hover === s.id ? 'text-ink' : 'text-ink-dim'
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
      {/* Tabs centred in the strip (2026-09-15), the directory pinned to the
          right edge outside the centring so it cannot push the tabs off
          centre. */}
      <div data-tauri-drag-region
           ref={strip.list}
           onMouseLeave={strip.leave}
           className="relative flex h-[var(--head-band)] shrink-0 items-center justify-center gap-[2px] border-b border-line px-[8px] font-mono text-[11px]"
           onDragOver={(e) => { if (dragging.current) e.preventDefault() }}
           onDrop={(e) => {
             e.preventDefault()
             if (dragging.current) onReorder(dragging.current, null)
             dragging.current = null
           }}>
        <Pill at={strip.pill} />
        {runs.map((run) =>
          run.length === 1 ? tab(run[0], false) : (
            /* One bracket around a split's tabs, with a rule between them:
               the strip says which terminals share the screen, and the
               bracket is what you drag. Keyed by the run's first tab, not
               its group: a drag can leave a group's tabs non-adjacent, and
               two runs of one group under one key had React warning on
               every render. */
            <div key={run[0].id}
                 draggable
                 onDragStart={startDrag(run.map((s) => s.id))}
                 onDragEnd={() => { dragging.current = null }}
                 // Sized by its tabs, not fixed at their height: at h-26 with a
                 // 1px border the tabs overhung the bracket a pixel each way and
                 // the pill showed it. Radius 8 over 1px border + 2px padding
                 // leaves 6px inside, which is the pill's own corner -- so it
                 // nests instead of crossing the bracket's curve.
                 className="relative flex cursor-grab items-center rounded-card border border-line p-[2px] active:cursor-grabbing"
                 title="shown together — drag to move the group">
              {run.map((s, k) => (
                <div key={s.id} className="flex items-center">
                  {k > 0 && <span className="mx-[1px] h-[14px] w-px bg-line" />}
                  {tab(s, true)}
                </div>
              ))}
            </div>
          ))}
        <button
          type="button"
          onClick={onAdd}
          aria-label="new terminal"
          title="New session (⌘T)"
          className="ml-[4px] h-[26px] rounded-control px-[8px] text-ink-faint hover:text-ink"
        >
          +
        </button>
        {shown && <span className="absolute right-[12px] text-ink-faint">{shortenHome(shown.cwd)}</span>}
      </div>

      {slots.length === 0 && (
        <div className="flex flex-1 items-center justify-center font-mono text-[12px] text-ink-faint">
          no sessions — ⌘T to start one
        </div>
      )}
      {/* Every slot is mounted; the visible ones share a grid of equal
          cells. Up to three sit in a row; from four on the grid squares up
          -- 2×2, then 3×2, then 3×3 for the nine ⌘-digits reach -- rather
          than thinning into strips. A hidden slot is `display: none`, which
          takes no cell. Display is set inline rather than through `hidden`:
          a cell needs `display: flex` for its focus rule, and a utility
          class would win over the attribute. Rules between cells are
          borders on the cell -- left when it is not first in its row, top
          when it is not in the first row -- rather than a gap over a
          coloured ground, because the ground is translucent and a gap's
          colour would show through every pane. */}
      {/* The terminals stay a slab divided by rules, not cards: they were
          made cards for an afternoon (2026-09-15) and it looked wrong -- a
          terminal is the work surface, not a panel on it. */}
      <div className="grid min-h-0 flex-1"
           style={{
             gridTemplateColumns: `repeat(${gridColumns(visible.length)}, minmax(0, 1fr))`,
             gridAutoRows: 'minmax(0, 1fr)',
           }}>
        {slots.map((s) => {
          const at = visible.indexOf(s.id)
          const cols = gridColumns(visible.length)
          const focused = s.id === shown?.id
          return (
            <div key={s.id}
                 style={{ display: at < 0 ? 'none' : 'flex' }}
                 className={`min-h-0 min-w-0 flex-col ${at % cols > 0 ? 'border-l border-line' : ''} ${at >= cols ? 'border-t border-line' : ''}`}
                 onMouseDown={() => { if (at >= 0 && !focused) onSelect(s.id) }}>
              {/* Which column has the keyboard, when there is more than one:
                  a rule in the mode's accent along its top, nothing on the
                  others. */}
              {visible.length > 1 && (
                <div className="h-[2px] shrink-0" style={{ background: focused ? accent : 'transparent' }} />
              )}
              <div className="min-h-0 flex-1">
                <Terminal id={s.id} mode={s.mode} cwd={s.cwd} accent={accent}
                          resumeId={s.resumeId} prompt={s.prompt} effort={s.effort} model={s.model} />
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
