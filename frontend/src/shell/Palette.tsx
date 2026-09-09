/* Search — ⌘K over conversations and the vault.
 *
 * Two lists, not one merged ranking. The scores are not comparable (different
 * corpora, different index), so interleaving them would produce an order that
 * looks meaningful and is not. It also matches how you search: "what did I
 * say about X" and "what does the vault say about X" are different questions,
 * and you usually know which one you are asking.
 *
 * ⌘K is finally real. It was labelled in the UI early on and removed again
 * because the label was a lie -- a shortcut shown but not implemented is
 * worse than one that is absent.
 */
import { useEffect, useRef, useState } from 'react'
import { get } from './engine'
import { MODE_ACCENT, MODE_LABEL, type Mode } from './domain'

interface Results {
  conversations: { session_id: number; mode: Mode; role: string; excerpt: string; at: string }[]
  documents: { path: string; heading: string; excerpt: string; score: number }[]
}

export function Palette({
  onOpenSession,
  onOpenDoc,
  onDelete,
  onClose,
}: {
  onOpenSession: (id: number) => void
  onOpenDoc: (path: string) => void
  onDelete: (id: number) => void
  onClose: () => void
}) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Results | null>(null)
  const [busy, setBusy] = useState(false)
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  /* Debounced, and every response checked against the query that is current
   * by the time it lands. Without that check a slow early request can
   * overwrite the results of a later, faster one, and the list ends up
   * showing matches for something you have already finished typing. */
  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) {
      setResults(null)
      return
    }
    setBusy(true)
    const timer = setTimeout(async () => {
      const data = await get<Results>(`/v2/search?q=${encodeURIComponent(term)}`)
      if (inputRef.current?.value.trim() !== term) return
      setResults(data ?? { conversations: [], documents: [] })
      setCursor(0)
      setBusy(false)
    }, 160)
    return () => clearTimeout(timer)
  }, [q])

  // Deleted ids are hidden immediately rather than by re-running the query:
  // a row that stays until the next search reads as a delete that failed.
  const [removed, setRemoved] = useState<Set<number>>(new Set())
  const sessions = (results?.conversations ?? []).filter((s) => !removed.has(s.session_id))
  const docs = results?.documents ?? []
  const total = sessions.length + docs.length

  const activate = (i: number) => {
    if (i < sessions.length) onOpenSession(sessions[i].session_id)
    else onOpenDoc(docs[i - sessions.length].path)
    onClose()
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => Math.min(total - 1, c + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => Math.max(0, c - 1))
    } else if (e.key === 'Enter' && total > 0) {
      e.preventDefault()
      activate(cursor)
    }
  }

  return (
    <div
      className="absolute inset-0 z-50 flex items-start justify-center bg-black/55 pt-[11vh]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        onKeyDown={onKey}
        className="flex max-h-[66vh] w-[640px] max-w-[calc(100%-32px)] flex-col overflow-hidden rounded-[6px] border border-line bg-surface shadow-[0_18px_50px_rgba(0,0,0,0.55)]"
      >
        <div className="flex items-center gap-[10px] border-b border-line px-[14px] py-[11px]">
          <span aria-hidden className="font-mono text-[13px] text-ink-faint">⌕</span>
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search conversations and the vault"
            spellCheck={false}
            className="flex-1 border-0 bg-transparent font-mono text-[13px] text-ink outline-none placeholder:text-ink-faint"
          />
          <kbd className="font-mono text-[10.5px] text-ink-faint">esc</kbd>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {q.trim().length < 2 ? (
            <Empty>Type at least two characters.</Empty>
          ) : busy && !results ? (
            <Empty>Searching…</Empty>
          ) : total === 0 ? (
            <Empty>No matches.</Empty>
          ) : (
            <>
              {sessions.length > 0 && <Group label="Conversations" />}
              {sessions.map((s, i) => (
                <Row
                  key={`s${s.session_id}`}
                  selected={cursor === i}
                  onHover={() => setCursor(i)}
                  onClick={() => activate(i)}
                  accent={MODE_ACCENT[s.mode] ?? 'var(--color-ink-dim)'}
                  title={`${MODE_LABEL[s.mode] ?? s.mode} · ${s.at.slice(0, 10)}`}
                  excerpt={s.excerpt}
                  /* Deleting lives here because this is where old
                     conversations are actually found. The tab strip only
                     ever holds two, so it was never the place to clear
                     history from. */
                  onDelete={() => {
                    onDelete(s.session_id)
                    setRemoved((r) => new Set(r).add(s.session_id))
                  }}
                />
              ))}

              {docs.length > 0 && <Group label="Vault" />}
              {docs.map((d, i) => (
                <Row
                  key={d.path + d.heading + i}
                  selected={cursor === sessions.length + i}
                  onHover={() => setCursor(sessions.length + i)}
                  onClick={() => activate(sessions.length + i)}
                  accent="var(--color-ink-faint)"
                  title={`${d.path}${d.heading ? ` · ${d.heading}` : ''}`}
                  excerpt={d.excerpt}
                />
              ))}
            </>
          )}
        </div>

        <div className="border-t border-line px-[14px] py-[9px] font-mono text-[10.5px] text-ink-faint">
          ↑↓ to move · ↵ opens
        </div>
      </div>
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="px-[14px] py-[16px] text-[12.5px] text-ink-faint">{children}</div>
}

function Group({ label }: { label: string }) {
  return (
    <div className="border-b border-line bg-elevated px-[14px] py-[5px] font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">
      {label}
    </div>
  )
}

function Row({
  selected,
  onHover,
  onClick,
  onDelete,
  accent,
  title,
  excerpt,
}: {
  selected: boolean
  onHover: () => void
  onClick: () => void
  onDelete?: () => void
  accent: string
  title: string
  excerpt: string
}) {
  return (
    <button
      type="button"
      onMouseEnter={onHover}
      onClick={onClick}
      className={`flex w-full items-start gap-[10px] px-[14px] py-[9px] text-left ${
        selected ? 'bg-elevated' : ''
      }`}
    >
      <span className="mt-[5px] h-[7px] w-[7px] shrink-0 rounded-[1px]" style={{ background: accent }} />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-mono text-[11.5px] text-ink-dim">{title}</span>
        <span className="mt-[2px] block text-[12.5px] leading-[1.5] text-ink-faint">{excerpt}</span>
      </span>
      {onDelete && (
        <span
          role="button"
          aria-label="Delete this conversation"
          title="Delete this conversation — removes its transcript and usage for good"
          tabIndex={-1}
          onClick={(e) => {
            e.stopPropagation()   // deleting must not also open it
            onDelete()
          }}
          className={`shrink-0 rounded-[3px] px-[5px] py-[2px] text-[12px] leading-none transition-colors hover:bg-line hover:text-faber ${
            selected ? 'text-ink-faint' : 'text-transparent'
          }`}
        >
          ×
        </span>
      )}
    </button>
  )
}
