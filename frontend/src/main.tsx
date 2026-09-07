import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './shell/App.tsx'

// v1's index.css and App.tsx are intentionally no longer imported: they carry
// the retired pixel-world tokens (indigo sky, Press Start 2P). Both files stay
// on disk, unreferenced, until the Stage 2 cutover removes them with their
// backend routes -- the same pattern the mode merge used.

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
