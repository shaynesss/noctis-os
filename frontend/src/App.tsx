import { useState } from 'react'
import World from './World'
import ProfileOverlay from './ProfileOverlay'
import type { Mode } from './api'

function App() {
  const [activeMode, setActiveMode] = useState<Mode | null>(null)

  return (
    <>
      <World onSelect={setActiveMode} activeMode={activeMode} />
      <ProfileOverlay mode={activeMode} onClose={() => setActiveMode(null)} />
    </>
  )
}

export default App
