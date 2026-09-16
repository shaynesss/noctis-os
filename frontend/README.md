# frontend/

The shell: React 19 + TypeScript + Vite + Tailwind 4 in `src/`, and the Tauri 2 window that hosts it in `src-tauri/`. `main.tsx` mounts `src/shell/App.tsx` inside an error boundary and nothing else.

| | |
|---|---|
| `src/shell/` | the v2 client — `App` (arrangement and chrome), `Terminals`/`Terminal` (xterm.js over the PTY), `Panels` (Repo, Settings), `Chrome` (rail, status bar, sprites), `Launcher`, `Palette`, `Transcript` (a past conversation from history), `tokens.css` (the design tokens the terminal theme is generated from) |
| `src-tauri/src/pty.rs` | the pseudo-terminals: spawn, resize, kill, and a registry that outlives the page so a reload reattaches |
| `src-tauri/src/lib.rs` | window, tray, global hotkey, `open_url` |
| `public/assets` | a symlink to `../../assets`, so the sprites have one source |
| `public/fonts/` | vendored faces; see its README |

Run it from the repo root, not here: `make dev` (the window) or `make browser` (a tab at `:5180`). `npm run typecheck` is `tsc -b` — never `tsc --noEmit -p tsconfig.json`, which is a solution file with `"files": []` and checks nothing. `npm run test` is vitest. The `[tsc]` stream in `make dev`'s terminal is the typecheck; Vite itself never checks types.

`DOCUMENTATION.md` §10 is the interface; §22 is the terminal.
