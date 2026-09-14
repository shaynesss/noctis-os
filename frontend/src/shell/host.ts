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
