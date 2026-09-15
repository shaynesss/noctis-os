/* Files a conversation created or changed.
 *
 * Derived from the session's own tool calls rather than anything it
 * announces — a turn that writes a file has already said so, and asking the
 * model to additionally declare its outputs would be a second source that
 * can disagree with the first.
 *
 * One chip per path, not per call: editing the same file eleven times is one
 * thing you might want to look at, and eleven identical chips would be the
 * tool log again wearing a different heading.
 */
import { useEffect, useState } from 'react'
import { get } from './engine'

export interface Artifact {
  path: string
  name: string
  tools: string[]
  writes: number
  at: string
}

/** Vault markdown can be opened in the reader; nothing else can.
 *
 * The reader is deliberately vault-and-markdown-only — it was narrowed that
 * way because a reader that serves any path is a file-exfiltration endpoint
 * wearing a document viewer's clothes. So a chip for a repo file shows what
 * it is and does not pretend to be a link. */
function readable(path: string): string | null {
  const at = path.indexOf('/second-brain/')
  if (at === -1 || !path.endsWith('.md')) return null
  return path.slice(at + '/second-brain/'.length)
}

export function Artifacts({
  sessionId,
  onOpen,
}: {
  /** Backend row id, or null for a session with no history row yet. */
  sessionId: number | null
  onOpen: (vaultPath: string) => void
}) {
  const [items, setItems] = useState<Artifact[]>([])

  useEffect(() => {
    if (sessionId === null) {
      setItems([])
      return
    }
    let live = true
    void get<{ artifacts: Artifact[] }>(`/v2/sessions/history/${sessionId}/artifacts`).then((d) => {
      if (live) setItems(d?.artifacts ?? [])
    })
    return () => {
      live = false
    }
  }, [sessionId])

  if (items.length === 0) return null

  return (
    <div className="mb-[16px] flex flex-wrap items-center gap-[6px]">
      <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-faint">
        touched
      </span>
      {items.map((a) => {
        const vault = readable(a.path)
        return (
          <button
            key={a.path}
            type="button"
            disabled={!vault}
            onClick={() => vault && onOpen(vault)}
            title={`${a.path}${a.writes > 1 ? ` · ${a.writes} writes` : ''}`}
            className={`flex items-center gap-[6px] rounded-control border border-line px-[8px] py-[3px] font-mono text-[11px] transition-colors ${
              vault
                ? 'cursor-pointer text-ink-dim hover:bg-elevated hover:text-ink'
                : 'cursor-default text-ink-faint'
            }`}
          >
            {a.name}
            {/* The count only when it says something: "1 write" is noise. */}
            {a.writes > 1 && <span className="text-ink-faint">{a.writes}×</span>}
          </button>
        )
      })}
    </div>
  )
}
