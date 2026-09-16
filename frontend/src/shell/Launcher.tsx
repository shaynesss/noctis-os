/* Mode entry and handoff — Stage 2 item 3.
 *
 * One component for both, because they are the same decision: which mode
 * runs next, in which directory, on what prompt. Handoff only adds a
 * provenance strip and a carried summary. Building them as two dialogs would
 * have meant maintaining two versions of the same keyboard model.
 *
 * **Why handoff opens a new session rather than switching a live one.** Each
 * mode has its own CLAUDE_CONFIG_DIR, model and tool policy, and a running
 * `claude -p` process cannot change any of them mid-flight. So the mechanic
 * is a spawn, not a mutation -- which is also how dev.md describes the mode
 * boundary: Faber *consumes* Vesper's verdict. Two artifacts, not one that
 * quietly became the other.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { ModeMark } from './Chrome'
import { useFetched } from './useFetched'
import { MODE_ACCENT, MODE_INFO, MODE_LABEL, type Mode } from './domain'

/* How hard the session thinks, chosen before it starts rather than typed as
 * `/effort` once it is already running. The levels are the CLI's own; the
 * chooser opens on what this mode's model is configured to do, so leaving it
 * alone sends an override identical to the default and changes nothing. */
const EFFORTS = ['low', 'medium', 'high', 'xhigh', 'max'] as const
export type Effort = (typeof EFFORTS)[number]

/* Maintenance is deliberately absent.
 *
 * It is the overnight auditor: the scheduler wakes it, it reads lessons
 * files and stages proposals, and the thing you interact with is its output
 * in the Inbox. Offering it here invited you to sit and chat with an
 * auditor, which is not a session anyone wants. Its config dir stays, so
 * the scheduler can still run it. */
const MODES: Mode[] = ['general', 'faber', 'noctua', 'vesper']

export interface LaunchRequest {
  mode: Mode
  cwd: string
  /** Omitted when the mode's configured level was left alone. */
  effort?: Effort
  /** Set when this launch came from a handoff, for the provenance block. */
  from?: { mode: Mode; label: string; carried: string }
}

