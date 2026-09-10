/* Markdown rendering, shared by the transcript and the panels.
 *
 * Parsing lives in `md.ts` and is tested there; this file is only the
 * mapping from nodes to elements. The parser is *not* called markdown.ts:
 * on a case-insensitive filesystem that resolves ahead of this file, so
 * `./Markdown` imported the parser and the component vanished.
 *
 * React elements throughout — nothing is ever set as HTML, so model output
 * cannot inject markup.
 *
 * The typographic choices are what make a reply readable rather than merely
 * correct: headings that separate without shouting, lists whose markers sit
 * outside the text column so wrapped lines stay aligned, and code that reads
 * as a distinct object rather than as differently-coloured prose.
 */
import { useState } from 'react'
import { parseBlocks, parseInline, type Block, type Span } from './md'

export function Markdown({ src, className = '' }: { src: string; className?: string }) {
  return (
    <div className={className}>
      {parseBlocks(src).map((block, i) => (
        <Node key={i} block={block} first={i === 0} />
      ))}
    </div>
  )
}

function Node({ block, first }: { block: Block; first: boolean }) {
  switch (block.type) {
    case 'heading':
      /* Small caps rather than large type. A reply is not a document, and a
       * 24px heading inside a chat turn shouts over the prose it introduces;
       * the job is separation, which weight and space do on their own. */
      return (
        <div
          className={`mb-[6px] font-mono text-[11px] font-bold uppercase tracking-[0.12em] text-ink-faint ${
            first ? '' : 'mt-[16px]'
          }`}
        >
          <Inline text={block.text} />
        </div>
      )

    case 'code':
      return <CodeBlock code={block.code} />

    case 'list': {
      const Tag = block.ordered ? 'ol' : 'ul'
      return (
        /* Markers outside the text column, so a wrapped line aligns with the
         * text above it instead of with the bullet. */
        <Tag
          start={block.ordered ? block.start : undefined}
          className={`mb-[10px] ml-[18px] list-outside space-y-[4px] text-[13.5px] leading-[1.6] ${
            block.ordered ? 'list-decimal' : 'list-disc'
          } marker:text-ink-faint`}
        >
          {block.items.map((item, i) => (
            <li key={i} className="pl-[3px]">
              <Inline text={item} />
            </li>
          ))}
        </Tag>
      )
    }

    case 'quote':
      return (
        <blockquote className="mb-[10px] border-l-2 border-line pl-[11px] text-[13px] leading-[1.6] text-ink-dim">
          <Inline text={block.text} />
        </blockquote>
      )

    case 'rule':
      return <hr className="my-[14px] border-0 border-t border-line" />

    case 'paragraph':
      return (
        <p className="m-0 mb-[9px] whitespace-pre-wrap text-[13.5px] leading-[1.65] last:mb-0">
          <Inline text={block.text} />
        </p>
      )
  }
}

function Inline({ text }: { text: string }) {
  return <>{parseInline(text).map((span, i) => renderSpan(span, i))}</>
}

function renderSpan(span: Span, key: number) {
  switch (span.type) {
    case 'code':
      return (
        <code
          key={key}
          className="rounded-[3px] border border-line bg-elevated px-[4px] py-px font-mono text-[0.87em] text-ink"
        >
          {span.text}
        </code>
      )
    case 'strong':
      return <strong key={key} className="font-semibold text-white">{span.text}</strong>
    case 'em':
      return <em key={key} className="text-ink-dim">{span.text}</em>
    case 'link':
      // No target/rel juggling: there is no browser here to open a tab in,
      // and a link that silently does nothing is better than one that
      // navigates the shell away from itself.
      return (
        <span key={key} className="text-noctua underline decoration-line underline-offset-2">
          {span.text}
        </span>
      )
    default:
      return <span key={key}>{span.text}</span>
  }
}


/* A code block you can take.
 *
 * Most of these are commands meant to be run somewhere else, and selecting
 * one by dragging is fiddly in a transcript that scrolls — the whole reason
 * the block is visually separate is that it is a thing to lift out.
 *
 * The button sits inside the block rather than beside it, so a long line
 * scrolling horizontally cannot push it off the edge, and it only appears on
 * hover: on a screen of code blocks a permanent button on each is more
 * furniture than help.
 */
function CodeBlock({ code }: { code: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      // Long enough to read, short enough that the block is ready again
      // before you would reach for it a second time.
      setTimeout(() => setCopied(false), 1400)
    } catch {
      // A refused clipboard is not worth an error state: the text is right
      // there and still selectable.
    }
  }

  return (
    <div className="group relative mb-[10px] mt-[2px]">
      <pre className="overflow-x-auto rounded-[4px] border border-line bg-ground py-[9px] pl-[11px] pr-[64px] font-mono text-[11.5px] leading-[1.6] text-ink-dim">
        <code>{code}</code>
      </pre>
      <button
        type="button"
        onClick={copy}
        aria-label="Copy to clipboard"
        className={`absolute right-[7px] top-[6px] rounded-[3px] border border-line bg-surface px-[7px] py-[2px] font-mono text-[10.5px] transition-opacity ${
          copied
            ? 'text-good opacity-100'
            : 'text-ink-faint opacity-0 hover:text-ink group-hover:opacity-100 focus-visible:opacity-100'
        }`}
      >
        {copied ? 'copied' : 'copy'}
      </button>
    </div>
  )
}
