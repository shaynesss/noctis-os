/* Transcript — block-structured, not a character stream.
 *
 * `stream-json` hands us discrete events (thinking, tool_use, tool_result,
 * text), so the transcript is built from blocks rather than appended text.
 * That is why the Design Brief takes Ghostty for *rendering* and not for its
 * stream model: a terminal-shaped transcript would fight the data. */
import { useLayoutEffect, useRef, useState } from 'react'
import { Markdown } from './Markdown'
import { Artifacts } from './Artifacts'
import { failures, groupTools, summarise, type ToolBlock } from './tools'
import { Finished, Working } from './Working'
import { MODE_ACCENT, MODE_LABEL, type Block, type Mode } from './domain'

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
  accent,
  thinking,
  mode,
  startedAt,
  recap,
  lastTurn,
  historyId,
  onOpenDoc,
  scrollKey,
  initialScroll,
  onScroll,
  streaming,
  onEdit,
  onRetry,
}: {
  blocks: Block[]
  accent: string
  /** Live thinking-token estimate, or null when not reasoning. */
  thinking?: number | null
  mode: Mode
  /** When the running turn began, or null when nothing is running. */
  startedAt?: number | null
  /** One-line reminder of where a restored conversation left off. */
  recap?: string | null
  /** The last turn's duration and end time. */
  lastTurn?: { seconds: number; at: number } | null
  /** Backend row id, for the files this conversation touched. */
  historyId?: number | null
  onOpenDoc?: (vaultPath: string) => void
  /** Identifies the conversation, so its scroll position is its own. */
  scrollKey: string
  /** Where this conversation was last left, in pixels from the top. */
  initialScroll?: number
  onScroll?: (key: string, top: number) => void
  /** True while a turn is streaming, which is when to follow the output. */
  streaming?: boolean
  /** Put a past message back in the composer to rephrase. */
  onEdit?: (text: string) => void
  /** Ask the same thing again. */
  onRetry?: (text: string) => void
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
    el.scrollTop = initialScroll ?? el.scrollHeight
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
  }, [blocks, thinking, streaming])

  return (
    <div
      ref={box}
      onScroll={(e) => {
        const el = e.currentTarget
        wasAtBottom.current = atBottom()
        onScroll?.(scrollKey, el.scrollTop)
      }}
      className="min-h-0 flex-1 overflow-y-auto"
    >
      <div className="mx-auto max-w-[840px] px-8 pb-8 pt-7">
        {/* Above the transcript, not inside it: this is not something anyone
            said. It is a reminder of where a resumed conversation got to,
            which is the one thing you need before reading a wall of text you
            wrote days ago. */}
        {recap && (
          <div className="mb-[20px] flex gap-[9px] text-[12.5px] italic leading-[1.6] text-ink-faint">
            <span aria-hidden className="not-italic" style={{ color: accent }}>✳</span>
            <span>
              <span className="font-semibold not-italic">recap:</span> {recap}
            </span>
          </div>
        )}
        {groupTools(blocks).map((group, gi) => {
          if (group.kind === 'tools') return <ToolRun key={`g${gi}`} tools={group.tools} />
          const b = group.block
          const i = gi
          /* The last thing you said is the only one worth offering to redo:
           * re-asking something from the middle of a conversation would send
           * it to the end anyway, where it no longer means the same thing. */
          const isLastUser = b.kind === 'user' && !blocks.slice(blocks.indexOf(b) + 1)
            .some((later) => later.kind === 'user')
          return renderBlock(b, i, isLastUser && !startedAt ? { onEdit, onRetry } : undefined)
        })}

        {/* Below the conversation, above the turn's closing line: it is a
            summary of what the session did, so it belongs where you land
            when you finish reading rather than at the top. */}
        {historyId != null && onOpenDoc && (
          <Artifacts sessionId={historyId} onOpen={onOpenDoc} />
        )}

        {startedAt != null ? (
          <Working key={startedAt} mode={mode} startedAt={startedAt} thinking={thinking} accent={accent} />
        ) : (
          lastTurn && (
            <Finished mode={mode} seconds={lastTurn.seconds} at={lastTurn.at} accent={accent} />
          )
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
        className="flex w-full items-center gap-[8px] rounded-[3px] px-[2px] py-[3px] text-left font-mono text-[12px] text-ink-faint hover:text-ink-dim"
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
function renderBlock(
  b: Block,
  i: number,
  redo?: { onEdit?: (text: string) => void; onRetry?: (text: string) => void },
) {
          if (b.kind === 'user') {
            /* A prompt glyph and dimmer ink instead of a YOU label: it is
             * already obvious which turn is yours, and a caption on every
             * one of them was two lines of furniture per exchange. The time
             * moves to a tooltip -- worth having, not worth a line. */
            return (
              <div key={i} className="group mb-[16px] flex gap-[9px]" title={b.at}>
                <span
                  aria-hidden
                  className="select-none font-mono text-[13px] leading-[1.6] text-ink-faint"
                >
                  ›
                </span>
                <div className="min-w-0 whitespace-pre-wrap font-mono text-[13px] leading-[1.6] text-ink-dim">
                  {b.text}
                </div>
                {/* On hover, and only on the last thing you said. The engine
                    cannot rewind a session, so neither of these replaces the
                    exchange -- they ask again with it still in view, which is
                    what actually happens and so what the UI should look like. */}
                {redo && (
                  <span className="ml-auto flex shrink-0 items-start gap-[4px] opacity-0 transition-opacity group-hover:opacity-100">
                    {redo.onEdit && (
                      <button
                        type="button"
                        onClick={() => redo.onEdit!(b.text)}
                        title="Put this back in the composer to rephrase"
                        className="rounded-[3px] px-[6px] py-[2px] font-mono text-[10.5px] text-ink-faint hover:bg-elevated hover:text-ink"
                      >
                        edit
                      </button>
                    )}
                    {redo.onRetry && (
                      <button
                        type="button"
                        onClick={() => redo.onRetry!(b.text)}
                        title="Ask this again"
                        className="rounded-[3px] px-[6px] py-[2px] font-mono text-[10.5px] text-ink-faint hover:bg-elevated hover:text-ink"
                      >
                        retry
                      </button>
                    )}
                  </span>
                )}
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
          if (b.kind === 'silent') {
            /* Deliberately plain, and deliberately not an error: the turn
             * did not fail, it just did not speak. What it needs to do is
             * end the ambiguity -- you are looking at a finished turn, not
             * a crash and not a pause. */
            const denied = b.denials ?? []
            return (
              <div
                key={i}
                className="mb-[16px] rounded-[3px] border border-dashed border-line font-mono text-[11px]"
              >
                <div className="flex items-center gap-[7px] px-[11px] py-[7px] text-ink-faint">
                  <span className="h-[5px] w-[5px] rounded-full bg-ink-faint" />
                  {denied.length > 0 ? 'turn ended blocked' : 'turn ended with no reply'}
                  <span className="text-ink-dim">
                    · {b.tools} tool {b.tools === 1 ? 'call' : 'calls'}, no text
                  </span>
                </div>
                {denied.length > 0 && (
                  /* The cause, not a footnote. A session refused its tools had
                   * nothing it could report -- naming the refusals turns an
                   * unexplained silence into something you can go and fix. */
                  <div className="border-t border-line px-[11px] py-[7px] text-ink-dim">
                    <div className="mb-[4px] uppercase tracking-[0.1em] text-ink-faint">
                      refused {denied.length} {denied.length === 1 ? 'tool' : 'tools'}
                    </div>
                    {denied.map((d, j) => (
                      <div key={j} className="truncate">
                        {d.tool}
                        {d.target && <span className="text-ink-faint"> · {d.target}</span>}
                      </div>
                    ))}
                  </div>
                )}
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
          return <Markdown key={i} src={b.text} className="mb-[18px]" />
}
