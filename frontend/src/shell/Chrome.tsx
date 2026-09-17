/* Rail, title strip, status bar, characters — the shell around the terminals. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Logo } from './Logo'
import { CHARACTERS, MODE_ACCENT, MODE_LABEL, type Mode } from './domain'

/* ------------------------------------------------------------------ rail */
/* Icons only, no labels (2026-09-17). Four items, two of which now wear the
 * mark of the thing they are about rather than a generic glyph, which is
 * what made the words removable: a label under an icon that already names
 * itself is furniture.
 *
 * Each carries its own viewBox and whether it is drawn filled or stroked,
 * because a borrowed mark comes with its own geometry and redrawing it on
 * this file's 24px stroked grid would be redrawing it wrong. The name stays
 * in `title` and `aria-label`, so hovering still says it and a screen
 * reader still hears it.
 */
const RAIL = [
  {
    id: 'terminal',
    label: 'Terminal',
    // The conversation surface: the real `claude`, hosted in a PTY. Claude's
    // own sunburst, drawn here rather than imported -- it takes
    // `currentColor` that way, and there is no official asset in this repo.
    // An approximation of the mark, not a copy of it: eight tapered rays
    // from a core, concave-sided so they read as light.
    viewBox: '0 0 24 24',
    fill: true,
    d: 'M12.95 10.00 Q12.81 6.70 12.00 1.40 Q11.19 6.70 11.05 10.00 Z M14.09 11.26 Q16.32 8.82 19.50 4.50 Q15.18 7.68 12.74 9.91 Z M14.00 12.95 Q17.30 12.81 22.60 12.00 Q17.30 11.19 14.00 11.05 Z M12.74 14.09 Q15.18 16.32 19.50 19.50 Q16.32 15.18 14.09 12.74 Z M11.05 14.00 Q11.19 17.30 12.00 22.60 Q12.81 17.30 12.95 14.00 Z M9.91 12.74 Q7.68 15.18 4.50 19.50 Q8.82 16.32 11.26 14.09 Z M10.00 11.05 Q6.70 11.19 1.40 12.00 Q6.70 12.81 10.00 12.95 Z M11.26 9.91 Q8.82 7.68 4.50 4.50 Q7.68 8.82 9.91 11.26 Z'
  },
  {
    id: 'repo',
    label: 'Repo',
    // The repositories the open terminals are in, one module each: the
    // commit log is the memory of where a piece of work was left, and the
    // app opens here. (The Inbox tab, and the Brief before it, went
    // 2026-09-15: what arrives is in Settings' Maintenance section.)
    // GitHub's own mark, on its own 16px grid, because the GitHub half of
    // that view is what the tab is for.
    viewBox: '0 0 16 16',
    fill: true,
    d: 'M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0 0 16 8c0-4.42-3.58-8-8-8z',
  },
  { id: 'stats', label: 'Stats', viewBox: '0 0 24 24', fill: false, d: 'M4 20V10M10 20V4M16 20v-7M22 20H2' },
  { id: 'settings', label: 'Settings', viewBox: '0 0 24 24', fill: false, d: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.5 19.4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3.6 14H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 3.6V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z' },
] as const

/* One highlight for a whole list, not one per row (2026-09-15, after
 * Bencho's selection list): a rounded pill that slides to the row under the
 * pointer and settles back on the active row when the pointer leaves. Rows
 * register with `row(key)`; the pill is measured from their rects relative
 * to the list after layout -- so a badge, a longer label or a row nested in
 * a bracket never puts it off, and on the first pass (refs still empty) it
 * simply waits for the measurement. Used by the rail and the tab strip. */
export type PillRect = { top: number; left: number; width: number; height: number }
export function usePill(active: string | null) {
  const [hover, setHover] = useState<string | null>(null)
  const rows = useRef<Record<string, HTMLElement | null>>({})
  const list = useRef<HTMLDivElement>(null)
  const [pill, setPill] = useState<PillRect | null>(null)
  const key = hover ?? active
  useLayoutEffect(() => {
    const measure = () => {
      const target = key ? rows.current[key] : null
      const box = list.current
      if (!target || !box) { setPill(null); return }
      const t = target.getBoundingClientRect(), b = box.getBoundingClientRect()
      setPill({ top: t.top - b.top, left: t.left - b.left, width: t.width, height: t.height })
    }
    measure()
    // The pill was measured once, on the key changing, and the rows moved
    // under it afterwards (2026-09-16): the strip centres its tabs, so any
    // tab changing width -- the monospace font arriving, a split button
    // appearing on the tab that stopped being the showing one -- shifts
    // every other tab, and the pill stayed where the tab had been. It now
    // follows every size change of the box and of any row, and the font.
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    if (ro) {
      if (list.current) ro.observe(list.current)
      for (const el of Object.values(rows.current)) if (el) ro.observe(el)
    }
    window.addEventListener('resize', measure)
    void document.fonts?.ready.then(measure)
    return () => { ro?.disconnect(); window.removeEventListener('resize', measure) }
  }, [key])
  return {
    list, hover, pill,
    row: (k: string) => (el: HTMLElement | null) => { rows.current[k] = el },
    enter: (k: string) => setHover(k),
    leave: () => setHover(null),
  }
}
export function Pill({ at }: { at: PillRect | null }) {
  if (!at) return null
  // The signature, not the elevated grey (2026-09-15): the same pill is the
  // hover highlight while it moves and the active mark where it rests, so
  // one colour does both and nothing else has to say "you are here". A
  // tint rather than the solid hue, so the label stays ink on it.
  return (
    <div aria-hidden className="pointer-events-none absolute rounded-control"
         style={{ ...at,
                  background: 'color-mix(in srgb, var(--color-sig) 34%, transparent)',
                  boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--color-sig) 45%, transparent)',
                  transition: 'top 220ms cubic-bezier(0.2, 0.8, 0.2, 1), left 220ms cubic-bezier(0.2, 0.8, 0.2, 1), width 220ms cubic-bezier(0.2, 0.8, 0.2, 1), height 220ms cubic-bezier(0.2, 0.8, 0.2, 1)' }} />
  )
}

