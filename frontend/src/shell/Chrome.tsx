/* Rail, tabs, composer, status, characters — the shell around the transcript. */
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { Logo } from './Logo'
import {
  CHARACTERS, MODE_ACCENT, MODE_LABEL, PERMISSION_LABEL, PERMISSION_TONE, STATUS,
  type Mode, type Permission, type Tab,
} from './mock'

/* ------------------------------------------------------------------ rail */
const RAIL = [
  { id: 'brief', label: 'Brief', d: 'M4 5h16M4 12h16M4 19h10' },
  { id: 'chat', label: 'Chat', d: 'M20 15a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2z' },
  { id: 'stats', label: 'Stats', d: 'M4 20V10M10 20V4M16 20v-7M22 20H2' },
  { id: 'inbox', label: 'Inbox', d: 'M4 13h5l1 3h4l1-3h5M4 13l2-8h12l2 8v6H4z', badge: 3 },
  { id: 'settings', label: 'Settings', d: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.5 19.4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3.6 14H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 3.6V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z' },
] as const

export function Rail({ view, onView }: { view: string; onView: (v: string) => void }) {
  // pt-7 clears the macOS traffic lights, which titleBarStyle:"Overlay"
  // floats over the content at the top-left. They cannot be moved to the
  // right on macOS, so the rail moves out from under them instead.
  return (
    <nav className="flex w-[160px] shrink-0 flex-col border-r border-line bg-surface">
      {/* Mark and wordmark centred together. The star takes the active
          mode's accent via currentColor, so the identity shifts with the
          session rather than sitting inert above a UI that changes. */}
      {/* h-[34px] is the tab bar's height. Matching them makes the rail's
          divider continue the tab bar's, so the two panes read as one
          surface split rather than two boxes side by side. */}
      <div className="flex h-[34px] shrink-0 items-center justify-center gap-[7px] border-b border-line px-[12px]">
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
            {'badge' in item && item.badge ? (
              <span className="ml-auto rounded-lg bg-maint px-[6px] font-mono text-[10px] font-bold text-ground">
                {item.badge}
              </span>
            ) : null}
          </button>
        )
      })}

      {/* The tab numbers live on the tabs, where there is room for them. This
          one does not: the permission chip already carries a word-length
          label, so a badge beside it was present without being legible.
          Sized to be read rather than merely shown. */}
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

/* ------------------------------------------------------------------ tabs */
/* Each tab shows the key that reaches it, rather than a legend elsewhere
 * listing them. A shortcut printed on the thing it operates is discovered
 * while you use it; a legend has to be remembered and read, which is the
 * same "UI explaining itself" pattern as placeholder instructions. */
