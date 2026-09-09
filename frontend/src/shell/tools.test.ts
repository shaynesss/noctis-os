/* The summary line has to stay true: phrasing that drops or double-counts a
 * call is worse than the eleven boxes it replaced. */
import { describe, expect, it } from 'vitest'
import { failures, groupTools, summarise, type ToolBlock } from './tools'
import type { Block } from './mock'

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