export function Rail({ view, onView, badges }: {
  view: string
  onView: (v: string) => void
  /** Counts worth a glance, by rail item id. The inbox's is what is
   *  actually waiting on a decision -- it was a literal 3 in this file for
   *  weeks, which is a badge that says nothing. */
  badges?: Partial<Record<string, number>>
}) {
  const { list, row, enter, leave, hover, pill } = usePill(view)

  // pt-7 clears the macOS traffic lights, which titleBarStyle:"Overlay"
  // floats over the content at the top-left. They cannot be moved to the
  // right on macOS, so the rail moves out from under them instead.
  return (
    <nav className="flex w-[58px] shrink-0 flex-col border-r border-line">
      {/* The mark alone. The wordmark went with the labels (2026-09-17):
          "NOCTIS" spelled out above four named rows was the app saying its
          own name twice in a column it then had to be wide enough for. The
          star takes the active mode's accent via currentColor, so the
          identity shifts with the session rather than sitting inert above a
          UI that changes. */}
      {/* Height comes from --head-band, shared with the tab bar beside it,
          so the two bottom rules meet and the header reads as one band
          split by the rail rather than two boxes of different sizes. */}
      <div className="flex h-[var(--head-band)] shrink-0 items-center justify-center border-b border-line">
        <Logo size={16} className="shrink-0" style={{ color: 'var(--accent)' }} />
      </div>

      <div className="h-[10px] shrink-0" />

      <div ref={list} className="relative mx-auto flex w-[42px] flex-col gap-[2px]" onMouseLeave={leave}>
        <Pill at={pill} />
        {RAIL.map((item) => {
          const active = view === item.id
          const lit = active || hover === item.id
          return (
            <button
              key={item.id}
              ref={row(item.id)}
              type="button"
              onClick={() => onView(item.id)}
              onMouseEnter={() => enter(item.id)}
              aria-current={active}
              aria-label={item.label}
              title={item.label}
              className={`relative flex h-[34px] w-full items-center justify-center rounded-control transition-colors duration-150 ${
                lit ? 'text-ink' : 'text-ink-dim'
              }`}
            >
              <svg
                viewBox={item.viewBox}
                aria-hidden
                className="h-[16px] w-[16px] shrink-0"
                style={item.fill
                  ? { fill: 'currentColor' }
                  : { fill: 'none', stroke: 'currentColor', strokeWidth: 1.6 }}
              >
                <path d={item.d} />
              </svg>
              {/* In the signature, like every other reading the interface
                  makes about itself (2026-09-17): it was in maintenance's
                  orange, which said "this belongs to Maintenance" when what
                  it counts is simply what is waiting. Top-right of the icon
                  now the row is a square, and it never moves the icon. */}
              {badges?.[item.id] ? (
                <span
                  className="absolute right-[3px] top-[3px] min-w-[14px] rounded-full px-[3px] font-mono text-[9.5px] font-bold leading-[14px] text-ground"
                  style={{
                    background: 'var(--color-sig-5)',
                    // A ring in the ground the rail is painted on, so the
                    // badge reads as sitting beside the icon rather than
                    // cutting into it.
                    boxShadow: '0 0 0 2px var(--color-ground)',
                  }}
                >
                  {badges[item.id]}
                </span>
              ) : null}
            </button>
          )
        })}
      </div>
    </nav>
  )
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded-control border border-b-2 border-line bg-elevated px-[5px] py-[2px] font-mono text-[11px] text-ink-dim">
      {children}
    </kbd>
  )
}