export function TabBar({
  tabs,
  active,
  onSelect,
}: {
  tabs: Tab[]
  active: string
  onSelect: (id: string) => void
}) {
  return (
    <div role="tablist" className="flex h-[34px] shrink-0 items-stretch border-b border-line bg-surface">
      {tabs.map((t, i) => {
        const selected = t.id === active
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={selected}
            onClick={() => onSelect(t.id)}
            className={`relative flex h-full items-center gap-[7px] border-r border-line px-[14px] font-mono text-[11.5px] ${
              selected ? 'bg-ground text-ink' : 'text-ink-faint hover:text-ink-dim'
            }`}
          >
            {selected && (
              <span className="absolute inset-x-0 top-0 h-[2px]" style={{ background: MODE_ACCENT[t.mode] }} />
            )}
            {t.pinned && <span className="text-[9px] text-ink-faint">◆</span>}
            {!t.pinned && (
              <span className="h-[7px] w-[7px] rounded-[1px]" style={{ background: MODE_ACCENT[t.mode] }} />
            )}
            {t.label}
            {i < 3 && (
              <span className="ml-[3px] rounded-[2px] border border-line px-[3px] text-[9px] leading-[13px] text-ink-faint">
                ⌘{i + 1}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/* -------------------------------------------------------------- composer */
export const Composer = forwardRef<HTMLTextAreaElement, {
  mode: Mode
  value: string
  onChange: (v: string) => void
  onSend: () => void
  permission: Permission
  onCyclePermission: () => void
}>(function Composer({ mode, value, onChange, onSend, permission, onCyclePermission }, forwarded) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useImperativeHandle(forwarded, () => ref.current as HTMLTextAreaElement)

  // Grow to a cap, then scroll. Done here rather than with CSS because a
  // textarea cannot size to its content without measuring it.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [value])

  const accent = MODE_ACCENT[mode]
  // The composer keeps its own width (aligned to the transcript's text
  // column); BottomBar centres it and fills the space either side.
  return (
    <div className="w-[776px] max-w-full">
      <div className="flex items-start gap-[9px] rounded-[4px] border border-line bg-ground px-[10px] py-[7px] focus-within:border-[#3a3a3a]">
        <span
          className="flex shrink-0 self-start items-center gap-[5px] rounded-[3px] border px-[7px] py-[2px] font-mono text-[10.5px] uppercase leading-[1.5] tracking-[0.06em]"
          // Mixed toward the ground colour, not toward `transparent`.
          // Mixing to transparent in srgb is unreliable across engines --
          // WebKit returned near-opaque, which is what made the selection
          // paint solid red. Mixing between two opaque colours is
          // well-defined everywhere and gives the same result on this ground.
          style={{
            color: accent,
            borderColor: `color-mix(in srgb, ${accent} 34%, var(--color-ground))`,
            background: `color-mix(in srgb, ${accent} 11%, var(--color-ground))`,
          }}
        >
          {MODE_LABEL[mode]}
        </span>

        {/* Sets --permission-mode on the next spawn. Unlike the CLI's own
            shift-tab, this applies to the next turn rather than mid-turn --
            each `claude -p` is a fresh process, so there is nothing running
            to re-permission. */}
        <button
          type="button"
          onClick={onCyclePermission}
          title={`Permission: ${PERMISSION_LABEL[permission]} — ⇧⇥ to cycle`}
          className="flex shrink-0 self-start items-center gap-[5px] rounded-[3px] border border-line px-[7px] py-[2px] font-mono text-[10.5px] leading-[1.5] hover:border-[#3a3a3a]"
          style={{ color: PERMISSION_TONE[permission] }}
        >
          <span className="text-[8px]">▶▶</span>
          {PERMISSION_LABEL[permission]}
        </button>

        {/* A persistent prompt glyph rather than placeholder text. A
            placeholder disappears the moment you type, so it can only ever
            label an empty field; the prompt stays, which is what makes a
            terminal read as a terminal. Dimmed and unselectable so it never
            gets caught in a drag-select of the line. */}
        <span
          aria-hidden
          className="shrink-0 select-none self-start font-mono text-[12.5px] leading-[21px] text-ink-faint"
        >
          ›
        </span>

        {/* Still a real text field: click to place the caret anywhere, drag
            to select, standard undo -- the CLI's input cannot do any of it. */}
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              if (value.trim()) onSend()
            }
          }}
          rows={1}
          spellCheck={false}
          aria-label="Message"
          className="max-h-[160px] min-h-[21px] flex-1 resize-none border-0 bg-transparent font-mono text-[12.5px] leading-[21px] text-ink outline-none"
          style={{ caretColor: accent }}
        />

        <span className="flex shrink-0 items-center gap-[6px] self-end">
          <IconButton title="Attach" d="M21 11l-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8" />
          <IconButton title="Send" d="M4 12h15M13 6l6 6-6 6" onClick={() => value.trim() && onSend()} />
        </span>
      </div>

    </div>
  )
})

function IconButton({ title, d, onClick }: { title: string; d: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      className="grid h-[21px] w-[21px] place-items-center rounded-[3px] border border-line text-ink-faint hover:border-[#3a3a3a] hover:text-ink"
    >
      <svg viewBox="0 0 24 24" aria-hidden className="h-3 w-3" style={{ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8 }}>
        <path d={d} />
      </svg>
    </button>
  )
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
export function StatusBar() {
  const s = STATUS
  return (
    <div className="flex min-w-0 flex-col gap-[2px] font-mono text-[10.5px] text-ink-faint">
      {/* Each row stays on one line. The cwd is the only variable-length
          item, so it is the one allowed to truncate -- everything else is
          short and fixed, and wrapping a status bar makes it read as
          content rather than furniture. */}
      <div className="flex min-w-0 items-center whitespace-nowrap">
        <Seg className="min-w-0 truncate text-ink-dim">{s.cwd}</Seg>
        <Seg className="text-ink-dim">⎇ {s.branch}</Seg>
        <Seg>{s.model}</Seg>
        <Seg last>{s.clock}</Seg>
      </div>
      <div className="flex items-center whitespace-nowrap">
        <Seg className="text-noctua">
          ctx <Meter pct={s.contextPct} tone="var(--color-noctua)" /> {s.contextPct}%
        </Seg>
        <Seg>
          5h <Meter pct={s.fiveHourPct} /> {s.fiveHourPct}%
        </Seg>
        <Seg last>
          7d <Meter pct={s.sevenDayPct} /> {s.sevenDayPct}%
        </Seg>
      </div>
    </div>
  )
}

/* The bottom bar adapts rather than hides.
 *
 * Wide enough (past 1620px: 160 rail + 776 composer leaves ~340 a side) and
 * the status and characters sit either side of the input, costing one band.
 * Narrower, they drop to their own row beneath it, costing two.
 *
 * The earlier version simply hid them below the breakpoint, which traded an
 * overlap for an absence -- worse, because the quota numbers are the ones
 * that govern whether to start another session. Information that matters at
 * every width should move when it does not fit, not vanish. */
export function BottomBar({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex shrink-0 border-t border-line bg-surface">
      {/* Rail-width cell, always present. It was previously only rendered in
          the narrow layout, so the permission hint vanished on a wide window
          -- the same "hidden rather than moved" mistake as before. */}
      <div className="flex w-[160px] shrink-0 items-center gap-[7px] border-r border-line px-[12px] font-mono text-[11px] text-ink-faint">
        <Kbd>⇧⇥</Kbd> permission
      </div>

      {/* Everything else lives inside the main pane's width, not the
          window's. Centring the composer across the whole window put it out
          of line with the transcript above, which is centred in the pane. */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 px-[14px] py-[10px]">
          <div className="hidden min-w-0 justify-self-start overflow-hidden min-[1620px]:flex">
            <StatusBar />
          </div>
          {children}
          <div className="hidden justify-self-end min-[1620px]:flex">
            <CharacterStrip />
          </div>
        </div>

        {/* Same components, second position -- rendered twice rather than
            moved with JS, since only one is ever displayed. */}
        <div className="flex h-[var(--status-band)] items-center gap-4 border-t border-line px-[14px] min-[1620px]:hidden">
          <StatusBar />
          <div className="ml-auto">
            <CharacterStrip />
          </div>
        </div>
      </div>
    </div>
  )
}

function Seg({ children, last, className = '' }: { children: React.ReactNode; last?: boolean; className?: string }) {
  return (
    <span className={`${last ? '' : 'mr-[9px] shrink-0 border-r border-line pr-[9px]'} ${className}`}>
      {children}
    </span>
  )
}

/* The characters sit here rather than in a bar of their own: with the pixel
 * world retired they are status indicators, and a full-width strip cost
 * ~54px of permanent vertical space to say what a dot can. */
function CharacterStrip() {
  return (
    <div className="flex shrink-0 items-center gap-[10px]">
      {CHARACTERS.map((c) => {
        const accent = MODE_ACCENT[c.mode]
        const live = c.state === 'working'
        return (
          <button
            key={c.mode}
            type="button"
            title={`${MODE_LABEL[c.mode]} · ${c.state}`}
            className="group relative grid h-6 w-6 place-items-center rounded-[3px] hover:bg-elevated"
          >
            <span
              className="font-mono text-[11px] font-bold"
              style={{ color: live ? accent : 'var(--color-ink-faint)', opacity: live ? 1 : 0.55 }}
            >
              {MODE_LABEL[c.mode][0]}
            </span>
            <span
              className={`absolute -bottom-px -right-px h-[6px] w-[6px] rounded-full border-[1.5px] border-surface ${live ? 'animate-pulse' : ''}`}
              style={{ background: live ? accent : 'var(--color-ink-faint)' }}
            />
          </button>
        )
      })}
    </div>
  )
}
