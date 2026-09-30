import { describe, expect, it, vi } from 'vitest'

vi.mock('./engine', () => ({ get: vi.fn(), put: vi.fn(async () => true) }))

import { rememberSlots, validSlots } from './domain'

describe('the remembered arrangement', () => {
  it('sends the backend a copy only when it changed', () => {
    const sent: unknown[] = []
    const send = (s: readonly unknown[]) => { sent.push(s) }
    const tabs = [{ mode: 'faber' as const, cwd: '/x', sessionId: 'abc', id: 'term-1' }]
    rememberSlots(tabs, send)
    rememberSlots([...tabs], send)             // the same list, re-saved on a status report
    rememberSlots([{ ...tabs[0], sessionId: 'def' }], send)
    expect(sent).toHaveLength(2)
  })

  it('keeps what recall would keep, and drops the rest', () => {
    expect(validSlots([{ mode: 'general', cwd: '/y' }, { mode: 3, cwd: '/z' }, 'junk', null]))
      .toEqual([{ mode: 'general', cwd: '/y' }])
    expect(validSlots({ not: 'a list' })).toEqual([])
  })
})