/* A full-width strip for the macOS traffic lights.
 *
 * titleBarStyle:"Overlay" floats them over the content at the top-left, and
 * macOS will not move them to the right. Giving them their own band -- rather
 * than padding the rail out from under them -- is what lets the rail and the
 * main pane start at the same y, which is the only way their internal
 * dividers can line up without being hand-matched.
 *
 * data-tauri-drag-region makes it behave like a title bar: drag to move.
 */
export function TitleStrip() {
  return <div data-tauri-drag-region className="h-7 shrink-0" />
}

/* ---------------------------------------------------- status + characters */
function Meter({ pct, tone = 'var(--sig-meter)' }: { pct: number; tone?: string }) {
  return (
    <span className="mx-[3px] inline-block h-1 w-[30px] overflow-hidden rounded-sm bg-line align-[1px]">
      <span className="block h-full" style={{ width: `${pct}%`, background: tone }} />
    </span>
  )
}

/* Every element here is sourced from something real: cwd and model from
 * SessionStart, the two windows from rate_limit_event, sessions from the
 * manager, branch from git. Context % is the one exception -- it is not in
 * stream-json and is computed from token totals.
 *
 * Two rows were removed after review: an "auto mode on (shift-tab to cycle)"
 * line and artifact chips, both copied from a Claude Code terminal
 * screenshot. Neither has any meaning here -- there is no permission-mode
 * cycling in headless -p, and Noctis produces no artifacts -- and neither
 * appears in the spec's status-line list. A status bar that reports things
 * the app cannot know is worse than a shorter one. */
/** A model the engine is refusing right now, in its own words. */
export interface Refusal {
  model: string
  /** `claude-fable-5-1` as `Fable 5.1`. */
  label: string
  /** ISO 8601, from the transcript record. */
  at: string
  message: string
  session: string
}

export interface LiveLimits {
  five_hour: { used: number; resets_at: number }
  seven_day: { used: number; resets_at: number }
  /** What the windows above cannot say: a model can be out of usage credits
   *  while both windows sit at half, and on 2026-09-16 one was. */
  refused?: Refusal[]
  /** Unix seconds when this reading arrived at the backend. A hosted session
   *  only learns the windows from its own API responses, so an idle terminal
   *  repeats one figure while other sessions move the account on -- the age
   *  is what makes that read as stale rather than wrong. */
  reported_at?: number
}

