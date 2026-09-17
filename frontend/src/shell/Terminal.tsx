/* A real Claude Code session, hosted in the shell.
 *
 * This is the conversation surface. Noctis used to drive `claude -p` —
 * "print response and exit" — once per turn and rebuild the interactive loop
 * on top of it; that orchestrator is deleted (`PTY-MIGRATION.md`). This runs
 * the CLI the way a terminal does, so the loop is the CLI's own.
 *
 * xterm.js ships no look of its own, so the theme below is generated from
 * `tokens.css` rather than written twice — one source of truth for what
 * `ink-dim` is, whether it lands in a card or in a terminal cell.
 */
import { useEffect, useRef, useState } from 'react'
import { Terminal as Xterm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebglAddon } from '@xterm/addon-webgl'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { inTauri } from './host'
import '@xterm/xterm/css/xterm.css'
import { del, getResult, post } from './engine'
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
  /* The signature, not maintenance's orange (2026-09-17). This is the slot
   * the CLI prints its permission-mode line in ("auto mode on (shift+tab to
   * cycle)"), which is furniture: it states a setting, it is not news, and an
   * orange as strong as `--color-maint` read as a warning every time the
   * terminal redrew.
   *
   * `--sig-text` rather than a grey (tried first, same day) or a raw
   * `--color-sig-*` step: it is the signature's text weight, the one already
   * chosen to sit legibly on the ground beside a meter, so the line belongs
   * to the app without competing with the mode accent the cursor carries.
   * Every other slot stays where it was. */
  brightYellow: token('--sig-text', '#de778a'),
  brightBlue: '#7aa7ea',
  brightMagenta: '#b662d0',
  brightCyan: '#5cc4bc',
  brightWhite: '#ffffff',

  scrollbarSliderBackground: token('--color-line-soft', '#212121'),
  scrollbarSliderHoverBackground: token('--color-line', '#2a2a2a'),
  scrollbarSliderActiveBackground: token('--color-ink-faint', '#6a6a6a'),
})

/* The last size any terminal here fitted to. A slot that is not showing --
 * the second of two remembered terminals at a reload, or all of them while
 * Stats is up -- sits in a `display: none` box that measures nothing, so
 * FitAddon leaves xterm at its 80×24 default and the session is spawned at
 * that. The CLI's boot banner is laid out once, to the width it was born
 * with; it came up truncated ("Opus 5 with high ef…") in a pane four times
 * as wide. Every terminal in the strip shares one pane, so the size the
 * showing one fitted to is the right size for the hidden ones. */
let lastFit: { rows: number; cols: number } | null = null

/** Fit if the box is laid out; otherwise borrow the last real size.
 *
 * Decided by the host element, not by FitAddon's proposal: inside a
 * `display: none` subtree the addon does not report "no size", it computes
 * one from styles that read `auto` and proposes something tiny -- the
 * hidden terminal was found running at 5×20, the Rust side's floor, with
 * the first version of this check waiting for a proposal that never came.
 * An element with no layout has no client width; that is the test. */
function fitOrBorrow(el: HTMLElement, term: Xterm, fit: FitAddon): void {
  if (el.clientWidth > 0 && el.clientHeight > 0) {
    fit.fit()
    lastFit = { rows: term.rows, cols: term.cols }
  } else if (lastFit) {
    term.resize(lastFit.cols, lastFit.rows)
  } else {
    // Nothing has fitted yet: a first terminal opened while hidden. Wider
    // than xterm's default, because 80 columns is narrower than any pane
    // Noctis draws, and the observer corrects it the moment it shows.
    term.resize(120, 36)
  }
}

/* Spawns are queued, not simultaneous. A reload restores every tab at once,
 * and each tab's session is a ~300MB process plus its MCP servers booting
 * together; six of those in the same second is a spike the machine was
 * shedding processes for. Attaching to a session that survived the reload
 * costs nothing and is not queued -- only a real spawn waits its turn. */
