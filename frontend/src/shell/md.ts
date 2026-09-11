/* Markdown → blocks, for the transcript and the panels.
 *
 * The previous renderer handled inline bold/code and split paragraphs on
 * blank lines, which is not what the model actually writes: replies use
 * headings, tight lists and fenced code, and single newlines throughout. So
 * "## What a session is" printed its own hashes, list items ran together
 * into one paragraph, and the inline regex mis-split around sequences like
 * `.**`, bleeding code styling across ordinary text.
 *
 * Parsing to a block tree rather than rendering inline is what makes it
 * testable: the shapes below are asserted directly, without a DOM.
 *
 * Deliberately no HTML: this parses model output, and the renderer builds
 * React elements from these nodes. Nothing here can inject markup, which a
 * `dangerouslySetInnerHTML`-based renderer would have to defend against.
 */

export type Block =
  | { type: 'heading'; depth: number; text: string }
  | { type: 'code'; lang: string; code: string }
  | { type: 'list'; ordered: boolean; start: number; items: string[] }
  | { type: 'quote'; text: string }
  | { type: 'rule' }
  | { type: 'table'; header: string[]; align: Align[]; rows: string[][] }
  | { type: 'paragraph'; text: string }

export type Align = 'left' | 'center' | 'right'

const HEADING = /^(#{1,6})\s+(.*)$/
const BULLET = /^[-*+]\s+(.*)$/
const ORDERED = /^(\d+)[.)]\s+(.*)$/
const FENCE = /^```(\w*)\s*$/
const QUOTE = /^>\s?(.*)$/
const RULE = /^(?:---+|\*\*\*+|___+)$/
const TABLE_DELIM = /^\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?$/

/** The cells of one row, with the optional outer pipes removed. */
function splitRow(line: string): string[] {
  return line.replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
}

/** `:---`, `---:` and `:---:` are left, right and centre respectively. */
function alignOf(spec: string): Align {
  const left = spec.startsWith(':')
  const right = spec.endsWith(':')
  if (left && right) return 'center'
  return right ? 'right' : 'left'
}

export function parseBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let paragraph: string[] = []

  const flush = () => {
    if (paragraph.length) {
      blocks.push({ type: 'paragraph', text: paragraph.join('\n') })
      paragraph = []
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()

    // Fenced code first: everything inside is literal, including lines that
    // would otherwise look like headings or list items.
    const fence = FENCE.exec(trimmed)
    if (fence) {
      flush()
      const lang = fence[1]
      const body: string[] = []
      i++
      while (i < lines.length && !FENCE.test(lines[i].trim())) body.push(lines[i++])
      blocks.push({ type: 'code', lang, code: body.join('\n') })
      continue
    }

    if (!trimmed) {
      flush()
      continue
    }

    if (RULE.test(trimmed)) {
      flush()
      blocks.push({ type: 'rule' })
      continue
    }

    /* Tables, recognised at the header row.
     *
     * A row is only a header if the line under it is a delimiter row, and
     * both lines have to carry a pipe -- that pair is the entire difference
     * between a table and an ordinary sentence containing a "|", so neither
     * line is consumed until both are confirmed. Without this the whole
     * table fell through to `paragraph` and rendered as raw pipes. */
    const delim = i + 1 < lines.length ? lines[i + 1].trim() : ''
    if (trimmed.includes('|') && delim.includes('|') && TABLE_DELIM.test(delim)) {
      flush()
      const header = splitRow(trimmed)
      const align = splitRow(lines[++i].trim()).map(alignOf)
      const rows: string[][] = []
      while (i + 1 < lines.length && lines[i + 1].trim().includes('|')) {
        const cells = splitRow(lines[++i].trim())
        // Ragged rows are padded, never dropped: a row with too few cells is
        // a flaw in the text, and showing it with blanks says so, where
        // silently discarding the row would hide it.
        while (cells.length < header.length) cells.push('')
        rows.push(cells.slice(0, header.length))
      }
      blocks.push({ type: 'table', header, align, rows })
      continue
    }

    const heading = HEADING.exec(trimmed)
    if (heading) {
      flush()
      blocks.push({ type: 'heading', depth: heading[1].length, text: heading[2] })
      continue
    }

    const quote = QUOTE.exec(trimmed)
    if (quote) {
      flush()
      const body = [quote[1]]
      // Consecutive quoted lines are one block, so a multi-line quotation
      // does not become a stack of separate bars.
      while (i + 1 < lines.length && QUOTE.test(lines[i + 1].trim())) {
        body.push(QUOTE.exec(lines[++i].trim())![1])
      }
      blocks.push({ type: 'quote', text: body.join('\n') })
      continue
    }

    const bullet = BULLET.exec(trimmed)
    const ordered = ORDERED.exec(trimmed)
    if (bullet || ordered) {
      flush()
      const isOrdered = Boolean(ordered)
      const start = ordered ? Number(ordered[1]) : 1
      const items: string[] = [ordered ? ordered[2] : bullet![1]]

      // Gather the rest of the run, and fold continuation lines into the
      // item they belong to -- a wrapped bullet is one item, not two.
      while (i + 1 < lines.length) {
        const nextRaw = lines[i + 1]
        const next = nextRaw.trim()
        if (!next) break
        const nb = BULLET.exec(next)
        const no = ORDERED.exec(next)
        if (isOrdered ? no : nb) {
          items.push(isOrdered ? no![2] : nb![1])
          i++
        } else if (nb || no || HEADING.test(next) || FENCE.test(next)) {
          break                      // a different block starts here
        } else if (/^\s+/.test(nextRaw)) {
          items[items.length - 1] += `\n${next}`   // indented continuation
          i++
        } else {
          break
        }
      }
      blocks.push({ type: 'list', ordered: isOrdered, start, items })
      continue
    }

    paragraph.push(trimmed)
  }

  flush()
  return blocks
}

export type Span =
  | { type: 'text'; text: string }
  | { type: 'code'; text: string }
  | { type: 'strong'; text: string }
  | { type: 'em'; text: string }
  | { type: 'link'; text: string; href: string }

/* Code is matched first so markdown inside a code span stays literal, and
 * bold before italic so `**x**` is not read as an empty italic wrapping one.
 * The italic rule requires a non-space after the opener, which is what stops
 * a lone `*` in prose from starting one that never closes. */
const INLINE = new RegExp(
  [
    '(`[^`]+`)',
    '(\\*\\*[^*]+?\\*\\*)',
    '(\\[[^\\]]+\\]\\([^)\\s]+\\))',
    '(\\*[^\\s*][^*]*?\\*)',
    '(__[^_]+?__)',
  ].join('|'),
  'g',
)

export function parseInline(text: string): Span[] {
  const spans: Span[] = []
  let last = 0

  for (const m of text.matchAll(INLINE)) {
    const at = m.index ?? 0
    if (at > last) spans.push({ type: 'text', text: text.slice(last, at) })
    const token = m[0]

    if (token.startsWith('`')) spans.push({ type: 'code', text: token.slice(1, -1) })
    else if (token.startsWith('**')) spans.push({ type: 'strong', text: token.slice(2, -2) })
    else if (token.startsWith('__')) spans.push({ type: 'strong', text: token.slice(2, -2) })
    else if (token.startsWith('[')) {
      const cut = token.indexOf('](')
      spans.push({ type: 'link', text: token.slice(1, cut), href: token.slice(cut + 2, -1) })
    } else spans.push({ type: 'em', text: token.slice(1, -1) })

    last = at + token.length
  }

  if (last < text.length) spans.push({ type: 'text', text: text.slice(last) })
  return spans
}