/* Shown only past the plan's limits.
 *
 * This is the one number in the app that can mean money. Everything else --
 * tokens, list price, window percentages -- is either free or notional, and
 * an alert about any of those would train you to dismiss this one.
 *
 * A band rather than a modal: it must be impossible to miss and equally
 * impossible for it to stop you working, since you may well have decided the
 * overage is worth it.
 */
/* What the engine refused, in the engine's own words.
 *
 * The banner this replaced announced overage from a `using_overage` field
 * the status line has never sent, so it could not fire. On 2026-09-16 Fable
 * 5.1 returned 429 "You're out of usage credits" while the 7-day window read
 * 51% and the bar showed nothing: the windows are the subscription's, and a
 * model billed to credits is outside them. The message is quoted rather than
 * summarised, because it names the two commands that fix it.
 */
export function RefusedBanner({ refused, onDismiss }: { refused: Refusal; onDismiss: () => void }) {
  const at = new Date(refused.at)
  const when = Number.isNaN(at.valueOf())
    ? null
    : at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  return (
    <div
      role="status"
      className="flex shrink-0 items-center gap-[10px] border-b px-[14px] py-[7px] font-mono text-[11.5px]"
      style={{
        borderColor: 'color-mix(in srgb, var(--color-faber) 40%, var(--color-surface))',
        background: 'color-mix(in srgb, var(--color-faber) 12%, var(--color-surface))',
        color: 'var(--color-faber)',
      }}
    >
      <span aria-hidden>▲</span>
      <span className="min-w-0">
        <b className="font-semibold">{refused.label}</b> stopped answering
        {when ? ` at ${when}` : ''}: {refused.message}
      </span>
      <button
        type="button"
        onClick={onDismiss}
        className="ml-auto rounded-control px-[6px] py-px text-ink-faint transition-colors hover:bg-line hover:text-ink"
      >
        dismiss
      </button>
    </div>
  )
}

export interface BarState {
  /** Sessions running right now, and the concurrency budget. */
  live?: { running: number; max: number }
  cwd: string
  model: string
  /** Null while unknown, or when the directory is not a repository. */
  branch: string | null
  /** 0-1 of the context window, or null when the engine has not said. */
  context: number | null
}

/** A value that re-renders every second.
 *
 * The clock and the reset countdown both need it, and both were previously
 * frozen strings -- the bar showed 12:23 whatever the time was. One timer
 * for both, rather than two drifting a fraction of a second apart.
 */
