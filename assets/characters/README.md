# Character assets

Sprite grid definitions, the PIL render script, and generated PNGs go here — the sole source of truth per the EDD (`noctis-os/SPEC.md`), never duplicated into `frontend/src`.

Art direction (final, locked in the vault at `second-brain/wiki/Noctis OS/Modes.md`): minimal chunky pixel art, ~16×16-grade grid, flat solid colors, no outlines/shading/gradients, simplest recognizable animal silhouette, tiny dark pixel eyes, stubby pixel limbs. Five characters: Faber (beaver, dev, warm red), Noctua (owl, learn, gold), Vesper (moth, research, purple), Custos (badger, settings, burnt orange), Echo (bat, nightshift, deep navy).

Shayne drops sprite files in here manually. See `../world/README.md` for the background's footing-spot coordinates these sprites will be positioned against.

## Interim sprites (added 2026-07-20, frontend milestone)

`faber.png`, `noctua.png`, `vesper.png`, `custos.png`, `echo.png` are trimmed idle-frame crops taken directly from `noctisv1sprites.png` — **not** the final production art. Modes.md's Asset plan is explicit that the AI-generated sheet is a *design reference only* and final assets should be a 16×16 palette-indexed grid rendered programmatically via PIL (git-diffable, true pixel grid, no AI-generation fuzziness). These crops exist so the frontend has something real to render while that grid-data pipeline is still unbuilt — swap them for the PIL-rendered PNGs at the same filenames once that pass happens, no frontend code change needed.

**Hex sampled from these crops (dominant fill color, for reference until the grid-data pass locks exact values):**

| Character | Hex |
|---|---|
| Faber | `#E53311` |
| Noctua | `#ECA207` |
| Vesper | `#953EAD` |
| Custos | `#DA5B00` |
| Echo | `#293187` |

## Expression variants (added 2026-07-21)

`expressions/` holds every other sprite on `noctisv1sprites.png` beyond the idle frame — 19 variants across all five characters (hard-hat, sleepy, magnifier, and 16 others), extracted and cleaned with the same pipeline as the idle crops above. Not wired into the app: idle roaming and the full expression library are explicitly v2 scope. See `expressions/README.md` for the full list and naming confidence per file.
