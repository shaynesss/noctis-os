import { Component, StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './shell/App.tsx'


/* Catches a render-time crash and shows it.
 *
 * React unmounts the whole tree when a render throws, so without this the
 * window goes blank and says nothing -- which reads as a hang rather than a
 * fault, and leaves nothing to act on. The message is the point: a stack in
 * a console nobody has open is not a report.
 *
 * This cannot catch a failure at import time, which happens before React
 * runs; the boot placeholder in index.html covers that case.
 */
class Boundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  private unsubscribe?: () => void

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  /* Clear on the next hot update.
   *
   * A React error boundary latches: once it catches, it renders the error
   * until something resets it. Under Vite that is wrong, because the usual
   * cause is a file caught mid-edit — a hook added before its import, a
   * rename half-applied — and the next keystroke fixes it. HMR pushes the
   * working module, nothing tells the boundary, and the crash screen stays
   * up for code that is already correct. Observed twice on 2026-09-11/12,
   * both times while a second session was editing the file.
   *
   * Dev only, and not merely because `import.meta.hot` is undefined in a
   * build: in production a render crash is a real fault, and retrying it
   * automatically would loop rather than recover.
   */
  componentDidMount() {
    if (!import.meta.hot) return
    const clear = () => this.setState({ error: null })
    import.meta.hot.on('vite:afterUpdate', clear)
    this.unsubscribe = () => import.meta.hot?.off('vite:afterUpdate', clear)
  }

  componentWillUnmount() {
    this.unsubscribe?.()
  }

  render() {
    if (!this.state.error) return this.props.children
    const dev = Boolean(import.meta.hot)
    return (
      <div className="h-full overflow-auto bg-ground p-7 font-mono text-[12.5px] text-ink-dim">
        <div className="mb-3 text-faber">Noctis hit an error and stopped rendering.</div>
        <div className="mb-4 text-ink-faint">
          {dev
            ? 'Dev build — clears itself once the code compiles. The `[tsc]` stream in your `make dev` terminal names the actual fault; this stack is only where it surfaced.'
            : 'Reopen the window to recover. The session and its history are on disk and were not lost.'}
        </div>
        {dev && (
          <pre className="m-0 whitespace-pre-wrap text-ink-faint">
            {this.state.error.message}
            {'\n\n'}
            {this.state.error.stack}
          </pre>
        )}
      </div>
    )
  }
}

/* A file dropped on the window must do nothing.
 *
 * `dragDropEnabled: false` in tauri.conf hands drag and drop to the webview,
 * which is what lets the tab strip reorder itself with ordinary HTML5 drags.
 * The cost is the webview's own default for a dropped file: navigate to it.
 * On 2026-09-17 a PDF dropped on the window replaced the whole app with the
 * PDF, with no back item in the menu and no reload that returns here, so the
 * only way out was the web inspector. The terminals survived -- they live in
 * the Rust process, not the page -- but the window was gone.
 *
 * So: swallow any drag carrying files, at the window, in the capture phase.
 * The strip's own drags carry no files and are untouched; its handlers run
 * on the element and still see the events they need.
 */
const carriesFiles = (e: DragEvent) => e.dataTransfer?.types?.includes('Files') ?? false
for (const type of ['dragover', 'drop'] as const) {
  window.addEventListener(type, (e: DragEvent) => {
    if (carriesFiles(e)) e.preventDefault()
  }, { capture: true })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Boundary>
      <App />
    </Boundary>
  </StrictMode>,
)
