/* Whether an image is sitting in the clipboard.
 *
 * Only so the composer can say "there's an image, paste it" — the shell
 * never *takes* it. Reading is still what the paste does, on your keystroke.
 *
 * Deliberately image-only, enforced by the capability file rather than by
 * this code: clipboard text is where passwords, tokens and half the things
 * you copy in a day pass through, and an app that reads it to be helpful is
 * reading all of that too.
 */

const inTauri = () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

type Plugin = { readImage: () => Promise<{ rgba: () => Promise<Uint8Array> }> }

async function plugin(): Promise<Plugin | null> {
  if (!inTauri()) return null
  try {
    return (await import('@tauri-apps/plugin-clipboard-manager')) as unknown as Plugin
  } catch {
    return null
  }
}

/** True when the clipboard holds an image.
 *
 * The read throwing is the normal "no image" answer, not a fault: the plugin
 * has no "peek" that avoids reading, so absence arrives as an error.
 */
export async function hasImage(): Promise<boolean> {
  const p = await plugin()
  if (!p) return false
  try {
    await p.readImage()
    return true
  } catch {
    return false
  }
}
