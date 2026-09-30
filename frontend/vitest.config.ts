import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

// Its own file, not a `test` block in vite.config.ts: editing that file
// restarts a running dev server, and the tests only need the setup below.
export default mergeConfig(viteConfig, defineConfig({
  test: { setupFiles: ['./src/test-setup.ts'] },
}))
