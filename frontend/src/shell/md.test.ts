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

  it('reads a table, with alignment', () => {
    const blocks = parseBlocks('| # | Item | State |\n|---|:----:|------:|\n| 3 | Dialog | done |')
    expect(blocks).toEqual([{
      type: 'table',
      header: ['#', 'Item', 'State'],
      align: ['left', 'center', 'right'],
      rows: [['3', 'Dialog', 'done']],
    }])
  })

  it('pads a row with too few cells rather than dropping it', () => {
    const blocks = parseBlocks('| a | b |\n|---|---|\n| 1 |')
    expect(blocks[0]).toMatchObject({ rows: [['1', '']] })
  })

  it('leaves a sentence containing a pipe as a paragraph', () => {
    // The delimiter row is the whole difference; without one there is no
    // table, however many pipes the prose happens to contain.
    expect(parseBlocks('Run a | b to pipe it.').map((b) => b.type)).toEqual(['paragraph'])
  })

  it('does not turn a paragraph followed by a rule into a table', () => {
    const blocks = parseBlocks('Piped a | b here.\n---')
    expect(blocks.map((b) => b.type)).toEqual(['paragraph', 'rule'])
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
    /* A fixed Wednesday, not `new Date()`. The grid is 53 weeks from
     * `today - 364 - today.getDay()`, so it ends on the last day of the
     * current week and there are `6 - getDay()` future cells -- which is
     * zero on a Saturday. This assertion therefore failed one day in seven,
     * and did, on 2026-09-12. The grid is right; the test was reading the
     * clock. */
    const today = new Date(2026, 8, 9)     // Wed 2026-09-09
    const tomorrow = new Date(today)
    tomorrow.setDate(tomorrow.getDate() + 1)
    const weeks = buildGrid(today, new Map([[iso(tomorrow), 99]]))
    expect(weeks.flat().reduce((n, c) => n + c.count, 0)).toBe(0)
    expect(weeks.flat().some((c) => c.future)).toBe(true)
  })

  it('has no future cells when today is the last day of the week', () => {
    /* The Saturday case the test above used to hit by accident. Not a bug:
     * the week is complete, so there is nothing ahead of today to mark. */
    const saturday = new Date(2026, 8, 12)
    expect(saturday.getDay()).toBe(6)
    const weeks = buildGrid(saturday, new Map())
    expect(weeks.flat().some((c) => c.future)).toBe(false)
    expect(weeks.flat().at(-1)!.date.getDate()).toBe(12)
  })
})

/* A guard for a mistake I made three times in one session: a lowercase
 * module beside a same-named component file. On a case-insensitive
 * filesystem the wrong one wins the import, and the failure is a build error
 * or — worse — a dev server serving the stale module and a blank window. */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

describe('module names', () => {
  it('has no two files whose names differ only by case', () => {
    const dir = join(process.cwd(), 'src', 'shell')
    const seen = new Map<string, string>()
    for (const file of readdirSync(dir)) {
      const stem = file.replace(/\.(tsx?|css)$/, '').toLowerCase()
      const previous = seen.get(stem)
      expect(previous, `${previous} and ${file} collide on a case-insensitive filesystem`)
        .toBeUndefined()
      seen.set(stem, file)
    }
  })
})

/* A font can be vendored, shipped and never loaded. JetBrains Mono was: its
 * @font-face lived in v1's index.css, which stopped being imported at the v2
 * cutover, so the app fell through to Menlo while serving a 92KB file
 * nothing referenced. Nothing failed — it just quietly looked wrong. */
describe('fonts', () => {
  it('declares every vendored font the loaded stylesheet uses', () => {
    const fontsDir = join(process.cwd(), 'public', 'fonts')
    const css = readFileSync(join(process.cwd(), 'src', 'shell', 'tokens.css'), 'utf8')

    // The families the stylesheet asks for, from --font-mono / --font-sans.
    const requested = [...css.matchAll(/"([A-Za-z][A-Za-z0-9 ]+)"/g)].map((m) => m[1])

    for (const file of readdirSync(fontsDir)) {
      if (!/\.(woff2?|ttf)$/.test(file)) continue
      // Extension first, then any -Weight suffix: stripping from the first
      // hyphen alone leaves "CascadiaCode.woff2", which matches no family
      // and silently skips the file this test exists to check.
      const family = file.replace(/\.(woff2?|ttf)$/, '').replace(/-.*$/, '')
      const wanted = requested.some((r) => r.replace(/\s/g, '').startsWith(family))
      if (!wanted) continue                            // retired, kept until the v1 cutover
      expect(css, `${file} is vendored and requested but never declared`).toContain(file)
    }
  })
})
