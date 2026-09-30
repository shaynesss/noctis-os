import { describe, expect, it, vi } from 'vitest'

vi.mock('./engine', () => ({
  upload: vi.fn(async (path: string) =>
    path.includes('bad') ? { error: 'is over 50MB' } : { path: `/r/drops/20260930-${decodeURIComponent(path.split('name=')[1])}` }),
}))

import { attachFiles, escapePath, registerPaster } from './attach'

describe('attach', () => {
  it('escapes a path the way a terminal types a dropped file', () => {
    expect(escapePath('/a b/c(1).png')).toBe('/a\\ b/c\\(1\\).png')
    expect(escapePath('/plain/x.png')).toBe('/plain/x.png')
  })

  it('pastes every kept path into the terminal it was dropped on', async () => {
    const pasted: string[] = []
    const off = registerPaster('term-1', (t) => pasted.push(t))
    expect(await attachFiles('term-1', [new File(['x'], 'a.png'), new File(['y'], 'b.txt')])).toBeNull()
    expect(pasted).toEqual(['/r/drops/20260930-a.png /r/drops/20260930-b.txt '])
    off()
    expect(await attachFiles('term-1', [new File(['x'], 'a.png')])).toBe('that terminal is not open')
  })

  it('pastes nothing when a file is refused, and says which', async () => {
    const pasted: string[] = []
    registerPaster('term-2', (t) => pasted.push(t))
    expect(await attachFiles('term-2', [new File(['x'], 'bad.bin')])).toBe('bad.bin: is over 50MB')
    expect(pasted).toEqual([])
  })
})
