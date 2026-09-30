/* Files into a session: a drop on a terminal, or its attach button.
 *
 * A terminal given a dropped file types the file's path, and Claude Code
 * turns an image path into an attached image. This window cannot do that
 * the direct way: the webview owns drag and drop (the tab strip reorders
 * with it, `dragDropEnabled: false`), and a web page is told what a dropped
 * file contains, never where it lives. So the bytes go to the backend,
 * which keeps a copy under `backend/runtime/drops/`, and the path it
 * returns is pasted into the terminal the way a terminal would paste it.
 * The session reads the copy.
 */
import { upload } from './engine'

/** Each mounted terminal's way to paste, by slot id. A paste goes through
 *  xterm, so it honours the CLI's bracketed-paste mode and arrives the way
 *  a real terminal's paste would. */
/** A mounted terminal's paste, and whether its session is still running:
 *  an ended one keeps its pane (and its `r` to restart) but cannot take
 *  a file, and a drop on it said nothing (review, 2026-09-30). */
interface Paster { paste: (text: string) => void; alive: () => boolean }
const pasters = new Map<string, Paster>()

export function registerPaster(id: string, paste: (text: string) => void,
                               alive: () => boolean = () => true): () => void {
  const entry = { paste, alive }
  pasters.set(id, entry)
  return () => { if (pasters.get(id) === entry) pasters.delete(id) }
}

/** A path as a terminal types a dropped file: backslash before anything a
 *  shell or the CLI would read as syntax. */
export function escapePath(p: string): string {
  return p.replace(/([ \\'"()&;$`!*?[\]{}<>|#~])/g, '\\$1')
}

export async function attachFiles(id: string, files: File[]): Promise<string | null> {
  const target = pasters.get(id)
  if (!target) return 'that terminal is not open'
  if (!target.alive()) return 'that session has ended (press r in it to start a new one)'
  if (!files.length) return null
  const kept: string[] = []
  for (const f of files) {
    const out = await upload(`/v2/sessions/attach?name=${encodeURIComponent(f.name || 'file')}`, f)
    if ('error' in out) return `${f.name}: ${out.error}`
    kept.push(escapePath(out.path))
  }
  target.paste(kept.join(' ') + ' ')
  return null
}

export const carriesFiles = (e: { dataTransfer: DataTransfer | null }) =>
  e.dataTransfer?.types?.includes('Files') ?? false
