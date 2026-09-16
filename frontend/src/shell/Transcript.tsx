/* Transcript — a past conversation, read from history.
 *
 * Block-structured, not a character stream: the CLI's own transcript on disk
 * records discrete events (thinking, tool_use, tool_result, text), so the
 * reader is built from blocks rather than appended text. A live session is
 * the CLI's own TUI in a terminal; this renders only what the store indexed. */
import { useLayoutEffect, useRef, useState } from 'react'
import { Markdown } from './Markdown'
import { Artifacts } from './Artifacts'
import { failures, groupTools, summarise, type ToolBlock } from './tools'
import { type Block } from './domain'

function Caret({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden
      className="h-[9px] w-[9px] shrink-0 stroke-ink-faint transition-transform duration-150"
      style={{ transform: open ? 'rotate(90deg)' : undefined, fill: 'none', strokeWidth: 2 }}
    >
      <path d="M9 6l6 6-6 6" />
    </svg>
  )
}

/** Tool calls and thinking share a disclosure row: same shape, same rhythm,
 *  so a long run of them reads as one texture rather than several. */
function Disclosure({
  label,
  target,
  meta,
  body,
  defaultOpen = false,
  italic = false,
}: {
  label: string
  target?: string
  meta?: string
  body?: string
  defaultOpen?: boolean
  italic?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const canOpen = Boolean(body)
  return (
    <div className="mb-[8px] overflow-hidden rounded-card border border-line bg-surface">
      <button
        type="button"
        onClick={() => canOpen && setOpen(!open)}
        aria-expanded={canOpen ? open : undefined}
        disabled={!canOpen}
        className="flex w-full items-center gap-[9px] px-[11px] py-[7px] text-left font-mono text-[11.5px] text-ink-dim enabled:hover:bg-elevated disabled:cursor-default"
      >
        {canOpen ? <Caret open={open} /> : <span className="w-[9px]" />}
        <span className={`text-ink ${italic ? 'italic' : ''}`}>{label}</span>
        {target && <span className="truncate text-ink-faint">{target}</span>}
        {meta && <span className="ml-auto shrink-0 text-[10.5px] text-ink-faint">{meta}</span>}
      </button>
      {open && body && (
        <pre className="m-0 whitespace-pre-wrap border-t border-line px-[11px] py-[10px] pl-[29px] font-mono text-[11.5px] leading-[1.7] text-ink-dim">
          {body}
        </pre>
      )}
    </div>
  )
}

/* Scrolling.
 *
 * Two behaviours, and they conflict, so the rule is explicit: follow new
 * output only while you are already at the bottom. Yanking the view down
 * while someone is reading further up is the thing that makes a streaming
 * transcript unusable, and it is worse than not following at all.
 *
 * Position is remembered per conversation and restored on return. Switching
 * to Stats and back used to unmount this and rebuild it at the top, so you
 * came back to the beginning of a conversation you were halfway through.
 */
export function Transcript({
  blocks,
  historyId,
  onOpenDoc,
  scrollKey,
}: {
  blocks: Block[]
  /** Backend row id, for the files this conversation touched. */
  historyId?: number | null
  onOpenDoc?: (vaultPath: string) => void
  /** Identifies the conversation, so its scroll position is its own. */
  scrollKey: string
}) {
  const box = useRef<HTMLDivElement>(null)
  // How close to the bottom still counts as "at the bottom". A couple of
  // lines of slack, so a stray pixel or an image finishing loading does not
  // silently stop the follow.
  const NEAR_BOTTOM = 60

  const wasAtBottom = useRef(true)

  const atBottom = () => {
    const el = box.current
    if (!el) return true
    return el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM
  }

  // Restore before paint, not after, or the conversation is visibly at the
  // top for a frame before jumping.
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    el.scrollTop = el.scrollHeight
    /* And decide, from where we just landed, whether output should be
     * followed. Both layout effects run on mount and this one is declared
     * first, so without setting it here the follow below would immediately
     * override the position just restored — returning you to the bottom of
     * a conversation you had deliberately scrolled up in. */
    wasAtBottom.current = atBottom()
    // Only when the conversation changes: re-running on every render would
    // fight the person scrolling.
  }, [scrollKey])   // eslint-disable-line react-hooks/exhaustive-deps

  // Follow the output, if you were already following it.
  useLayoutEffect(() => {
    const el = box.current
    if (!el || !wasAtBottom.current) return
    el.scrollTop = el.scrollHeight
  }, [blocks])

  return (
    <div
      ref={box}
      onScroll={() => {
        wasAtBottom.current = atBottom()
      }}
      className="min-h-0 flex-1 overflow-y-auto"
    >
      <div className="mx-auto max-w-[840px] px-8 pb-8 pt-7">
        {groupTools(blocks).map((group, gi) => {
          if (group.kind === 'tools') return <ToolRun key={`g${gi}`} tools={group.tools} />
          return renderBlock(group.block, gi)
        })}

        {/* Below the conversation, above the turn's closing line: it is a
            summary of what the session did, so it belongs where you land
            when you finish reading rather than at the top. */}
        {historyId != null && onOpenDoc && (
          <Artifacts sessionId={historyId} onOpen={onOpenDoc} />
        )}
      </div>
    </div>
  )
}


