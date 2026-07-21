import { useEffect, useState } from 'react'
import World from './World'
import ProfileOverlay from './ProfileOverlay'
import type { Mode } from './api'

function App() {
  const [activeMode, setActiveMode] = useState<Mode | null>(null)

  // The desktop window is frameless (desktop/app.py) with no default reload
  // shortcut, and static assets like sprites don't always pick up an update
  // through Vite's HMR the way JS/CSS does -- a hard reload is the reliable
  // "pick up what just changed" action. Cmd+R on macOS, Ctrl+R elsewhere, so
  // this also works if the app is ever opened in a plain browser tab.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'r') {
        e.preventDefault()
        window.location.reload()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <>
      <World onSelect={setActiveMode} activeMode={activeMode} />
      <ProfileOverlay mode={activeMode} onClose={() => setActiveMode(null)} />
    </>
  )
}

export default App
