/* A real Claude Code session, hosted in the shell.
 *
 * The transcript beside this one is built from `stream-json` events: Noctis
 * drives `claude -p` — "print response and exit" — once per turn and rebuilds
 * the interactive loop on top of it. This runs the CLI the way a terminal
 * does, so the loop is the CLI's own.
 *
 * Both exist at once, deliberately. `PTY-MIGRATION.md` §7 sequences it that
 * way: the 2026-09-12 cutover deleted `launch_config/` while a guard still
 * required it and broke every spawn, and the lesson was that a path gets
 * removed only once nothing reads it.
 *
 * xterm.js ships no look of its own, so the theme below is generated from
 * `tokens.css` rather than written twice — one source of truth for what
 * `ink-dim` is, whether it lands in a card or in a terminal cell.
 */
import { useEffect, useRef } from 'react'
import { Terminal as Xterm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebglAddon } from '@xterm/addon-webgl'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import '@xterm/xterm/css/xterm.css'
import { get } from './engine'
import type { Mode } from './domain'

/** Read a design token, so the terminal cannot drift from the rest of the UI. */
const token = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback

/* The palette, from the shell's own tokens.
 *
 * The sixteen ANSI slots are what a terminal program actually addresses: the
 * CLI decides *that* a line is yellow, this decides what yellow is. Mapping
 * them onto the character accents is what makes a Faber terminal read as
 * Faber rather than as a terminal that happens to be inside Noctis. */
const theme = (accent: string) => ({
  background: token('--color-ground', '#0f0f0f'),
  foreground: token('--color-ink', '#cccccc'),
  cursor: accent,
  cursorAccent: token('--color-ground', '#0f0f0f'),
  selectionBackground: token('--color-elevated', '#1c1c1c'),
  selectionForeground: token('--color-ink', '#cccccc'),
  selectionInactiveBackground: token('--color-line', '#2a2a2a'),

  black: token('--color-line', '#2a2a2a'),
  red: token('--color-faber', '#e53311'),
  green: token('--color-good', '#3fa463'),
  yellow: token('--color-noctua', '#eca207'),
  blue: '#5a8ad6',
  magenta: token('--color-vesper', '#953ead'),
  cyan: '#3fa39c',
  white: token('--color-ink-dim', '#8a8a8a'),

  brightBlack: token('--color-ink-faint', '#6a6a6a'),
  brightRed: '#ff5c3d',
  brightGreen: '#54c67e',
  brightYellow: token('--color-maint', '#da5b00'),
  brightBlue: '#7aa7ea',
  brightMagenta: '#b662d0',
  brightCyan: '#5cc4bc',
  brightWhite: '#ffffff',

  scrollbarSliderBackground: token('--color-line-soft', '#212121'),
  scrollbarSliderHoverBackground: token('--color-line', '#2a2a2a'),
  scrollbarSliderActiveBackground: token('--color-ink-faint', '#6a6a6a'),
})

