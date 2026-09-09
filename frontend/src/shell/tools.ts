/* Grouping consecutive tool calls into one line.
 *
 * A turn that runs eleven Bash commands produced eleven bordered boxes, each
 * with its own error text, and the reply that mattered was somewhere past
 * the bottom of the screen. The tool calls are almost never the point — they
 * are how the answer was reached, and they belong collapsed behind one line
 * that says what happened, openable when it matters.
 *
 * Kept out of the component so the summarising is testable: "Ran 3 shell
 * commands · read 2 files" has to stay true, and phrasing that quietly drops
 * or double-counts a call is worse than the boxes it replaced.
 */
import type { Block } from './domain'

export type ToolBlock = Extract<Block, { kind: 'tool' }>

/** How a tool is described in a summary line, singular and plural. */
const PHRASING: Record<string, [string, string]> = {
  Bash: ['ran 1 shell command', 'ran $n shell commands'],
  Read: ['read 1 file', 'read $n files'],
  Write: ['wrote 1 file', 'wrote $n files'],
  Edit: ['edited 1 file', 'edited $n files'],
  Grep: ['searched for 1 pattern', 'searched for $n patterns'],
  Glob: ['matched 1 path pattern', 'matched $n path patterns'],
  WebSearch: ['ran 1 web search', 'ran $n web searches'],
  WebFetch: ['fetched 1 page', 'fetched $n pages'],
  Task: ['ran 1 subagent', 'ran $n subagents'],
  ToolSearch: ['loaded 1 tool', 'loaded $n tools'],
}

/** A run of tool calls, plus whatever else the transcript holds. */
export type Grouped =
  | { kind: 'tools'; tools: ToolBlock[] }
  | { kind: 'other'; block: Block }

/** Fold consecutive tool blocks together; everything else passes through. */
export function groupTools(blocks: Block[]): Grouped[] {
  const out: Grouped[] = []
  for (const block of blocks) {
    if (block.kind === 'tool') {
      const last = out.at(-1)
      if (last?.kind === 'tools') last.tools.push(block)
      else out.push({ kind: 'tools', tools: [block] })
    } else {
      out.push({ kind: 'other', block })
    }
  }
  return out
}

/** "Ran 3 shell commands · read 2 files", capitalised.
 *
 * Counts by tool in the order each first appeared, so the sentence reads in
 * the order the work happened rather than alphabetically. */
export function summarise(tools: ToolBlock[]): string {
  const counts = new Map<string, number>()
  for (const t of tools) counts.set(t.name, (counts.get(t.name) ?? 0) + 1)

  const parts = [...counts].map(([name, n]) => {
    const phrasing = PHRASING[name]
    if (!phrasing) return n === 1 ? `used ${name}` : `used ${name} ${n}×`
    return (n === 1 ? phrasing[0] : phrasing[1]).replace('$n', String(n))
  })

  const line = parts.join(' · ')
  return line.charAt(0).toUpperCase() + line.slice(1)
}

/** How many of a run failed. Surfaced on the summary line, because a
 *  collapsed row that hides failures is how you miss that nothing ran. */
export const failures = (tools: ToolBlock[]): number =>
  tools.filter((t) => t.meta === 'error').length