function useTick(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

/** "3h44m" / "12m" / "now". Compact because it sits in a one-line bar.
 *
 * Relative rather than a clock time: the question it answers is how long
 * until you can work again, and a second absolute time next to the clock
 * would invite reading one as the other.
 */
function until(epochSeconds: number, now: number): string {
  const mins = Math.round((epochSeconds * 1000 - now) / 60000)
  if (mins <= 0) return 'now'
  if (mins < 60) return `${mins}m`
  return `${Math.floor(mins / 60)}h${String(mins % 60).padStart(2, '0')}m`
}

export function StatusBar({ limits, state }: { limits?: LiveLimits | null; state: BarState }) {
  const now = useTick()
  const clock = new Date(now).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', hour12: false,
  })
  const fiveHour = limits ? Math.round(limits.five_hour.used * 100) : null
  const sevenDay = limits ? Math.round(limits.seven_day.used * 100) : null
  const ctx = state.context === null ? null : Math.round(state.context * 100)

  return (
    <div className="flex min-w-0 flex-col gap-[2px] font-mono text-[10.5px] text-ink-faint">
      {/* Each row stays on one line. The cwd is the only variable-length
          item, so it is the one allowed to truncate -- everything else is
          short and fixed, and wrapping a status bar makes it read as
          content rather than furniture. */}
      <div className="flex min-w-0 items-center whitespace-nowrap">
        <Seg className="min-w-0 truncate text-ink-dim">{state.cwd}</Seg>
        {/* Omitted rather than shown empty when the directory is not a
            repository, which plenty of useful directories are not. */}
        {state.branch && <Seg className="text-ink-dim">⎇ {state.branch}</Seg>}
        <Seg>{state.model}</Seg>
        <Seg last>{clock}</Seg>
      </div>
      {/* min-w-0 so the row may shrink, and the segments hold their own
          width — without it the row overflowed its cell and the last item
          was cut mid-word ("0/2 l"). The cwd on the row above is the only
          thing allowed to truncate; a number cut in half is not a smaller
          number, it is a wrong one. */}
      <div className="flex min-w-0 items-center whitespace-nowrap">
        {/* A dash, not 0%: unknown and empty are different, and an invented
            0% reads as a conversation with room to spare. */}
        <Seg className={ctx === null ? '' : 'text-[var(--sig-text)]'}>
          ctx {ctx === null ? '—' : <><Meter pct={ctx} /> {ctx}%</>}
        </Seg>
        <Seg>
          5h{' '}
          {fiveHour === null ? '—' : (
            <>
              <Meter pct={fiveHour} /> {fiveHour}%
              {/* The reset is on the 5h window only. It is the one that
                  actually blocks you inside a working day; the 7d window
                  resets on a horizon no decision turns on. */}
              <span className="ml-[5px] text-ink-faint">↻ {until(limits!.five_hour.resets_at, now)}</span>
              {/* How old the reading is, once it is old enough to matter. A
                  hosted session only learns these from its own API responses,
                  so a terminal sitting at its prompt repeats one figure while
                  other sessions move the account on. Shown from a minute, so
                  a fresh reading is just a number and a stale one says so. */}
              {limits!.reported_at != null && now / 1000 - limits!.reported_at >= 60 && (
                <span className="ml-[5px] text-ink-faint">
                  · {Math.floor((now / 1000 - limits!.reported_at) / 60)}m ago
                </span>
              )}
            </>
          )}
        </Seg>
        <Seg last>
          7d {sevenDay === null ? '—' : <><Meter pct={sevenDay} /> {sevenDay}%</>}
        </Seg>
      </div>
    </div>
  )
}

export function BottomBar({
  children,
  limits,
  state,
  open,
}: {
  children: React.ReactNode
  limits?: LiveLimits | null
  state: BarState
  /** Modes with a conversation open. */
  open?: Mode[]
}) {
  return (
    /* One band, one rule. This used to be two rows on the main side -- a
       composer row and, under a second rule, the status row -- with the
       rail-width cell spanning both, so the cell's top edge sat a row above
       the status row's and the composer's row stayed as an empty band after
       the composer went with the orchestrator. The strip at the top is the
       rail's title band's height; this is the status band's, and the cell,
       the readings and the characters share it. */
    <div className="flex h-[var(--status-band)] shrink-0 items-center border-t border-line">
      {/* The bar runs the window's full width now (2026-09-15): the rail-width
          cell that held the two key hints made the bar read as two bars, and
          the hints belong with the other glanceable things on the right. */}
      <div className="flex min-w-0 flex-1 items-center gap-4 px-[14px]">
        <div className="flex min-w-0 overflow-hidden">
          <StatusBar limits={limits} state={state} />
        </div>
        {children}
        <div className="ml-auto flex shrink-0 items-center gap-[18px]">
          <span className="flex items-center gap-[7px] font-mono text-[11px] text-ink-faint">
            <Kbd>⌘T</Kbd> new · <Kbd>⌘K</Kbd> search
          </span>
          <CharacterStrip open={open} live={state.live} />
        </div>
      </div>
    </div>
  )
}


/* One status segment. `shrink-0` by default: these are short, fixed strings
 * and a truncated one reads as a different value rather than a shorter one.
 * The cwd passes `min-w-0 truncate` to opt out, because it is the only item
 * here whose length is unbounded. */
function Seg({ children, last, className = '' }: { children: React.ReactNode; last?: boolean; className?: string }) {
  return (
    <span className={`shrink-0 ${last ? '' : 'mr-[9px] border-r border-line pr-[9px]'} ${className}`}>
      {children}
    </span>
  )
}

/* The characters sit here rather than in a bar of their own: with the pixel
 * world retired they are status indicators, and a full-width strip cost
 * ~54px of permanent vertical space to say what a dot can. */
