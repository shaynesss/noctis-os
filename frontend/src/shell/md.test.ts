/* Parser tests, using the shapes from a real reply that rendered badly:
 * headings printed their own hashes, list items ran together into one
 * paragraph, and inline styling bled across text at sequences like `.**`. */
import { describe, expect, it } from 'vitest'
import { parseBlocks, parseInline } from './md'

describe('parseBlocks', () => {
  it('reads a heading instead of printing its hashes', () => {
    expect(parseBlocks('## What a session actually is')).toEqual([
      { type: 'heading', depth: 2, text: 'What a session actually is' },
    ])
  })

  it('keeps a run of bullets as one list, not one paragraph', () => {
    // These arrived on consecutive lines with no blank line between them,
    // which is why they used to render as a single run-on paragraph.
    const blocks = parseBlocks('- Mid-turn: aborts the fetch\n- Idle: nothing to kill\n- Either way: it stays')
    expect(blocks).toHaveLength(1)
    expect(blocks[0]).toMatchObject({ type: 'list', ordered: false })
    expect((blocks[0] as { items: string[] }).items).toHaveLength(3)
  })

  it('reads a numbered list and keeps its starting number', () => {
    const blocks = parseBlocks('2. second\n3. third')
    expect(blocks[0]).toMatchObject({ type: 'list', ordered: true, start: 2 })
  })

  it('folds a wrapped bullet into the item it belongs to', () => {
    const blocks = parseBlocks('- first line\n  continues here\n- second')
    expect((blocks[0] as { items: string[] }).items).toEqual(['first line\ncontinues here', 'second'])
  })

  it('keeps fenced code literal, hashes and dashes included', () => {
    const blocks = parseBlocks('text\n\n```py\n# not a heading\n- not a bullet\n```\nafter')
    expect(blocks[1]).toEqual({ type: 'code', lang: 'py', code: '# not a heading\n- not a bullet' })
    expect(blocks[2]).toMatchObject({ type: 'paragraph', text: 'after' })
  })

  it('joins consecutive quoted lines into one block', () => {
    const blocks = parseBlocks('> one\n> two')
    expect(blocks).toEqual([{ type: 'quote', text: 'one\ntwo' }])
  })

  it('separates a heading that follows a paragraph with no blank line', () => {
    const blocks = parseBlocks('Traced it. Short version.\n## What a session is\nThere is no process.')
    expect(blocks.map((b) => b.type)).toEqual(['paragraph', 'heading', 'paragraph'])
  })

  it('reads a horizontal rule', () => {
    expect(parseBlocks('---')).toEqual([{ type: 'rule' }])
  })
})

describe('parseInline', () => {
  it('does not let bold bleed across a following full stop', () => {
    // The old regex matched from the ** in "gitignored.**" onwards, which is
    // how code styling ended up running through ordinary prose.
    const spans = parseInline('`history.db` is not gitignored.** `.gitignore` has no entry')
    expect(spans.filter((s) => s.type === 'code').map((s) => s.text))
      .toEqual(['history.db', '.gitignore'])
  })

  it('keeps markdown inside code spans literal', () => {
    expect(parseInline('`**not bold**`')).toEqual([{ type: 'code', text: '**not bold**' }])
  })

  it('reads bold, italic and code together', () => {
    const spans = parseInline('**bold** then *thin* then `code`')
    expect(spans.map((s) => s.type)).toEqual(['strong', 'text', 'em', 'text', 'code'])
  })

  it('reads a link', () => {
    expect(parseInline('see [yr.no](https://yr.no) for it')[1])
      .toEqual({ type: 'link', text: 'yr.no', href: 'https://yr.no' })
  })

  it('leaves a lone asterisk alone rather than opening an italic', () => {
    expect(parseInline('2 * 3 = 6')).toEqual([{ type: 'text', text: '2 * 3 = 6' }])
  })

  it('returns plain text unchanged', () => {
    expect(parseInline('nothing special')).toEqual([{ type: 'text', text: 'nothing special' }])
  })
})

/* The activity grid's date handling, which produced "0 sessions in the last
 * year" while the backend was returning rows for today. */
import { buildGrid } from './grid'

describe('activity grid', () => {
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

  it("counts sessions recorded today", () => {
    // The grid used a hardcoded date, so anything after it was treated as
    // future and forced to zero -- which is every real session.
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const weeks = buildGrid(today, new Map([[iso(today), 10]]))
    expect(weeks.flat().reduce((n, c) => n + c.count, 0)).toBe(10)
  })

  it('counts yesterday too', () => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const y = new Date(today)
    y.setDate(y.getDate() - 1)
    const weeks = buildGrid(today, new Map([[iso(y), 3]]))
    expect(weeks.flat().reduce((n, c) => n + c.count, 0)).toBe(3)
  })

  it('leaves future days empty and marked', () => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const tomorrow = new Date(today)
    tomorrow.setDate(tomorrow.getDate() + 1)
    const weeks = buildGrid(today, new Map([[iso(tomorrow), 99]]))
    expect(weeks.flat().reduce((n, c) => n + c.count, 0)).toBe(0)
    expect(weeks.flat().some((c) => c.future)).toBe(true)
  })
})
