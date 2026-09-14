/* Rail, title strip, status bar, characters — the shell around the terminals. */
import { useEffect, useState } from 'react'
import { Logo } from './Logo'
import { CHARACTERS, MODE_ACCENT, MODE_LABEL, type Mode } from './domain'

/* ------------------------------------------------------------------ rail */
const RAIL = [
  { id: 'brief', label: 'Brief', d: 'M4 5h16M4 12h16M4 19h10' },
  // The conversation surface: the real CLI, hosted in a pseudo-terminal.
  { id: 'terminal', label: 'Terminal', d: 'M4 4h16v16H4zM7 9l3 3-3 3M13 15h4' },
  // The repositories the open terminals are in, grouped: local truth, GitHub beside it.
  { id: 'repo', label: 'Repo', d: 'M6 3v12M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9a9 9 0 0 1-9 9' },
  { id: 'stats', label: 'Stats', d: 'M4 20V10M10 20V4M16 20v-7M22 20H2' },
  { id: 'inbox', label: 'Inbox', d: 'M4 13h5l1 3h4l1-3h5M4 13l2-8h12l2 8v6H4z' },
  { id: 'settings', label: 'Settings', d: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.5 19.4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3.6 14H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 3.6V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z' },
] as const

export function Rail({ view, onView, badges }: {
  view: string
  onView: (v: string) => void
  /** Counts worth a glance, by rail item id. The inbox's is what is
   *  actually waiting on a decision -- it was a literal 3 in this file for
   *  weeks, which is a badge that says nothing. */
  badges?: Partial<Record<string, number>>
}) {
  // pt-7 clears the macOS traffic lights, which titleBarStyle:"Overlay"
  // floats over the content at the top-left. They cannot be moved to the
  // right on macOS, so the rail moves out from under them instead.
  return (
    <nav className="flex w-[160px] shrink-0 flex-col border-r border-line bg-surface">
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

      {RAIL.map((item) => {
        const active = view === item.id
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onView(item.id)}
            aria-current={active}
            className={`flex w-full items-center gap-[9px] border-l-2 px-[12px] py-[7px] text-left text-[12.5px] ${
              active
                ? 'border-l-[var(--accent)] bg-elevated text-ink'
                : 'border-l-transparent text-ink-dim hover:bg-elevated hover:text-ink'
            }`}
          >
            <svg viewBox="0 0 24 24" aria-hidden className="h-[15px] w-[15px] shrink-0" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.6 }}>
              <path d={item.d} />
            </svg>
            {item.label}
            {badges?.[item.id] ? (
              <span className="ml-auto rounded-lg bg-maint px-[6px] font-mono text-[10px] font-bold text-ground">
                {badges[item.id]}
              </span>
            ) : null}
          </button>
        )
      })}
    </nav>
  )
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded-[3px] border border-b-2 border-line bg-elevated px-[5px] py-[2px] font-mono text-[11px] text-ink-dim">
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
  return <div data-tauri-drag-region className="h-7 shrink-0 bg-surface" />
}

