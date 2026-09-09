JetBrains Mono (JetBrains, Apache 2.0) — the Design Brief's fallback mono,
declared in `src/shell/tokens.css`. Self-hosted rather than linked from
Google Fonts so the app has no runtime network dependency, consistent with
this project's local-only scope.

Press Start 2P (Cody "CodeMan38" Boisclair, SIL OFL 1.1) is **retired for
v2** — it served v1's game world, and a pixel face is a reading burden in a
text-dense tool. Kept here, unreferenced, until the v1 cutover removes it
with the rest of that surface.

**Cascadia Code is the locked mono and is not vendored yet.** It is not on
this machine and not on Google Fonts, so it needs its woff2 fetched from
Microsoft's release (SIL OFL) and an @font-face beside the existing one.
Until then the chain resolves to JetBrains Mono, which is the declared
fallback rather than the locked choice.
