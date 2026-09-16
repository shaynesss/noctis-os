# Expression variants — extracted, not wired in

Extracted 2026-07-21 from the v1 reference sheet (removed from the repo 2026-09-15 with Custos's and Echo's variants, the personas having been retired). Every non-idle sprite on the sheet, found via connected-component labeling (not hand-picked crop boxes) and run through the same cleanup pipeline the 5 locked idle sprites use: white-background flood removal to transparency, then a 1px alpha erosion pass to eat the anti-alias halo along the silhouette.

**Mostly not wired into the app.** The tab marks and the Repo view's chips use `noctua-sleepy` and `vesper-drowsy` (Faber's mark is the idle `faber.png`); the rest is the library for states the app does not yet draw.

## Naming — most are confident, a few are a best guess

The sheet has no captions per variant beyond the character-name header row, so names below are visual-inspection calls, not confirmed against original design intent. Marked `(uncertain)` where the read is genuinely ambiguous — worth a real pass with Shayne before these get used anywhere.

| File | Read |
|---|---|
| `faber-blush.png` | pink cheek mark — pleased/happy |
| `faber-hardhat.png` | hard-hat state (named explicitly in Modes.md) |
| `faber-building.png` | with a small tree — a build/work context, not a facial expression |
| `faber-back.png` | rear view |
| `noctua-sleepy.png` | eyes fully closed |
| `noctua-blink.png` | heavy-lidded, mid-blink *(uncertain — could also be "sleepy, less far along")* |
| `vesper-alert.png` | ears/antennae up, wide eyes |
| `vesper-excited.png` | sparkle mark |
| `vesper-humming.png` | small mark near mouth, reads as mid-sound |
| `vesper-drowsy.png` | half-lidded eyes |
| `vesper-happy.png` | heart mark |

## Regenerating

`extract_expressions.py` (the extraction script) wasn't kept in the repo — it was a one-off scratch script, not a build-time tool, matching how the original 5 idle crops were also produced ad hoc rather than via a committed pipeline. If the sheet ever changes or more variants get added by hand, the technique to reuse: `scipy.ndimage.label` on a white-background mask (exclude the top ~260px label-text row) to find each blob's bounding box automatically rather than eyeballing crop coordinates, then the same flood-fill-white + 1px alpha erosion cleanup as `../README.md` documents for the idle set.
