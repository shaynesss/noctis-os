"""Bearer-token + Origin auth, mandatory on every route per CLAUDE.md hard
constraints: localhost binding alone isn't sufficient (CSRF/DNS-rebinding
class of attack against a local server with no other auth).
"""

import hmac
import os

from fastapi import Header, HTTPException

ALLOWED_ORIGIN = "http://localhost:5173"  # Vite dev server default


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

    if origin and origin != ALLOWED_ORIGIN:
        raise HTTPException(status_code=403, detail="Origin not allowed")