export function Terminal({
  id, mode, cwd, accent, onExit,
}: {
  id: string
  mode: Mode
  cwd: string
  accent: string
  onExit?: () => void
}) {
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = host.current
    if (!el) return
    let live = true
    let term: Xterm | undefined
    let webgl: WebglAddon | undefined
    const cleanups: Array<() => void> = []

    /* Teardown may not throw, and getting this wrong took the whole app down
     * on the first click.
     *
     * StrictMode double-invokes effects in development: mount, unmount,
     * mount. The unmount lands while the async setup below is still in
     * flight, so the terminal gets disposed part-attached — and
     * `WebglAddon.dispose()` then reaches for a `_terminal._core._store` it
     * never received, throwing `undefined is not an object`. That escaped the
     * effect cleanup, which React cannot recover from, so the error boundary
     * caught it and Noctis stopped rendering.
     *
     * Same shape as the dropped-stream bug: the failure was in the path that
     * runs when something is being taken apart, and it was louder than the
     * thing it was cleaning up after. */
    const safely = (what: string, f: () => void) => {
      try {
        f()
      } catch (e) {
        // Reported, not raised. A terminal that fails to come apart cleanly
        // is worth knowing about; it is not worth the window going white.
        console.warn(`[noctis] terminal ${what} on teardown:`, e)
      }
    }

    void (async () => {
      const term_ = new Xterm({
        theme: theme(accent),
        fontFamily: token('--font-mono', 'Cascadia Code, monospace'),
        fontSize: 12.5,
        /* A notch heavier than the shell's body text on purpose. WKWebView
         * rasterises glyphs lighter than Terminal.app does, so the default
         * weight reads thin next to the rest of the interface — Termic hit
         * the same thing. Cascadia is vendored as a 200–700 variable font, so
         * this interpolates rather than synthesising a smear. */
        fontWeight: 450,
        fontWeightBold: 650,
        lineHeight: 1.35,
        letterSpacing: 0,
        cursorBlink: true,
        cursorStyle: 'bar',
        cursorInactiveStyle: 'outline',
        /* Deeper than xterm's 1000-row default: a session that has been
         * working for an hour should still be scrollable back to what it did
         * at the start, which is the whole reason to watch it. */
        scrollback: 20000,
        allowTransparency: false,
        /* Box-drawing glyphs are drawn rather than taken from the font, so
         * the CLI's own rules and frames stay unbroken at any size. */
        customGlyphs: true,
      })
      term = term_
      const fit = new FitAddon()
      term_.loadAddon(fit)
      term_.open(el)

      /* WebGL where it is available, DOM where it is not.
       *
       * Not decoration: it is the renderer that avoids visible row gaps in
       * full-screen TUI output and holds frame rates under load. WKWebView is
       * not Chromium, so the addon can refuse — `onContextLoss` and the throw
       * are both real paths, and dropping to the DOM renderer costs frames
       * rather than correctness. */
      try {
        const addon = new WebglAddon()
        /* Disposed once, and only through the same path teardown uses. It
         * used to dispose itself here *and* again via `term.dispose()`, and
         * the second call is what found a half-attached addon. */
        addon.onContextLoss(() => {
          safely('webgl context loss', () => addon.dispose())
          webgl = undefined
        })
        term_.loadAddon(addon)
        webgl = addon
      } catch {
        // DOM renderer stays; nothing to report to the person using it.
      }

      safely('fit', () => fit.fit())
      // Unmounted while the renderer was attaching — StrictMode does exactly
      // this. Stop before touching a terminal the cleanup has already taken.
      if (!live) return

      const args = await get<{ binary: string; args: string[] }>(
        `/v2/sessions/interactive-args?mode=${mode}&cwd=${encodeURIComponent(cwd)}`)
      if (!live) return
      if (!args) {
        term_.writeln('\r\n  the backend did not answer, so this session has no')
        term_.writeln('  methodology to start with. `make doctor` says whether it is up.\r\n')
        return
      }

      if (!live) return
      const unData = await listen<{ id: string; b64: string }>('pty:data', (e) => {
        if (e.payload.id !== id) return
        /* Bytes, not text. A read can split a multi-byte character down the
         * middle; xterm has its own UTF-8 decoder that holds the seam, and
         * decoding here would corrupt it. */
        const bin = atob(e.payload.b64)
        const bytes = new Uint8Array(bin.length)
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
        term_.write(bytes)
      })
      const unExit = await listen<{ id: string }>('pty:exit', (e) => {
        if (e.payload.id !== id) return
        term_.writeln('\r\n\x1b[2m  session ended\x1b[0m')
        onExit?.()
      })
      cleanups.push(unData, unExit)
      // The listeners are registered; if the tab went away while they were
      // being attached, unregister rather than spawning a process nothing
      // will read.
      if (!live) return

      try {
        await invoke('pty_spawn', {
          id, cwd, args: args.args, binary: args.binary,
          rows: term_.rows, cols: term_.cols,
        })
      } catch (e) {
        term_.writeln(`\r\n  could not start the engine: ${String(e)}\r\n`)
        return
      }

      term_.onData((d) => { void invoke('pty_write', { id, data: d }) })

      const ro = new ResizeObserver(() => {
        fit.fit()
        void invoke('pty_resize', { id, rows: term_.rows, cols: term_.cols })
      })
      ro.observe(el)
      cleanups.push(() => ro.disconnect())

      term_.focus()
    })()

    return () => {
      // First, so anything still awaiting above stops before it touches a
      // terminal that is about to go.
      live = false
      cleanups.forEach((f) => safely('listener', f))
      /* The process goes with the tab. Leaving it would keep a session
       * burning the 5h window with nothing reading it — the same reason the
       * SSE reader releases its lock on abort. */
      void invoke('pty_kill', { id }).catch(() => {
        // Killing a session that already exited is not a failure.
      })
      /* Renderer before terminal. `term.dispose()` disposes its addons as
       * part of coming apart, and the WebGL addon cannot survive being
       * reached for after its terminal's core store has gone — which is the
       * exact throw that took the app down. Disposing it first, explicitly,
       * means the terminal has nothing left to unwind into. */
      if (webgl) {
        safely('webgl dispose', () => webgl!.dispose())
        webgl = undefined
      }
      if (term) {
        safely('dispose', () => term!.dispose())
        term = undefined
      }
    }
    // Deliberately once per tab: re-running would kill and respawn the
    // session on a prop change, losing the conversation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  return <div ref={host} className="h-full w-full overflow-hidden px-[10px] py-[8px]" />
}
