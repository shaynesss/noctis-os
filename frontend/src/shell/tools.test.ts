/* The summary line has to stay true: phrasing that drops or double-counts a
 * call is worse than the eleven boxes it replaced. */
import { describe, expect, it } from 'vitest'
import { failures, groupTools, summarise, type ToolBlock } from './tools'
import type { Block } from './domain'

const tool = (name: string, meta = 'done'): Block =>
  ({ kind: 'tool', id: Math.random().toString(36), name, target: '', meta, body: '' })

describe('groupTools', () => {
  it('folds a run of tool calls into one group', () => {
    const grouped = groupTools([tool('Bash'), tool('Bash'), tool('Read')])
    expect(grouped).toHaveLength(1)
    expect(grouped[0].kind).toBe('tools')
  })

  it('does not fold across the text between two runs', () => {
    // The text is why there are two runs; merging them would claim the model
    // did all of it before saying anything.
    const grouped = groupTools([tool('Bash'), { kind: 'text', text: 'then' }, tool('Bash')])
    expect(grouped.map((g) => g.kind)).toEqual(['tools', 'other', 'tools'])
  })

  it('passes non-tool blocks through untouched', () => {
    const user: Block = { kind: 'user', text: 'hi', at: '12:00' }
    expect(groupTools([user])).toEqual([{ kind: 'other', block: user }])
  })

  it('returns nothing for an empty transcript', () => {
    expect(groupTools([])).toEqual([])
  })

  it('drops a thinking block that reports nothing, and folds across it', () => {
    // The row would read "Thinking · 0 tokens · 0.0s" -- no information, and
    // it splits one stretch of work into two runs.
    const empty: Block = { kind: 'thinking', tokens: 0, ms: 0 }
    const grouped = groupTools([tool('Bash'), empty, tool('Grep')])
    expect(grouped).toHaveLength(1)
    expect(grouped[0]).toMatchObject({ kind: 'tools' })
    expect(summarise((grouped[0] as { tools: ToolBlock[] }).tools))
      .toBe('Ran 1 shell command · searched for 1 pattern')
  })

  it('keeps a thinking block that has real numbers', () => {
    const real: Block = { kind: 'thinking', tokens: 412, ms: 2300 }
    expect(groupTools([tool('Bash'), real, tool('Grep')]).map((g) => g.kind))
      .toEqual(['tools', 'other', 'tools'])
  })
})

describe('summarise', () => {
  const tools = (...names: string[]) => names.map((n) => tool(n) as ToolBlock)

  it('counts each tool and reads in the order the work happened', () => {
    expect(summarise(tools('Grep', 'Bash', 'Bash', 'Bash')))
      .toBe('Searched for 1 pattern · ran 3 shell commands')
  })

  it('uses the singular for one', () => {
    expect(summarise(tools('Bash'))).toBe('Ran 1 shell command')
  })

  it('names an unknown tool rather than dropping it', () => {
    // Silently omitting a call would make the line a lie about what ran.
    expect(summarise(tools('NotebookEdit'))).toBe('Used NotebookEdit')
    expect(summarise(tools('NotebookEdit', 'NotebookEdit'))).toBe('Used NotebookEdit 2×')
  })

  it('counts every call in a long mixed run', () => {
    const line = summarise(tools('Bash', 'Read', 'Bash', 'Read', 'Read'))
    expect(line).toBe('Ran 2 shell commands · read 3 files')
  })
})

describe('failures', () => {
  it('counts the failed calls, because a collapsed row must not hide them', () => {
    expect(failures([tool('Bash', 'error'), tool('Bash'), tool('Read', 'error')] as ToolBlock[]))
      .toBe(2)
  })
})

/* Which message gets the edit/retry controls. The engine cannot rewind a
 * session, so these ask again rather than replace — and offering them on a
 * message from the middle of a conversation would send it to the end, where
 * it no longer means the same thing. */
describe('which message can be redone', () => {
  const lastUserIndex = (blocks: Block[]) =>
    blocks.reduce((last, b, i) => (b.kind === 'user' ? i : last), -1)

  it('is the last thing you said', () => {
    const blocks: Block[] = [
      { kind: 'user', text: 'first', at: '10:00' },
      { kind: 'text', text: 'a reply' },
      { kind: 'user', text: 'second', at: '10:01' },
      { kind: 'text', text: 'another reply' },
    ]
    expect(lastUserIndex(blocks)).toBe(2)
  })

  it('is still the last one when a reply followed it', () => {
    const blocks: Block[] = [
      { kind: 'user', text: 'only', at: '10:00' },
      { kind: 'text', text: 'reply' },
    ]
    expect(lastUserIndex(blocks)).toBe(0)
  })

  it('is nothing in a conversation with no messages from you', () => {
    expect(lastUserIndex([{ kind: 'text', text: 'unprompted' }])).toBe(-1)
  })
})

/* Scroll behaviour. Following output and preserving position conflict, so
 * the rule has to be explicit: follow only while already at the bottom.
 * Yanking the view down while someone reads further up is worse than not
 * following at all. */
describe('scroll following', () => {
  const NEAR_BOTTOM = 60
  const atBottom = (scrollHeight: number, scrollTop: number, clientHeight: number) =>
    scrollHeight - scrollTop - clientHeight <= NEAR_BOTTOM

  it('follows when pinned to the bottom', () => {
    expect(atBottom(1000, 600, 400)).toBe(true)
  })

  it('still follows within a couple of lines of the bottom', () => {
    // Slack, so a stray pixel or an image finishing loading does not
    // silently stop the follow.
    expect(atBottom(1000, 560, 400)).toBe(true)
  })

  it('does not follow when reading further up', () => {
    expect(atBottom(1000, 200, 400)).toBe(false)
  })

  it('treats a transcript shorter than the viewport as at the bottom', () => {
    expect(atBottom(300, 0, 400)).toBe(true)
  })
})