let spawnQueue: Promise<void> = Promise.resolve()
const SPAWN_GAP_MS = 700
function spawnTurn(): Promise<void> {
  const turn = spawnQueue.then(() => new Promise<void>((r) => setTimeout(r, SPAWN_GAP_MS)))
  spawnQueue = turn.catch(() => undefined)
  return turn
}

export function Terminal({
  id, mode, cwd, accent, resumeId, prompt, effort, model, onExit,
}: {
  id: string
  mode: Mode
  cwd: string
  accent: string
  /** An engine session id to `--resume`: a remembered terminal coming back
   *  after a reload, or a history row reopened to continue. */
  resumeId?: string
  /** A first message, submitted as the session opens. A handoff's carried
   *  summary arrives this way rather than through a clipboard. */
  prompt?: string
  effort?: string
  model?: string
  onExit?: () => void
}) {
  const host = useRef<HTMLDivElement>(null)
  /* Restarting reuses the mount path rather than adding a second one.
   * Bumping this re-runs the effect below, which tears the old session down
   * and spawns a fresh one through exactly the code that opened the first. */
  const [generation, setGeneration] = useState(0)
  const dead = useRef(false)
  const setDead = (v: boolean) => { dead.current = v }
  /* The id this terminal will try to resume. A ref rather than the prop,
   * because a resume that fails has to be retried *without* it, and the
   * prop cannot change from in here. Cleared on a fast death; see below. */
  const resumeRef = useRef<string | undefined>(resumeId)
  const spawnedAt = useRef(0)
  /* Ending the session is an intent, not a side effect of unmounting (see
   * the cleanup below). A restart is one: the old process -- ended, or a
   * resume of nothing -- is killed, and only then does the next generation
   * mount, so it finds nothing in the registry and spawns rather than
   * attaching to the corpse. */
  const restart = () => {
    void invoke('pty_kill', { id }).catch(() => {
      // Killing a session that already exited is not a failure.
    }).finally(() => {
      setDead(false)
      setGeneration((g) => g + 1)
    })
  }

  useEffect(() => {
    const el = host.current
    if (!el) return
    let live = true
    let term: Xterm | undefined
    let webgl: WebglAddon | undefined
    const cleanups: Array<() => void> = []
    /* Disposal waits one macrotask. xterm's Viewport constructor queues
     * `setTimeout(() => this.syncScrollArea())` and never cancels it, and
     * `syncScrollArea` reads the render service, whose `dimensions` throws
     * once the service is disposed. StrictMode's mount / cleanup / mount
     * disposed the terminal in the same tick it was opened, so that timer
     * fired against a corpse: one unhandled `_renderer.value.dimensions`
     * error per terminal on every launch, reproduced headlessly with
     * Playwright. A zero-delay timeout queued here sits behind xterm's in
     * the same queue, so xterm's lands on a live terminal and ours takes
     * it down. A frame was not the right wait -- with three terminals
     * opening, rAF fired before the timers and the errors came back.
     *
     * Renderer before terminal. `term.dispose()` disposes its addons as
     * part of coming apart, and the WebGL addon cannot survive being
     * reached for after its terminal's core store has gone — which is the
     * exact throw that took the app down. Disposing it first, explicitly,
     * means the terminal has nothing left to unwind into. */
    const teardown = () => {
      setTimeout(() => {
        if (webgl) {
          safely('webgl dispose', () => webgl!.dispose())
          webgl = undefined
        }
        if (term) {
          safely('dispose', () => term!.dispose())
          term = undefined
        }
      }, 0)
    }

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
        /* The window is a macOS vibrancy material with the desktop showing
         * through, and the ground token is translucent to let it. A terminal
         * that painted an opaque black rectangle over that would be the one
         * solid slab in a glass window. Costs the WebGL renderer some
         * optimisations; the DOM renderer does not care. */
        allowTransparency: true,
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

      /* Fit twice, a frame apart.
       *
       * The first fit runs before the browser has finished laying the host
       * element out, so it measures a box that is not its final size and the
       * terminal opens too narrow — the CLI then wraps its first paint to
       * that width and the prompt arrives with its options cut off. The
       * second fit lands after layout has settled, and the size the engine is
       * told about below is the one from that.
       *
       * `requestAnimationFrame` because the thing being waited for is a
       * layout pass, which is exactly what rAF is scheduled behind -- raced
       * against a short timeout, because WebKit suspends rAF entirely while
       * the window is occluded. A reload with Noctis behind another window
       * parked every terminal on this line: mounted, never spawned, never
       * reattached, until someone looked. A session must not depend on
       * being looked at; the resize observer corrects any fit the timeout
       * path measured early. */
      safely('fit', () => fitOrBorrow(el, term_, fit))
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => resolve())
        setTimeout(resolve, 120)
      })
      // Unmounted while the renderer was attaching — StrictMode does exactly
      // this. Stop before touching a terminal the cleanup is taking down.
      if (!live) return
      safely('fit', () => fitOrBorrow(el, term_, fit))

      /* Keys go to the process -- or, once there is no process, to the
       * restart control. Registered before anything that can fail, so a
       * session that never started is as recoverable as one that ended:
       * the first version registered this after the spawn, and a pane whose
       * backend was down printed its message and then ate every keystroke,
       * `r` included. */
      term_.onData((d) => {
        if (dead.current) {
          if (d === 'r' || d === 'R') restart()
          return
        }
        void invoke('pty_write', { id, data: d })
      })
      const stillborn = (...lines: string[]) => {
        for (const l of lines) term_.writeln(l)
        term_.writeln('\r\n\x1b[2m  press \x1b[0mr\x1b[2m to try again\x1b[0m')
        setDead(true)
      }

      /* Attach or spawn.
       *
       * The PTY registry lives in the Rust process and outlives this web
       * view. After a reload the session this slot belonged to is usually
       * still running -- the registry kept it, the slot kept its id -- and
       * the right thing is to pick it up where it was, not to kill it and
       * `--resume` a copy that has forgotten its screen. VS Code's terminal
       * does the same across a window reload; it is why an integrated
       * terminal survives one. */
      const running = await invoke<string[]>('pty_list').catch(() => [] as string[])
      if (!live) return
      const attaching = running.includes(id)

      const decode = (b64: string) => {
        /* Bytes, not text. A read can split a multi-byte character down the
         * middle; xterm has its own UTF-8 decoder that holds the seam, and
         * decoding here would corrupt it. */
        const bin = atob(b64)
        const bytes = new Uint8Array(bin.length)
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
        return bytes
      }
      /* While attaching, frames are held rather than written. The replay is
       * a snapshot of everything the session has printed, numbered by the
       * last frame it contains and taken under the lock that numbers the
       * frames -- so a held frame numbered past the snapshot is one the
       * replay lacks and is written after it; one numbered within it is
       * already there. The listener goes up before the snapshot is taken,
       * so nothing falls between the two. */
      let held: Array<{ seq: number; bytes: Uint8Array }> | null = attaching ? [] : null
      /* A resume of nothing, by the CLI's own words. The exit handler used
       * to infer it from timing alone -- a resume that dies within five
       * seconds -- and a boot slowed by MCP servers connecting, or parked
       * while the window was hidden, took longer than that and reported a
       * plain "session ended" for a conversation that simply was not on
       * disk. The message is unambiguous; the clock is kept as a fallback.
       * A short tail of decoded text is enough: the phrase is under a
       * hundred characters and a frame boundary can fall inside it. */
      let tail = ''
      let resumedNothing = false
      const utf8 = new TextDecoder()
      const watch = (bytes: Uint8Array) => {
        tail = (tail + utf8.decode(bytes, { stream: true })).slice(-400)
        if (tail.includes('No conversation found')) resumedNothing = true
      }
      /* The browser fallback (`make browser`) has no PTY host: `listen` and
       * `invoke` reach for `__TAURI_INTERNALS__` and throw before anything
       * is subscribed, which landed as a page error on every load. Say so
       * in the pane instead, and leave the rest of the app to its work. */
      if (!inTauri()) {
        term_.writeln('\x1b[2m  terminals need the app -- this is the browser fallback. `make dev` opens the window.\x1b[0m')
        setDead(true)
        return
      }
      const unData = await listen<{ id: string; b64: string; seq: number }>('pty:data', (e) => {
        if (e.payload.id !== id) return
        // A frame can be in flight from the batcher after the listener is
        // unregistered; writing it into a disposed terminal is the same
        // unhandled throw as the resize case, from the other direction.
        if (!live) return
        const bytes = decode(e.payload.b64)
        watch(bytes)
        if (held) { held.push({ seq: e.payload.seq, bytes }); return }
        safely('write', () => term_.write(bytes))
      })
      /* A dead pane needs a way out of itself.
       *
       * A session ends for ordinary reasons -- answering "No, exit" at the
       * trust prompt, typing `exit`, `/quit` -- and the first version left
       * nothing behind but the words "session ended". The terminal was
       * still there, still focused, and every keystroke went nowhere. The
       * only recovery was clicking to another rail item and back, which is
       * not a thing anyone should have to discover.
       *
       * Deliberately a keypress rather than a button: focus is already in
       * the terminal, so the cheapest possible next action is the one your
       * hands are on. */
      const freshInstead = () => {
        resumeRef.current = undefined
        term_.writeln('\r\n\x1b[2m  nothing to resume — starting fresh\x1b[0m')
        restart()
      }
      const ended = () => {
        term_.writeln('\r\n\x1b[2m  session ended — press \x1b[0mr\x1b[2m to start a new one\x1b[0m')
        setDead(true)
        /* Into history, now rather than on the next Stats visit: until the
         * transcript is indexed the session exists on disk and nowhere in
         * the interface, and the exit is the moment the file is complete. */
        void post('/v2/sessions/index', {})
        /* And out of the live count now, not in thirty seconds. Liveness is
         * otherwise "reported recently", which is right for a terminal that
         * died without saying so; this one just said so. */
        void del(`/v2/sessions/statusline/${encodeURIComponent(id)}`)
        onExit?.()
      }
      const unExit = await listen<{ id: string }>('pty:exit', (e) => {
        if (e.payload.id !== id) return
        /* A resume that dies within seconds is a resume of nothing -- the
         * transcript was deleted, or never written. The CLI prints "No
         * conversation found" and exits, and the person is left with a dead
         * pane for an id they never chose. Try once more as a fresh session
         * instead; the mode and directory are what they wanted. */
        if (resumeRef.current && (resumedNothing || Date.now() - spawnedAt.current < 5000)) {
          freshInstead()
          return
        }
        ended()
      })
      cleanups.push(unData, unExit)
      // The listeners are registered; if the tab went away while they were
      // being attached, unregister rather than spawning a process nothing
      // will read.
      if (!live) return

      if (attaching) {
        let snap: { b64: string; seq: number; exited: boolean }
        try {
          snap = await invoke('pty_attach', { id })
        } catch (e) {
          // Listed a moment ago and gone now: it ended during the reload and
          // was reaped in between. Nothing to pick up.
          stillborn(`\r\n  the session is gone: ${String(e)}`)
          return
        }
        if (!live) return
        const replay = decode(snap.b64)
        // The replay is the whole history; a resume that failed before the
        // page came back says so in it.
        if (utf8.decode(replay).includes('No conversation found')) resumedNothing = true
        safely('replay', () => term_.write(replay))
        const pending = held ?? []
        held = null
        for (const h of pending) {
          if (h.seq > snap.seq) safely('write', () => term_.write(h.bytes))
        }
        if (snap.exited) {
          /* Ended while nobody was looking. A resume of nothing is still a
           * resume of nothing -- the mount that spawned it was parked
           * before it could see the exit, so this is where it is seen. */
          if (resumeRef.current && resumedNothing) freshInstead()
          else ended()
        } else {
          /* The pane may not be the size it was when the session last
           * painted. If it is, this changes nothing; if it is not, this is
           * the SIGWINCH that makes the CLI repaint to the new size. */
          void invoke('pty_resize', { id, rows: term_.rows, cols: term_.cols })
        }
      } else {
        await spawnTurn()
        if (!live) return
        const fetched = await getResult<{ binary: string; args: string[]; env?: Record<string, string> }>(
          `/v2/sessions/interactive-args?mode=${mode}&cwd=${encodeURIComponent(cwd)}&slot=${encodeURIComponent(id)}`
          + (resumeRef.current ? `&resume_id=${encodeURIComponent(resumeRef.current)}` : '')
          + (prompt ? `&prompt=${encodeURIComponent(prompt)}` : '')
          + (effort ? `&effort=${encodeURIComponent(effort)}` : '')
          + (model ? `&model=${encodeURIComponent(model)}` : ''))
        if (!live) return
        if (!fetched.ok) {
          // Two different failures that the first version reported as one.
          // A backend that is down is not a backend that said no.
          if (fetched.kind === 'offline') {
            stillborn('\r\n  the backend did not answer, so this session has no',
                      '  methodology to start with. `make doctor` says whether it is up.')
          } else {
            stillborn(`\r\n  the backend refused this session (HTTP ${fetched.status}).`,
                      `  ${fetched.status === 400 ? `is ${cwd} a directory that exists?` : 'its log says why.'}`)
          }
          return
        }
        const args = fetched.data

        spawnedAt.current = Date.now()
        try {
          await invoke('pty_spawn', {
            id, cwd, args: args.args, binary: args.binary, env: args.env ?? null,
            rows: term_.rows, cols: term_.cols,
          })
        } catch (e) {
          stillborn(`\r\n  could not start the engine: ${String(e)}`)
          return
        }
      }

      const ro = new ResizeObserver(() => {
        /* Guarded like the explicit fits above, and for a reason found in the
         * log rather than imagined: this callback landed while the WebGL
         * renderer was still attaching, and `fit()` reached into
         * `_renderer.value.dimensions` during the swap when `value` was
         * undefined. It was the only fit not wrapped, and it was the one that
         * threw -- as an unhandled error, since an observer callback has no
         * caller to catch it. */
        if (!live) return
        safely('fit on resize', () => fitOrBorrow(el, term_, fit))
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
      /* The process does *not* go with this effect. It used to -- "the
       * process goes with the tab" -- and that was right for as long as the
       * only way to leave this effect was closing the tab. Reattaching made
       * it wrong: StrictMode runs mount, cleanup, mount on every page load
       * in development, so the first thing a reload did was kill the
       * session it had come back to attach to. Ending a session is now an
       * intent, expressed where it is meant: `App.close` for ⌘W, `restart`
       * below for `r`. An unmount that is neither -- StrictMode, a hot
       * reload of this file -- leaves the process running for the next
       * mount to pick up, which is exactly what it will do. */
      teardown()
    }
    // Deliberately narrow: re-running on any prop change would kill and
    // respawn a live session, losing the conversation. `generation` is the
    // one intentional re-run, and it means restart.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, generation])

  // `data-terminal` is what the shell's key handler looks for to decide that
  // a keystroke belongs to the CLI rather than to the app.
  //
  // The padding sits on a wrapper, not on the element xterm fits to.
  // FitAddon sizes rows from its parent's border-box height and subtracts
  // only xterm's own padding, so 8px above and below on the host fitted one
  // row too many and the bottom row was cut at the status bar -- hidden
  // while the bar painted its own ground, plain once the bar became glass.
  return (
    <div className="h-full w-full overflow-hidden px-[10px] py-[8px]">
      <div ref={host} data-terminal className="h-full w-full overflow-hidden" />
    </div>
  )
}
