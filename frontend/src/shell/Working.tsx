/* The live line shown while a turn runs.
 *
 * It exists because a transcript that simply stops is indistinguishable from
 * one that has crashed — the elapsed timer is the proof that something is
 * still happening, which is the whole job of this line.
 *
 * Only real numbers. Elapsed is measured here; thinking tokens come from the
 * engine's own `thinking_tokens` events and are absent until it sends one.
 * Output tokens are deliberately not shown: they are unavailable mid-turn
 * without partial-message streaming, and a plausible number would be a lie
 * told convincingly.
 */
import { useEffect, useState } from 'react'
import { MODE_LABEL, type Mode } from './mock'

/* Each mode says what it is doing, so the line also tells you which session
 * is working when several are open. General has no craft of its own — it is
 * the front door — so it borrows Claude Code's whimsy instead. */
const MODE_VERB: Record<Exclude<Mode, 'general'>, string> = {
  faber: 'building',
  noctua: 'reading',
  vesper: 'digging',
  maintenance: 'auditing',
}

const GENERAL_WORDS = [
  'Propagating', 'Cogitating', 'Percolating', 'Ruminating', 'Simmering',
  'Noodling', 'Puzzling', 'Mulling', 'Churning', 'Distilling', 'Pondering',
  'Wondering', 'Untangling', 'Deliberating', 'Considering',
]

/** Chosen once, when this component mounts.
 *
 * A word that changed every second would be motion for its own sake and
 * unreadable besides. The caller keys this component on the turn's start
 * time, so a new turn remounts it and re-rolls the word — which is why
 * nothing here needs to watch for a change.
 */
function useTurnWord(mode: Mode): string {
  return useState(() =>
    mode === 'general'
      ? GENERAL_WORDS[Math.floor(Math.random() * GENERAL_WORDS.length)]
      : `${MODE_LABEL[mode]} is ${MODE_VERB[mode]}`,
  )[0]
}

function elapsed(ms: number): string {
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

export function Working({
  mode,
  startedAt,
  thinking,
  accent,
}: {
  mode: Mode
  startedAt: number
  /** Live thinking-token estimate, or null before the engine reports one. */
  thinking?: number | null
  accent: string
}) {
  const word = useTurnWord(mode)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="mb-[14px] flex items-center gap-[9px] font-mono text-[12px]">
      <span
        aria-hidden
        className="animate-pulse text-[13px] leading-none motion-reduce:animate-none"
        style={{ color: accent }}
      >
        ✳
      </span>
      <span style={{ color: accent }}>{word}…</span>
      <span className="text-ink-faint">
        ({elapsed(now - startedAt)}
        {thinking != null && thinking > 0 && ` · ${thinking.toLocaleString()} thinking tokens`})
      </span>
    </div>
  )
}
