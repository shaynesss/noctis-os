import { describe, expect, it } from 'vitest'
import { launchAtLoginOnce } from './host'

const memory = () => {
  const m = new Map<string, string>()
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v) } }
}

describe('launch at login', () => {
  it('is switched on once, and not again after that', async () => {
    let on = false
    const autostart = { isEnabled: async () => on, enable: async () => { on = true } }
    const store = memory()
    expect(await launchAtLoginOnce(autostart, store)).toBe('enabled')
    on = false                                  // turned off in System Settings
    expect(await launchAtLoginOnce(autostart, store)).toBe('skipped')
    expect(on).toBe(false)
  })

  it('leaves an already-enabled login item alone, and survives a failure', async () => {
    expect(await launchAtLoginOnce({ isEnabled: async () => true, enable: async () => { throw new Error('no') } }, memory()))
      .toBe('already')
    expect(await launchAtLoginOnce({ isEnabled: async () => { throw new Error('ipc') }, enable: async () => {} }, memory()))
      .toBe('skipped')
  })
})