/* ---------------------------------------------------- status + characters */
function Meter({ pct, tone = 'var(--color-good)' }: { pct: number; tone?: string }) {
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
        className="ml-auto rounded-[3px] px-[6px] py-px text-ink-faint transition-colors hover:bg-line hover:text-ink"
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
        <Seg className={ctx === null ? '' : 'text-noctua'}>
          ctx {ctx === null ? '—' : <><Meter pct={ctx} tone="var(--color-noctua)" /> {ctx}%</>}
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
  working,
  open,
}: {
  children: React.ReactNode
  limits?: LiveLimits | null
  state: BarState
  /** Modes with a turn in flight right now. */
  working?: Mode[]
  /** Modes with a conversation open, streaming or not. */
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
    <div className="flex h-[var(--status-band)] shrink-0 items-center border-t border-line bg-surface">
      {/* Rail-width cell, always present. It was previously only rendered in
          the narrow layout, so the permission hint vanished on a wide window
          -- the same "hidden rather than moved" mistake as before. */}
      <div className="flex h-full w-[160px] shrink-0 items-center gap-[7px] border-r border-line px-[12px] font-mono text-[11px] text-ink-faint">
        <Kbd>⌘T</Kbd> new · <Kbd>⌘K</Kbd> search
      </div>
      <div className="flex min-w-0 flex-1 items-center gap-4 px-[14px]">
        <div className="flex min-w-0 overflow-hidden">
          <StatusBar limits={limits} state={state} />
        </div>
        {children}
        <div className="ml-auto flex shrink-0">
          <CharacterStrip working={working} open={open} live={state.live} />
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
 * These were F/N/V initials standing in for artwork that already existed —
 * real pixel sprites have been sitting in assets/characters since July,
 * reachable at /assets because public/assets is a symlink to them, which is
 * how the vault stays their single source of truth.
 *
 * State is carried by the sprite itself, not only by a dot beside it: each
 * character has expression variants, so an idle Noctua is the sleepy one and
 * a working Faber is the one holding tools. The dot stays as the
 * unambiguous signal, because a drowsy owl is a charming way to say "idle"
 * and a poor way to be *sure*.
 */
export const SPRITE: Record<Mode, { idle: string; working: string } | null> = {
  general: null,          // the front door has no character; it is you
  faber: { idle: '/assets/characters/faber.png',
           working: '/assets/characters/expressions/faber-building.png' },
  noctua: { idle: '/assets/characters/expressions/noctua-sleepy.png',
            working: '/assets/characters/noctua.png' },
  vesper: { idle: '/assets/characters/expressions/vesper-drowsy.png',
            working: '/assets/characters/expressions/vesper-alert.png' },
  maintenance: null,      // its character was retired with the persona
}

/* A mode's mark where a tab or a chip needs one: the character's sprite,
 * or for General -- which has no character, it is you -- the Noctis star.
 * Maintenance has neither and keeps its dot. The same mark in the tab strip
 * and in the Repo view's terminal chips, so a terminal is recognisable by
 * the same picture in both places. */
export function ModeMark({ mode, size = 14, dim = false }: { mode: Mode; size?: number; dim?: boolean }) {
  const src = mode === 'general' ? '/favicon.svg' : SPRITE[mode]?.idle
  if (!src) {
    return <span className="rounded-[2px]" style={{ width: 7, height: 7, background: MODE_ACCENT[mode] }} />
  }
  return (
    <img src={src} alt="" width={size} height={size} className="shrink-0 object-contain"
         style={{ imageRendering: mode === 'general' ? 'auto' : 'pixelated', opacity: dim ? 0.6 : 1 }} />
  )
}

function CharacterStrip({
  working = [],
  open = [],
  live,
}: {
  /** Modes with a turn streaming this instant. */
  working?: Mode[]
  /** Modes with a conversation you could go back to. */
  open?: Mode[]
  /** Turns in flight now, and the budget. */
  live?: { running: number; max: number }
}) {
  return (
    <div className="flex shrink-0 items-center gap-[10px]">
      {/* Only while something is actually in flight.
   *
   * It used to render always, which meant it said "0/2" essentially every
   * time you looked at it: a turn is a separate `claude -p` process that
   * exits when the reply ends, so nothing is running in any moment you are
   * reading the screen. Sitting beside three idle-looking characters it read
   * as "you have no sessions" while three conversations were open.
   *
   * The budget only means something when it is being spent, so it appears
   * then. Amber at the cap, when the next turn queues instead of running. */}
      {live && live.running > 0 && (
        <span
          className="font-mono text-[10.5px] tabular-nums"
          style={{
            color: live.running >= live.max ? 'var(--color-noctua)' : 'var(--color-ink-faint)',
          }}
          title={`${live.running} of ${live.max} turns running`}
        >
          {live.running}/{live.max}
        </span>
      )}
      {CHARACTERS.map((c) => {
        const accent = MODE_ACCENT[c.mode]
        /* Three states, not two.
         *
         * `working` is a turn streaming right now, which is true for seconds
         * at a time. `open` is a conversation that exists and can be resumed,
         * which is the fact you actually want at a glance -- and the one the
         * strip could not previously show, so a mode you were mid-session in
         * looked exactly like one you had never opened. */
        const busy = working.includes(c.mode)
        const hasSession = busy || open.includes(c.mode)
        const sprite = SPRITE[c.mode]
        return (
          <button
            key={c.mode}
            type="button"
            title={`${MODE_LABEL[c.mode]} · ${busy ? 'working' : hasSession ? 'open' : 'idle'}`}
            className="group relative grid h-6 w-6 place-items-center rounded-[3px] hover:bg-elevated"
          >
            {sprite ? (
              <img
                src={busy ? sprite.working : sprite.idle}
                alt=""
                /* pixelated, or the browser smooths a 16-grade sprite into
                   mush at this size — the whole point of the art direction
                   is hard edges. Dimmed rather than greyed, so the character
                   stays itself; an open conversation sits between the two. */
                className="h-[20px] w-[20px] object-contain transition-opacity"
                style={{ imageRendering: 'pixelated', opacity: busy ? 1 : hasSession ? 0.8 : 0.45 }}
              />
            ) : (
              <span
                className="font-mono text-[11px] font-bold"
                style={{
                  color: hasSession ? accent : 'var(--color-ink-faint)',
                  opacity: busy ? 1 : hasSession ? 0.8 : 0.55,
                }}
              >
                {MODE_LABEL[c.mode][0]}
              </span>
            )}
            {/* Pulses only while a turn is streaming. An open conversation is
                a steady accent dot: present, not animated, because motion
                that never stops stops meaning anything. */}
            <span
              className={`absolute -bottom-px -right-px h-[6px] w-[6px] rounded-full border-[1.5px] border-surface ${busy ? 'animate-pulse motion-reduce:animate-none' : ''}`}
              style={{
                background: hasSession ? accent : 'var(--color-ink-faint)',
                opacity: busy ? 1 : hasSession ? 0.7 : 1,
              }}
            />
          </button>
        )
      })}
    </div>
  )
}

