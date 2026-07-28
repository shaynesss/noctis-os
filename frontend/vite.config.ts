import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Pinned, not Vite's 5173 default — collides with other projects' dev
  // servers on this machine. Must match backend/auth.py's ALLOWED_ORIGIN.
  server: {
    port: 5180,
    strictPort: true,
  },
})
