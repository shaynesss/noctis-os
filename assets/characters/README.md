# Character assets

The sole source of truth for the sprites, never duplicated into `frontend/src`: the app reaches this folder through the `frontend/public/assets` symlink, so a file here is `/assets/characters/<name>.png` in the page.

Three characters, one per mode with a face: Faber (beaver, build, warm red `#E53311`), Noctua (owl, learn, gold `#ECA207`), Vesper (moth, research, purple `#953EAD`). General has no character — the Noctis star stands in — and Maintenance's persona was retired with v1, as were Custos and Echo, whose sprites went with it on 2026-09-15.

Art direction (locked in the vault at `second-brain/wiki/Noctis OS/Modes.md`): minimal chunky pixel art, ~16×16-grade grid, flat solid colours, no outlines, shading or gradients, the simplest recognisable silhouette. Render with `image-rendering: pixelated`; smoothing turns a 16-grade sprite to mush.

**What the app uses today** (`SPRITE` in `frontend/src/shell/Chrome.tsx`): `faber.png` idle, and from `expressions/` `noctua-sleepy` and `vesper-drowsy` — one sprite per character; the "working" variants went with the `-p` orchestrator, since a terminal session does not report a turn in flight. Everything else in `expressions/` is the library for states the app does not yet draw; see `expressions/README.md`.
