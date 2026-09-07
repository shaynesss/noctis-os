/* Transcript — block-structured, not a character stream.
 *
 * `stream-json` hands us discrete events (thinking, tool_use, tool_result,
 * text), so the transcript is built from blocks rather than appended text.
 * That is why the Design Brief takes Ghostty for *rendering* and not for its
 * stream model: a terminal-shaped transcript would fight the data. */
import { useState } from 'react'
import type { Block } from './mock'

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
    <div className="mb-[7px] overflow-hidden rounded-[3px] border border-line bg-surface">
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

/** Minimal inline formatting. A full markdown renderer is a Stage 2 table
 *  stake; this covers what a transcript actually contains — bold, emphasis
 *  and inline code — without pulling a dependency in at design time. */
function Rich({ text }: { text: string }) {
  const nodes = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith('**')) return <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>
    if (part.startsWith('`'))
      return (
        <code key={i} className="rounded-[3px] border border-line bg-elevated px-[4px] py-px font-mono text-[0.88em] text-ink">
          {part.slice(1, -1)}
        </code>
      )
    if (part.startsWith('*')) return <em key={i} className="text-ink-dim">{part.slice(1, -1)}</em>
    return <span key={i}>{part}</span>
  })
  return <>{nodes}</>
}

export function Transcript({ blocks, accent }: { blocks: Block[]; accent: string }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[840px] px-8 pb-8 pt-7">
        {blocks.map((b, i) => {
          if (b.kind === 'user') {
            return (
              <div key={i} className="mb-[22px]">
                <div className="mb-2 flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-faint">
                  <span className="h-[6px] w-[6px] rounded-[1px] bg-ink-dim" />
                  You · {b.at}
                </div>
                <div className="border-l-2 border-line pl-3 text-[13.5px] leading-[1.68]">{b.text}</div>
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
          return (
            <div key={i} className="mb-[22px]">
              <div className="mb-2 flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-faint">
                <span className="h-[6px] w-[6px] rounded-[1px]" style={{ background: accent }} />
                Claude
              </div>
              <div className="space-y-[11px] text-[13.5px] leading-[1.68]">
                {b.text.split('\n\n').map((p, j) => (
                  <p key={j} className="m-0">
                    <Rich text={p} />
                  </p>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
