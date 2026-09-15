/* Rail, title strip, status bar, characters — the shell around the terminals. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Logo } from './Logo'
import { CHARACTERS, MODE_ACCENT, MODE_LABEL, type Mode } from './domain'

/* ------------------------------------------------------------------ rail */
const RAIL = [
  // Everything that arrived while you were away: the digest of what
  // happened, then what is waiting on a decision. First, because it is
  // what you open the app to read. (It absorbed the Brief tab 2026-09-15.)
  { id: 'inbox', label: 'Inbox', d: 'M4 13h5l1 3h4l1-3h5M4 13l2-8h12l2 8v6H4z' },
  // The conversation surface: the real CLI, hosted in a pseudo-terminal.
  { id: 'terminal', label: 'Terminal', d: 'M4 4h16v16H4zM7 9l3 3-3 3M13 15h4' },
  // The repositories the open terminals are in, grouped: local truth, GitHub beside it.
  { id: 'repo', label: 'Repo', d: 'M6 3v12M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9' },
  { id: 'stats', label: 'Stats', d: 'M4 20V10M10 20V4M16 20v-7M22 20H2' },
  { id: 'settings', label: 'Settings', d: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.5 19.4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3.6 14H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 3.6V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z' },
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
    const target = key ? rows.current[key] : null
    const box = list.current
    if (!target || !box) { setPill(null); return }
    const t = target.getBoundingClientRect(), b = box.getBoundingClientRect()
    setPill({ top: t.top - b.top, left: t.left - b.left, width: t.width, height: t.height })
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
    <nav className="flex w-[160px] shrink-0 flex-col border-r border-line">
      {/* Mark and wordmark centred together. The star takes the active
          mode's accent via currentColor, so the identity shifts with the
          session rather than sitting inert above a UI that changes. */}
      {/* Height comes from --head-band, shared with the tab bar beside it,
          so the two bottom rules meet and the header reads as one band
          split by the rail rather than two boxes of different sizes. */}
      <div className="flex h-[var(--head-band)] shrink-0 items-center justify-center gap-[7px] border-b border-line px-[12px]">
        <Logo size={15} className="shrink-0" style={{ color: 'var(--accent)' }} />
        <span className="font-mono text-[12px] font-bold uppercase tracking-[0.14em]">Noctis</span>
      </div>

      <div className="h-[10px] shrink-0" />

      {/* The rows keep icon-then-label, left-aligned; the block of rows is
          what sits in the middle of the rail. */}
      <div ref={list} className="relative mx-auto flex w-[124px] flex-col gap-[2px]" onMouseLeave={leave}>
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
              className={`relative flex w-full items-center gap-[9px] rounded-control px-[12px] py-[7px] text-[12.5px] transition-colors duration-150 ${
                lit ? 'text-ink' : 'text-ink-dim'
              }`}
            >
              <svg viewBox="0 0 24 24" aria-hidden className="h-[15px] w-[15px] shrink-0" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.6 }}>
                <path d={item.d} />
              </svg>
              {item.label}
              {badges?.[item.id] ? (
                <span className="rounded-full bg-maint px-[6px] font-mono text-[10px] font-bold text-ground">
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
export interface LiveLimits {
  five_hour: { used: number; resets_at: number }
  seven_day: { used: number; resets_at: number }
  using_overage?: boolean
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
export function OverageBanner({ onDismiss }: { onDismiss: () => void }) {
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
      <span>
        Past your plan's included usage — sessions from here may be billed as overage.
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

