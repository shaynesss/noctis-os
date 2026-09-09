/* The summariser is the part with judgement in it, so it is the part
 * tested: a notification body that quotes markdown syntax or an empty first
 * line is worse than no notification. */
import { describe, expect, it } from 'vitest'
import { _internal } from './notify'

const { summarise } = _internal

describe('summarise', () => {
  it('takes the first line with content, not the first line', () => {
    // Replies routinely open on a blank line, which would notify you with
    // nothing at all.
    expect(summarise('\n\n  \nBergen is wet today.\nMore detail.')).toBe('Bergen is wet today.')
  })

  it('strips markdown so the body reads as prose', () => {
    expect(summarise('**Done** — fixed the `parser` bug')).toBe('Done — fixed the parser bug')
  })

  it('truncates long lines with an ellipsis', () => {
    const out = summarise('x'.repeat(300))
    expect(out).toHaveLength(140)
    expect(out.endsWith('…')).toBe(true)
  })

  it('leaves a line at the limit alone', () => {
    expect(summarise('y'.repeat(140))).toBe('y'.repeat(140))
  })

  it('returns empty for text with nothing in it, so the caller can fall back', () => {
    expect(summarise('   \n\n  ')).toBe('')
  })
})
