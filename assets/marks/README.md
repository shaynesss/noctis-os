# Marks

Logos that are not ours, kept as files rather than drawn in code.

| File | What | Where it shows |
|---|---|---|
| `claude.png` | Claude's starburst, in its own terracotta | the rail's Terminal icon |

Reached through the `frontend/public/assets` symlink, so a file here is
`/assets/marks/<name>` in the page, the same route the character sprites take.

**Why a file and not a path in `Chrome.tsx`.** The rail's other icons are drawn
inline so they take `currentColor` and follow the active mode's accent. This one
must not: it is Claude's mark and it keeps Claude's orange whatever the session
is, so there is nothing for `currentColor` to do. A drawn approximation stood
here for an afternoon (2026-09-17) and was replaced by the real asset the same
day, which is the honest version of "use the logo".
