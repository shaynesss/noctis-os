/* Desktop notifications when a turn finishes.
 *
 * The premise of v2 is being one keystroke away: the window hides rather
 * than quits, and Opt+Space brings it back. That only works if you can leave
 * — and a Faber turn running for minutes with nothing to tell you it landed
 * means either sitting and watching it or forgetting it entirely. This is
 * the half that makes hiding the window safe.
 *
 * Everything here degrades to nothing outside Tauri: the dev server in a
 * browser has no notification plugin, and a shell that throws there would be
 * harder to work on for a feature you cannot see anyway.
 */
import type { Mode } from './mock'
import { MODE_LABEL } from './mock'

/** True in the desktop shell, false in a plain browser tab. */
const inTauri = () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

type Plugin = {
  isPermissionGranted: () => Promise<boolean>
  requestPermission: () => Promise<string>
  sendNotification: (o: { title: string; body: string }) => void
}

/* Imported lazily and only inside Tauri. A static import would pull the
 * plugin into the browser build too, where its first call throws. */
async function plugin(): Promise<Plugin | null> {
  if (!inTauri()) return null
  try {
    return (await import('@tauri-apps/plugin-notification')) as unknown as Plugin
  } catch {
    return null
  }
}

let granted: boolean | null = null

/** Ask once, lazily.
 *
 * Deliberately not on startup: a permission dialog before you have done
 * anything is the kind of thing people deny reflexively, and a denial is
 * far harder to reverse than a delay. Asked instead the first time a turn
 * actually finishes, when the reason for it is on screen.
 */
async function allowed(p: Plugin): Promise<boolean> {
  if (granted !== null) return granted
  granted = await p.isPermissionGranted()
  if (!granted) granted = (await p.requestPermission()) === 'granted'
  return granted
}

/** A short, useful body: what the session said, not that it finished.
 *
 * "Faber finished" tells you nothing you did not already know. The opening
 * line of the reply is what lets you decide whether to go back at all. */
function summarise(text: string, limit = 140): string {
  const firstLine = text.trim().split('\n').find((l) => l.trim()) ?? ''
  const clean = firstLine.replace(/[*`#>]/g, '').trim()
  return clean.length > limit ? `${clean.slice(0, limit - 1)}…` : clean
}

export interface TurnResult {
  mode: Mode
  /** The reply's text, for the body. Empty when the turn produced none. */
  text: string
  /** Seconds the turn took. */
  seconds: number
  failed?: boolean
}

/** Notify that a turn finished, if the window is not already in front.
 *
 * The focus check is the whole point: notifying about something you are
 * looking at is noise, and noise is how notifications get turned off.
 */
export async function turnFinished(result: TurnResult): Promise<void> {
  if (typeof document !== 'undefined' && document.hasFocus()) return

  const p = await plugin()
  if (!p || !(await allowed(p))) return

  const label = MODE_LABEL[result.mode]
  const took = result.seconds < 60
    ? `${Math.round(result.seconds)}s`
    : `${Math.floor(result.seconds / 60)}m ${Math.round(result.seconds % 60)}s`

  p.sendNotification({
    title: result.failed ? `${label} failed · ${took}` : `${label} · ${took}`,
    // Falls back to naming the outcome when there is no text to quote --
    // a tool-only turn, or one that was stopped.
    body: summarise(result.text) || (result.failed ? 'The session ended early.' : 'Turn finished.'),
  })
}

export const _internal = { summarise }
