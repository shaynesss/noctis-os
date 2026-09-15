/* Vault document reader.
 *
 * Search could find documents and had nowhere to put them, so a result was
 * an excerpt and a dead end. This is the other half of that.
 *
 * An overlay rather than a tab, because the actual use is looking something
 * up *during* a conversation — a decision you half-remember, what the spec
 * actually said. A tab would make you leave the session to check, which is
 * the friction v2 exists to remove. Escape returns you to exactly where you
 * were.
 */
import { useEffect, useState } from 'react'
import { get } from './engine'
import { Markdown } from './Markdown'

const cut = (p: string) => p.lastIndexOf('/') + 1
const folder = (p: string) => p.slice(0, cut(p))
const filename = (p: string) => p.slice(cut(p))

export function Reader({ path, onClose }: { path: string; onClose: () => void }) {
  const [doc, setDoc] = useState<{ markdown: string } | null | false>(null)

  useEffect(() => {
    let live = true
    void get<{ path: string; markdown: string }>(
      `/v2/vault/doc?path=${encodeURIComponent(path)}`,
    ).then((d) => live && setDoc(d ?? false))
    return () => {
      live = false
    }
  }, [path])

  // On the window, not the dialog: the reader has nothing focusable until it
  // has loaded, so a handler on the panel itself would miss Escape for as
  // long as the fetch takes -- which is exactly when you are most likely to
  // press it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose])

  return (
    <div
      className="absolute inset-0 z-[60] flex items-start justify-center bg-black/55 pt-[8vh]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={path}
        className="flex max-h-[80vh] w-[760px] max-w-[calc(100%-32px)] flex-col overflow-hidden rounded-sheet border border-line bg-sheet shadow-[0_18px_50px_rgba(0,0,0,0.55)]"
      >
        <div className="flex shrink-0 items-center gap-[10px] border-b border-line px-[14px] py-[10px]">
          {/* The full path, not a prettified title: it is how you find the
              file again outside the app, and the vault is the thing of
              record. Split so the filename is never what gets truncated --
              `dir="rtl"` would also keep the tail, but it reorders leading
              and trailing punctuation, and these are paths full of slashes
              and dots. */}
          <span className="flex min-w-0 flex-1 items-baseline font-mono text-[11.5px]" title={path}>
            <span className="min-w-0 truncate text-ink-faint">{folder(path)}</span>
            <span className="shrink-0 text-ink-dim">{filename(path)}</span>
          </span>
          <kbd className="shrink-0 font-mono text-[10.5px] text-ink-faint">esc</kbd>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {doc === null ? (
            <div className="px-[18px] py-[16px] text-[12.5px] text-ink-faint">Loading…</div>
          ) : doc === false ? (
            <div className="px-[18px] py-[16px] text-[12.5px] text-ink-dim">
              Could not read this document. It may have been moved or renamed since it was indexed.
            </div>
          ) : (
            <Markdown src={doc.markdown} className="px-[18px] py-[16px]" />
          )}
        </div>
      </div>
    </div>
  )
}