/* One collapsed row for a run of tool calls.
 *
 * Closed by default: eleven bordered boxes with their own error text pushed
 * the reply that mattered off the screen, and the calls are how the answer
 * was reached rather than the answer. Failures are counted on the row even
 * while it is shut, because a collapsed line that hides them is how you miss
 * that nothing actually ran.
 */
function ToolRun({ tools }: { tools: ToolBlock[] }) {
  const failed = failures(tools)
  const [open, setOpen] = useState(failed > 0 && tools.length <= 2)

  return (
    <div className="mb-[10px]">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-[8px] rounded-control px-[2px] py-[3px] text-left font-mono text-[12px] text-ink-faint hover:text-ink-dim"
      >
        <Caret open={open} />
        <span>{summarise(tools)}</span>
        {failed > 0 && (
          <span className="text-faber">
            · {failed} failed
          </span>
        )}
      </button>

      {open && (
        <div className="mt-[5px] pl-[17px]">
          {tools.map((t, i) => (
            <Disclosure
              key={t.id ?? i}
              label={t.name}
              target={t.target}
              meta={t.meta}
              body={t.body}
              defaultOpen={t.open}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** One transcript block. */
function renderBlock(b: Block, i: number) {
          if (b.kind === 'user') {
            /* A prompt glyph and dimmer ink instead of a YOU label: it is
             * already obvious which turn is yours, and a caption on every
             * one of them was two lines of furniture per exchange. The time
             * moves to a tooltip -- worth having, not worth a line. */
            return (
              <div key={i} className="mb-[16px] flex gap-[9px]" title={b.at}>
                <span
                  aria-hidden
                  className="select-none font-mono text-[13px] leading-[1.6] text-ink-faint"
                >
                  ›
                </span>
                <div className="min-w-0 whitespace-pre-wrap font-mono text-[13px] leading-[1.6] text-ink-dim">
                  {b.text}
                </div>
              </div>
            )
          }
          if (b.kind === 'thinking') {
            /* Thinking text is empty under display:"omitted" -- reasoning is
             * billed but never returned. So this shows activity, not content:
             * a token count and a duration, which is what is actually known. */
            return (
              <Disclosure
                key={i}
                label="Thinking"
                meta={`${b.tokens} tokens · ${(b.ms / 1000).toFixed(1)}s`}
                italic
              />
            )
          }
          if (b.kind === 'tool') {
            return (
              <Disclosure
                key={i}
                label={b.name}
                target={b.target}
                meta={b.meta}
                body={b.body}
                defaultOpen={b.open}
              />
            )
          }
          /* No CLAUDE label. The reply is the page's main column -- full
           * width, normal ink -- and the dimmed, glyph-prefixed user turn
           * above it is what marks the boundary. Naming the speaker on every
           * turn is the kind of thing that reads as helpful once and as
           * clutter for the rest of the session. */
          return <Markdown key={i} src={b.text} className="mb-[18px]" />
}
