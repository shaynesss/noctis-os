import { Component, StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './shell/App.tsx'

// v1's index.css and App.tsx are intentionally no longer imported: they carry
// the retired pixel-world tokens (indigo sky, Press Start 2P). Both files stay
// on disk, unreferenced, until the Stage 2 cutover removes them with their
// backend routes -- the same pattern the mode merge used.

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

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="h-full overflow-auto bg-ground p-7 font-mono text-[12.5px] text-ink-dim">
        <div className="mb-3 text-faber">Noctis hit an error and stopped rendering.</div>
        <pre className="m-0 whitespace-pre-wrap text-ink-faint">
          {this.state.error.message}
          {'\n\n'}
          {this.state.error.stack}
        </pre>
      </div>
    )
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Boundary>
      <App />
    </Boundary>
  </StrictMode>,
)
