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
import { useFetched } from './useFetched'
import { MODE_ACCENT, MODE_INFO, MODE_LABEL, type Mode } from './domain'

const MODES: Mode[] = ['general', 'faber', 'noctua', 'vesper', 'maintenance']

export interface LaunchRequest {
  mode: Mode
  cwd: string
  prompt: string
  /** Set when this launch came from a handoff, for the provenance block. */
  from?: { mode: Mode; label: string; carried: string }
}

export function Launcher({
  handoff,
  modeModels,
  onLaunch,
  onClose,
}: {
  /** Each mode's model, as the orchestrator reports it. */
  modeModels?: Record<string, string>
  /** Present when handing off: the source session and what it carries. */
  handoff?: { mode: Mode; label: string; cwd: string; carried: string }
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
  const [cwd, setCwd] = useState(handoff?.cwd ?? '')

  /* Filled in once history arrives, and only while untouched — typing a
   * directory and having it replaced a moment later would be maddening.
   * `dirs` is memoised on the fetch result, or a fresh array each render
   * would re-run this effect forever. */
  useEffect(() => {
    if (!cwd && dirs.length > 0) setCwd(dirs[0])
  }, [cwd, dirs])
  const [prompt, setPrompt] = useState('')
  const [carried, setCarried] = useState(handoff?.carried ?? '')
  const promptRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    promptRef.current?.focus()
  }, [])

  const launch = () => {
    if (!prompt.trim()) return
    onLaunch({
      mode,
      cwd,
      prompt: prompt.trim(),
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
    // Cmd+Enter, not bare Enter: the prompt is a textarea and newlines in an
    // opening instruction are normal, so Enter must stay a newline here even
    // though it sends in the composer.
    if (e.key === 'Enter' && e.metaKey) {
      e.preventDefault()
      launch()
      return
    }
    // Cmd+digit picks a mode. The composer's Cmd+1/2/3 is suspended while
    // this is open, so the same keys mean "choose" rather than "switch tab".
    if (e.metaKey && /^[1-5]$/.test(e.key)) {
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
        role="dialog"
        aria-modal="true"
        aria-label={handoff ? 'Hand off session' : 'New session'}
        onKeyDown={onKey}
        className="w-[560px] max-w-[calc(100%-32px)] overflow-hidden rounded-[6px] border border-line bg-surface shadow-[0_18px_50px_rgba(0,0,0,0.55)]"
        style={{ ['--accent' as string]: MODE_ACCENT[mode] }}
      >
        <div className="flex items-center gap-[9px] border-b border-line px-[14px] py-[10px] font-mono text-[11px] uppercase tracking-[0.13em] text-ink-faint">
          {handoff ? 'Hand off' : 'New session'}
          {handoff && (
            <span className="flex items-center gap-[6px] normal-case tracking-normal">
              <span className="text-ink-faint">from</span>
              <span
                className="h-[7px] w-[7px] rounded-[1px]"
                style={{ background: MODE_ACCENT[handoff.mode] }}
              />
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
                  className={`flex items-center gap-[10px] rounded-[4px] border px-[10px] py-[8px] text-left transition-colors ${
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
                  <span
                    className="h-[8px] w-[8px] shrink-0 rounded-[1px]"
                    style={{ background: MODE_ACCENT[m], opacity: selected ? 1 : 0.55 }}
                  />
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
                    <span className="shrink-0 rounded-[3px] border border-line px-[5px] py-px font-mono text-[10px] text-ink-faint">
                      {info.policy}
                    </span>
                  )}
                  {/* From the backend, so this cannot drift into naming a
                      model the orchestrator no longer runs. */}
                  <span className="shrink-0 font-mono text-[10.5px] text-ink-faint">
                    {modeModels?.[m] ?? info.model}
                  </span>
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
                className="w-full resize-none rounded-[4px] border border-line bg-ground px-[10px] py-[8px] font-mono text-[11.5px] leading-[1.6] text-ink-dim outline-none focus:border-[var(--accent)]"
              />
            </label>
          )}

          <label className="mt-[12px] block">
            <span className="mb-[5px] block font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-faint">
              Directory
            </span>
            <input
              value={cwd}
              onChange={(e) => setCwd(e.target.value)}
              list="cwd-recents"
              spellCheck={false}
              className="w-full rounded-[4px] border border-line bg-ground px-[10px] py-[7px] font-mono text-[11.5px] text-ink outline-none focus:border-[var(--accent)]"
            />
            <datalist id="cwd-recents">
              {dirs.map((d) => (
                <option key={d} value={d} />
              ))}
            </datalist>
          </label>

          <label className="mt-[12px] block">
            <span className="mb-[5px] block font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-faint">
              Opening prompt
            </span>
            <textarea
              ref={promptRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
              spellCheck={false}
              className="w-full resize-none rounded-[4px] border border-line bg-ground px-[10px] py-[8px] font-mono text-[12px] leading-[1.6] text-ink outline-none focus:border-[var(--accent)]"
            />
          </label>
        </div>

        <div className="flex items-center gap-[10px] border-t border-line px-[14px] py-[10px]">
          <span className="font-mono text-[10.5px] text-ink-faint">⌘↵ to start · ⌘1–5 to pick</span>
          <button
            type="button"
            onClick={launch}
            disabled={!prompt.trim()}
            className="ml-auto rounded-[4px] px-[13px] py-[6px] font-mono text-[11.5px] text-ground transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
            style={{ background: MODE_ACCENT[mode] }}
          >
            Start {MODE_LABEL[mode]}
          </button>
        </div>
      </div>
    </div>
  )
}
