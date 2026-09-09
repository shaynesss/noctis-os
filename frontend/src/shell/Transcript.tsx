/* Transcript — block-structured, not a character stream.
 *
 * `stream-json` hands us discrete events (thinking, tool_use, tool_result,
 * text), so the transcript is built from blocks rather than appended text.
 * That is why the Design Brief takes Ghostty for *rendering* and not for its
 * stream model: a terminal-shaped transcript would fight the data. */
import { useState } from 'react'
import { Working } from './Working'
import { MODE_ACCENT, MODE_LABEL, type Block, type Mode } from './mock'

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
    <div className="mb-[8px] overflow-hidden rounded-[3px] border border-line bg-surface">
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

export function Transcript({
  blocks,
  accent,
  thinking,
  mode,
  startedAt,
}: {
  blocks: Block[]
  accent: string
  /** Live thinking-token estimate, or null when not reasoning. */
  thinking?: number | null
  mode: Mode
  /** When the running turn began, or null when nothing is running. */
  startedAt?: number | null
}) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[840px] px-8 pb-8 pt-7">
        {blocks.map((b, i) => {
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
          if (b.kind === 'handoff') {
            /* Provenance, not a message. A handed-off session that opened on
             * a bare prompt would look like something you started and forgot
             * -- this says where it came from and what it was given, and the
             * distinction between the two is the point: the new session got
             * the summary, not the conversation. */
            return (
              <div key={i} className="mb-[16px] rounded-[3px] border border-line bg-surface">
                <div className="flex items-center gap-[7px] border-b border-line px-[11px] py-[7px] font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-faint">
                  Handed off from
                  <span
                    className="h-[6px] w-[6px] rounded-[1px]"
                    style={{ background: MODE_ACCENT[b.from] }}
                  />
                  <span className="normal-case tracking-normal text-ink-dim">{b.fromLabel}</span>
                  <span className="ml-auto normal-case tracking-normal">
                    carried summary · {MODE_LABEL[b.from]} session still open
                  </span>
                </div>
                <p className="m-0 px-[11px] py-[10px] text-[12.5px] leading-[1.65] text-ink-dim">
                  {b.carried}
                </p>
              </div>
            )
          }
          if (b.kind === 'error') {
            /* In the transcript rather than a toast: a failed turn is
             * exactly the thing you scroll back to find, and a toast puts it
             * somewhere the session's own history does not record. */
            return (
              <div
                key={i}
                className="mb-[16px] rounded-[3px] border px-[11px] py-[9px] text-[12.5px] leading-[1.6]"
                style={{
                  borderColor: 'color-mix(in srgb, var(--color-faber) 40%, var(--color-surface))',
                  background: 'color-mix(in srgb, var(--color-faber) 8%, var(--color-surface))',
                }}
              >
                <div className="mb-[4px] font-mono text-[10.5px] uppercase tracking-[0.1em] text-faber">
                  {b.fatal ? 'Session failed' : 'Engine error'}
                </div>
                <div className="text-ink-dim">{b.message}</div>
              </div>
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
          return (
            <div key={i} className="mb-[18px] space-y-[9px] text-[13.5px] leading-[1.65]">
              {b.text.split('\n\n').map((p, j) => (
                <p key={j} className="m-0">
                  <Rich text={p} />
                </p>
              ))}
            </div>
          )
        })}

        {startedAt != null && (
          <Working key={startedAt} mode={mode} startedAt={startedAt} thinking={thinking} accent={accent} />
        )}
      </div>
    </div>
  )
}
