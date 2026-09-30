/* What the host does for the page that a browser would do itself. */
import { invoke } from '@tauri-apps/api/core'

/** Whether the page is inside the Tauri shell rather than a plain browser
 *  (the Playwright loop, a dev tab). */
export const inTauri = (): boolean => '__TAURI_INTERNALS__' in window

/** Open a link in the person's browser. The webview does not honour
 *  `target="_blank"`, so an ordinary anchor did nothing; the shell's
 *  `open_url` command hands the link to the OS. http(s) only. */
export function openExternal(url: string): void {
  if (!/^https?:\/\//.test(url)) return
  const fallback = () => { window.open(url, '_blank', 'noopener') }
  if (inTauri()) void invoke('open_url', { url }).catch(fallback)
  else fallback()
}

const AUTOSTART_KEY = 'noctis.launch-at-login-set'

/** Open at login, switched on once (2026-09-30, Shayne's call).
 *
 * The spec calls the app an always-there front door, and the autostart
 * plugin was registered and granted without anything ever enabling it. Only
 * the packaged app does this: the dev window is a debug binary under
 * `tauri dev`, which is no thing to start at login. And only once: turned
 * off later in System Settings, it stays off. */
export async function launchAtLoginOnce(
  autostart: { isEnabled: () => Promise<boolean>; enable: () => Promise<void> },
  storage: Pick<Storage, 'getItem' | 'setItem'> = localStorage,
): Promise<'enabled' | 'already' | 'skipped'> {
  try {
    if (storage.getItem(AUTOSTART_KEY)) return 'skipped'
    const was = await autostart.isEnabled()
    if (!was) await autostart.enable()
    storage.setItem(AUTOSTART_KEY, new Date().toISOString())
    return was ? 'already' : 'enabled'
  } catch {
    return 'skipped'  // a window that cannot set it still works
  }
}
