"""Bearer-token + Origin auth, mandatory on every route per CLAUDE.md hard
constraints: localhost binding alone isn't sufficient (CSRF/DNS-rebinding
class of attack against a local server with no other auth).
"""

import hmac
import os

from fastapi import Header, HTTPException

ALLOWED_ORIGIN = "http://localhost:5180"  # noctis-os frontend's dedicated dev port (pinned, strictPort in vite.config.ts) — not Vite's 5173 default, which collides with other projects' dev servers

# The packaged desktop app is a *different origin* from the dev server: Tauri
# serves the bundled frontend from tauri://localhost on macOS, not from
# localhost:5180. Allowing only the dev origin therefore produces a build
# that works all through development and cannot reach its own backend the
# moment it is packaged — a failure that only appears at ship time.
#
# Both stay narrow: this is still an allowlist of two known origins, and the
# bearer token remains the actual authentication. Origin checking is the
# defence against a browser being tricked into making the request, and a
# packaged Tauri app is not a browser tab someone can be lured into.
TAURI_ORIGIN = "tauri://localhost"
ALLOWED_ORIGINS = (ALLOWED_ORIGIN, TAURI_ORIGIN)


def require_auth(
    authorization: str = Header(default=""),
    origin: str = Header(default=""),
) -> None:
    token = os.environ.get("NOCTIS_API_TOKEN")
    if not token:
        raise RuntimeError("NOCTIS_API_TOKEN environment variable is not set")

    scheme, _, presented = authorization.partition(" ")
    if scheme != "Bearer" or not hmac.compare_digest(presented, token):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    if origin and origin not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Origin not allowed")