export function Launcher({
  handoff,
  full,
  onLaunch,
  onClose,
}: {
  /** Present when handing off: the source session and what it carries. */
  handoff?: { mode: Mode; label: string; cwd: string; carried: string }
  /** Set when every terminal slot is taken: the reason nothing can start.
   *  Shown in place of the hint, and the button is disabled, because the
   *  ceiling is real (⌘1–9 and the backend's concurrency cap) and a Start
   *  that silently did nothing is the failure this launcher already fixed
   *  once for the empty prompt. */
  full?: string
  onLaunch: (req: LaunchRequest) => void
  onClose: () => void
}) {
  // A handoff never targets its own source mode -- that is a continuation,
  // not a handoff, and offering it would invite a session that spawns a
  // duplicate of itself for no reason.
  const choices = handoff ? MODES.filter((m) => m !== handoff.mode) : MODES

  const [mode, setMode] = useState<Mode>(choices[0])
  /* Directories from real session history, not a hardcoded list. The old
   * one named the same three whether or not you had ever opened them, and
   * never learned a project you started using. */
  const recents = useFetched<{ dirs: string[] }>('/v2/recent-dirs')
  const dirs = useMemo(() => (recents ? recents.dirs : []), [recents])

  /* Where each mode starts. The vault-native modes belong at the vault
   * root; a build session belongs in a repo. The default used to be
   * whichever directory was used last regardless of mode, which put a
   * Noctua session in the home folder — nobody's sensible starting point,
   * and the reason it opened by remarking on where it was. */
  const defaults = useFetched<{ dirs: Record<string, string>; effort: Record<string, Effort | null> }>('/v2/mode-defaults')
  const [cwd, setCwd] = useState(handoff?.cwd ?? '')
  const [touched, setTouched] = useState(false)

  /* Follows the mode until you type. A handoff keeps its source directory —
   * the conversation is being continued somewhere, and moving it would be a
   * second change nobody asked for. */
  useEffect(() => {
    if (touched || handoff) return
    const suggested = (defaults ? defaults.dirs[mode] : undefined) ?? dirs[0]
    if (suggested) setCwd(suggested)
  }, [mode, defaults, dirs, touched, handoff])
  const [carried, setCarried] = useState(handoff?.carried ?? '')

  /* Follows the mode too, until you pick one. Each mode has its own model
   * and models are configured separately, so the level that is already true
   * for Faber is not the one that is true for Noctua. */
  const [effort, setEffort] = useState<Effort | null>(null)
  const [effortTouched, setEffortTouched] = useState(false)
  const configured = defaults ? defaults.effort?.[mode] ?? null : null
  useEffect(() => {
    if (!effortTouched) setEffort(configured)
  }, [configured, effortTouched])

  /* The dialog takes focus itself, rather than a field inside it.
   *
   * It used to focus the opening-prompt textarea, which is gone; focusing
   * the directory instead would put a cursor in a field nobody usually
   * touches and mark it edited on the first keystroke. Focus still has to
   * land inside the dialog, because Escape, ⌘↵ and ⌘1–4 are handled here. */
  const dialogRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    dialogRef.current?.focus()
  }, [])

  /* Nothing to type here.
   *
   * There was an opening-prompt box, optional, and it went (2026-09-16):
   * the session opens by saying which mode it is and where it is, from the
   * backend's own prompt, and anything else is a first message better typed
   * into the terminal that is about to have focus anyway. A handoff still
   * carries its summary, which is not the same thing: that is the previous
   * session's words, and it is shown above for editing. */
  const launch = () => {
    if (full) return
    onLaunch({
      mode,
      cwd,
      effort: effort ?? undefined,
      from: handoff ? { mode: handoff.mode, label: handoff.label, carried } : undefined,
    })
  }

  // Capture phase for the same reason the app's shortcuts use it: the
  // textarea would otherwise swallow the keys before the dialog sees them.
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
      return
    }
    // Cmd+Enter, and bare Enter too once nothing here takes a newline: the
    // carried summary is the one field that does, and it is a textarea that
    // stops the event before this sees it.
    if (e.key === 'Enter') {
      e.preventDefault()
      launch()
      return
    }
    // Cmd+digit picks a mode. The shell's Cmd+1-9 (focus a terminal) is
    // suspended while this is open, so the same keys mean "choose".
    if (e.metaKey && /^[1-9]$/.test(e.key)) {
      const target = choices[Number(e.key) - 1]
      if (target) {
        e.preventDefault()
        setMode(target)
      }
    }
  }

  return (
    <div
      className="absolute inset-0 z-50 flex items-start justify-center bg-black/55 pt-[12vh]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        aria-label={handoff ? 'Hand off session' : 'New session'}
        onKeyDown={onKey}
        className="w-[560px] max-w-[calc(100%-32px)] overflow-hidden rounded-sheet border border-line bg-sheet shadow-[0_18px_50px_rgba(0,0,0,0.55)]"
        style={{ ['--accent' as string]: MODE_ACCENT[mode] }}
      >
        <div className="flex items-center gap-[9px] border-b border-line px-[14px] py-[10px] font-mono text-[11px] uppercase tracking-[0.13em] text-ink-faint">
          {handoff ? 'Hand off' : 'New session'}
          {handoff && (
            <span className="flex items-center gap-[6px] normal-case tracking-normal">
              <span className="text-ink-faint">from</span>
              <ModeMark mode={handoff.mode} size={13} />
              <span className="text-ink-dim">{handoff.label}</span>
            </span>
          )}
          <kbd className="ml-auto font-mono text-[10.5px] text-ink-faint">esc</kbd>
        </div>

        <div className="max-h-[52vh] overflow-y-auto p-[12px]">
          <div className="flex flex-col gap-[3px]">
            {choices.map((m, i) => {
              const selected = m === mode
              const info = MODE_INFO[m]
              return (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  aria-pressed={selected}
                  className={`flex items-center gap-[10px] rounded-control border px-[10px] py-[8px] text-left transition-colors ${
                    selected ? '' : 'border-transparent hover:bg-elevated'
                  }`}
                  style={
                    selected
                      ? {
                          background: `color-mix(in srgb, ${MODE_ACCENT[m]} 11%, var(--color-surface))`,
                          borderColor: `color-mix(in srgb, ${MODE_ACCENT[m]} 30%, var(--color-surface))`,
                        }
                      : undefined
                  }
                >
                  {/* The character, not a colour chip: the same mark the tab
                      strip and the Repo view use, so a mode is one picture
                      everywhere (2026-09-16). */}
                  <span className="shrink-0" style={{ opacity: selected ? 1 : 0.6 }}>
                    <ModeMark mode={m} size={18} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span
                      className="block font-mono text-[12px]"
                      style={{ color: selected ? MODE_ACCENT[m] : 'var(--color-ink)' }}
                    >
                      {MODE_LABEL[m]}
                    </span>
                    <span className="block truncate text-[11.5px] text-ink-faint">{info.blurb}</span>
                  </span>
                  {/* The tool policy is shown because it is the one thing that
                      changes what the session can do to your files. */}
                  {info.policy && (
                    <span className="shrink-0 rounded-control border border-line px-[5px] py-px font-mono text-[10px] text-ink-faint">
                      {info.policy}
                    </span>
                  )}
                  <kbd className="shrink-0 font-mono text-[10px] text-ink-faint">⌘{i + 1}</kbd>
                </button>
              )
            })}
          </div>

          {handoff && (
            <label className="mt-[12px] block">
              <span className="mb-[5px] flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-faint">
                Carrying
                {/* Editable, and labelled as a summary rather than the
                    transcript, so it is clear the new session gets this and
                    not the conversation it came from. */}
                <span className="normal-case tracking-normal">— summary, not the transcript</span>
              </span>
              <textarea
                value={carried}
                onChange={(e) => setCarried(e.target.value)}
                rows={3}
                className="w-full resize-none rounded-control border border-line bg-ground px-[10px] py-[8px] font-mono text-[11.5px] leading-[1.6] text-ink-dim outline-none focus:border-[var(--accent)]"
              />
            </label>
          )}

          <label className="mt-[12px] block">
            <span className="mb-[5px] block font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-faint">
              Directory
            </span>
            <input
              value={cwd}
              onChange={(e) => {
                setTouched(true)     // stop following the mode once you type
                setCwd(e.target.value)
              }}
              list="cwd-recents"
              spellCheck={false}
              className="w-full rounded-control border border-line bg-ground px-[10px] py-[7px] font-mono text-[11.5px] text-ink outline-none focus:border-[var(--accent)]"
            />
            <datalist id="cwd-recents">
              {dirs.map((d) => (
                <option key={d} value={d} />
              ))}
            </datalist>
          </label>

          <div className="mt-[12px]">
            <span className="mb-[5px] flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-faint">
              Effort
              <span className="normal-case tracking-normal">
                {configured ? `— ${MODE_LABEL[mode]} runs at ${configured} unless you say otherwise` : '— the engine\'s own setting'}
              </span>
            </span>
            <div className="flex gap-[3px]" role="group" aria-label="Effort">
              {EFFORTS.map((level) => {
                const on = effort === level
                return (
                  <button
                    key={level}
                    type="button"
                    onClick={() => { setEffortTouched(true); setEffort(level) }}
                    aria-pressed={on}
                    className={`flex-1 rounded-control border px-[8px] py-[6px] font-mono text-[11.5px] transition-colors ${
                      on ? '' : 'border-line text-ink-faint hover:bg-elevated hover:text-ink-dim'
                    }`}
                    style={
                      on
                        ? {
                            background: `color-mix(in srgb, ${MODE_ACCENT[mode]} 14%, var(--color-surface))`,
                            borderColor: `color-mix(in srgb, ${MODE_ACCENT[mode]} 35%, var(--color-surface))`,
                            color: MODE_ACCENT[mode],
                          }
                        : undefined
                    }
                  >
                    {level}
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-[10px] border-t border-line px-[14px] py-[10px]">
          <span className={`font-mono text-[10.5px] ${full ? 'text-ink' : 'text-ink-faint'}`}>
          {full ?? `↵ to start · ⌘1–${choices.length} to pick · opens by saying what it is`}
        </span>
          <button
            type="button"
            onClick={launch}
            disabled={!!full}

            className="ml-auto rounded-control px-[13px] py-[6px] font-mono text-[11.5px] text-ground transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
            style={{ background: MODE_ACCENT[mode] }}
          >
            Start {MODE_LABEL[mode]}
          </button>
        </div>
      </div>
    </div>
  )
}
