# World background — reference notes

This folder holds the world backdrop plate(s) Shayne drops in manually. This README documents the decisions behind whatever image lands here so the reasoning survives independent of the file.

## Current reference image (2026-07-19)

Generated via Copilot from the Indigo Variant art-direction brief (full brief in `noctis-os/SPEC.md` → Design Brief section). Verdict: strong match — flat color blocks, no gradients within any shape, correct indigo-to-violet sky, sparse asymmetric stars, full-width cloud coverage with no horizon gaps, ambient-only lighting.

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

## Outstanding before this is the final locked asset

1. Stray artifact — a thin comma-shaped mark in the sky, left-of-center — needs removing.
2. Star shape inconsistency — mixes small dots and four-point sparkles; pick one shape.
3. **Composite scale test not yet done.** A real sprite at its actual rendered size hasn't been dropped onto this background yet to confirm the cloud-to-character scale ratio reads right. Do this before treating the background as final — it can't be judged from the background alone.

## What goes in this folder

The locked background plate(s) (Shayne adds manually), plus any variant/rejected passes worth keeping for reference. Grid data, render script, and sprite PNGs live in `../characters/`, not here — this folder is world/backdrop only.