/* The three mode characters, drawn rather than lettered.
 *
 * Real pixel sprites, reachable at /assets because public/assets is a
 * symlink to assets/, which is how the vault stays their single source of
 * truth. One sprite each: "working" was a variant the `-p` orchestrator lit
 * while a turn streamed, and a terminal session does not report that, so
 * the variants went with it. The dot beside the sprite carries state. */
export const SPRITE: Record<Mode, string | null> = {
  general: null,          // the front door has no character; it is you
  faber: '/assets/characters/faber.png',
  noctua: '/assets/characters/expressions/noctua-sleepy.png',
  vesper: '/assets/characters/expressions/vesper-drowsy.png',
  maintenance: null,      // its character was retired with the persona
}

/* A mode's mark where a tab or a chip needs one: the character's sprite,
 * or for General -- which has no character, it is you -- the Noctis star.
 * Maintenance has neither and keeps its dot. The same mark in the tab strip
 * and in the Repo view's terminal chips, so a terminal is recognisable by
 * the same picture in both places. */
export function ModeMark({ mode, size = 14, dim = false }: { mode: Mode; size?: number; dim?: boolean }) {
  if (mode === 'general') {
    return <Logo size={size - 2} className="shrink-0" style={{ color: dim ? 'var(--color-ink-faint)' : 'var(--color-ink-dim)' }} />
  }
  const src = SPRITE[mode]
  if (!src) {
    return <span className="rounded-[2px]" style={{ width: 7, height: 7, background: MODE_ACCENT[mode] }} />
  }
  return (
    <img src={src} alt="" width={size} height={size} className="shrink-0 object-contain"
         style={{ imageRendering: 'pixelated', opacity: dim ? 0.6 : 1 }} />
  )
}

function CharacterStrip({
  open = [],
  live,
}: {
  /** Modes with a conversation you could go back to. */
  open?: Mode[]
  /** Terminals open now, and the ceiling. */
  live?: { running: number; max: number }
}) {
  return (
    <div className="flex shrink-0 items-center gap-[10px]">
      {/* The budget only means something when it is being spent, so it
          appears only while something is open. Amber at the cap. */}
      {live && live.running > 0 && (
        <span
          className="font-mono text-[10.5px] tabular-nums"
          style={{
            color: live.running >= live.max ? 'var(--color-noctua)' : 'var(--color-ink-faint)',
          }}
          title={`${live.running} of ${live.max} terminals open`}
        >
          {live.running}/{live.max}
        </span>
      )}
      {CHARACTERS.map((c) => {
        const accent = MODE_ACCENT[c.mode]
        const hasSession = open.includes(c.mode)
        const sprite = SPRITE[c.mode]
        return (
          <button
            key={c.mode}
            type="button"
            title={`${MODE_LABEL[c.mode]} · ${hasSession ? 'open' : 'idle'}`}
            className="group relative grid h-6 w-6 place-items-center rounded-control hover:bg-elevated"
          >
            {sprite ? (
              <img
                src={sprite}
                alt=""
                /* pixelated, or the browser smooths a 16-grade sprite into
                   mush at this size -- the whole point of the art direction
                   is hard edges. Dimmed rather than greyed, so the character
                   stays itself. */
                className="h-[20px] w-[20px] object-contain transition-opacity"
                style={{ imageRendering: 'pixelated', opacity: hasSession ? 0.8 : 0.45 }}
              />
            ) : (
              <span
                className="font-mono text-[11px] font-bold"
                style={{ color: hasSession ? accent : 'var(--color-ink-faint)', opacity: hasSession ? 0.8 : 0.55 }}
              >
                {MODE_LABEL[c.mode][0]}
              </span>
            )}
            {/* A steady accent dot for an open conversation: present, not
                animated, because motion that never stops stops meaning
                anything. */}
            <span
              className="absolute -bottom-px -right-px h-[6px] w-[6px] rounded-full border-[1.5px] border-surface"
              style={{ background: hasSession ? accent : 'var(--color-ink-faint)', opacity: hasSession ? 0.7 : 1 }}
            />
          </button>
        )
      })}
    </div>
  )
}

