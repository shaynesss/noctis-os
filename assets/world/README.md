# World background — reference notes

This folder holds the world backdrop plate(s) Shayne drops in manually. This README documents the decisions behind whatever image lands here so the reasoning survives independent of the file.

## Current reference image (2026-07-19)

Generated via Copilot from the Indigo Variant art-direction brief (full brief in `noctis-os/SPEC.md` → Design Brief section). Verdict: strong match — flat color blocks, no gradients within any shape, correct indigo-to-violet sky, sparse asymmetric stars, full-width cloud coverage with no horizon gaps, ambient-only lighting. File is `world-backdrop.jpeg` (renamed 2026-07-20 from its original export filename so the frontend can reference it as a stable URL).

## Footing spots (locked 2026-07-19)

Picked by analyzing the image's actual pixel silhouette (front near-white cloud layer's top boundary) for genuine flat plateaus, not eyeballed — avoids a sprite looking like it's balancing on a peak. Image native size: 1376×768.

| Character | Mode | x (px) | y (px) | x-frac | y-frac |
|---|---|---|---|---|---|
| Faber | dev | 206 | 493 | 0.150 | 0.642 |
| Noctua | learn | 357 | 519 | 0.259 | 0.676 |
| Vesper | research | 610 | 400 | 0.443 | 0.521 |
| Custos | settings | 808 | 465 | 0.587 | 0.605 |
| Echo | nightshift | 1062 | 467 | 0.772 | 0.608 |

Use fractions for CSS positioning (`left: X%; bottom: (100 - Y-as-%)%`) so placement survives resizing/recropping. Vesper's spot sits notably higher than the rest (a taller cloud hump) — this came out of the analysis, not a deliberate choice, but it suits the moth-drawn-to-height theme well enough to keep rather than force symmetry.

**Echo's contrast constraint (carried from the sprite-compatibility review):** all five spots above sit on the bright cloud plateau, never against the dark indigo sky — Echo's deep navy would nearly vanish against the sky, so any future re-placement must keep him on cloud, not sky.

**Percentage positioning alone didn't actually survive resizing (fixed 2026-07-21).** The fraction-based footing spots were always correct in principle, but `frontend/src/index.css`'s `.world` used `width:100%; height:100vh` with `background-size:cover` — a container whose aspect ratio doesn't match the image crops differently at every window size, so characters visibly drifted off their footing on resize despite the percentages being right. Fixed by locking `.world` to the image's native 1376:768 ratio (`aspect-ratio` + `width: min(100vw, 100vh * 1.791667)`), letterboxing/pillarboxing against the sky-deep background color outside that ratio instead of cropping differently. Verified at three very different window shapes (wide/tall/ultrawide) — same relative footing every time.

## Outstanding — all three resolved 2026-07-21

1. ~~Stray artifact — a thin comma-shaped mark in the sky, left-of-center.~~ Removed (cloned a clean nearby sky patch over it, matching local JPEG grain rather than a flat fill that would read as a visible seam).
2. ~~Star shape inconsistency — mixes small dots and four-point sparkles.~~ Standardized on the four-point sparkle (was already the narrow majority, 7 vs 6, and reads more clearly as a deliberate star than a dot does) — the 6 dot-shaped stars were erased and restamped using an actual existing sparkle's pixel signal (copied, not hand-drawn, to guarantee visual consistency with the ones already there).
3. ~~Composite scale test not yet done.~~ Done implicitly and repeatedly — every live Playwright screenshot taken across this whole build (world screen, profile overlays, the resize test above) is real sprites at their actual rendered size against this actual background. Scale reads right: characters are legible and proportionate against the cloud plateaus, neither lost nor overwhelming.

## What goes in this folder

The locked background plate(s) (Shayne adds manually), plus any variant/rejected passes worth keeping for reference. Grid data, render script, and sprite PNGs live in `../characters/`, not here — this folder is world/backdrop only.
