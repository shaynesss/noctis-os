Fonts are self-hosted rather than linked from a CDN, so the app has no
runtime network dependency — it is a local-only tool, and a webfont request
is a way for the interface to be worse exactly when the network is.

**Cascadia Code** (Microsoft, SIL OFL 1.1 — licence in `CascadiaCode-OFL.txt`)
is the Design Brief's locked mono: transcript, tool calls, code, status bar,
labels. Taken from Microsoft's own release (`v2407.24`) rather than a
third-party repackage. This is the variable font, so one file covers weights
200–700 and asking for bold interpolates instead of synthesising a smear.

The release ships `CascadiaCode` (with programming ligatures) and
`CascadiaMono` (without). The Design Brief names Code, so that is what is
here; swapping to Mono is a one-file change if the ligatures ever grate in a
transcript full of paths and operators.

**JetBrains Mono** (JetBrains, Apache 2.0) is the fallback beneath it. Worth
knowing: it was vendored and shipping for months while never being loaded at
all — its `@font-face` lived in v1's `index.css`, which stopped being
imported at the v2 cutover, so everything fell through to Menlo. Both faces
are declared in `src/shell/tokens.css` now, and a test fails if a vendored,
requested font is not.

**Press Start 2P** served v1's game world and was removed on 2026-09-16 —
a pixel face is a reading burden in a text-dense tool, and it had been
vendored and unreferenced since the v2 cutover.
