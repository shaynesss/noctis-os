import logging

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Loads ../.env (VAULT_PATH, NOCTIS_API_TOKEN, PORT) so `make dev` works
# standalone — without this, those vars only exist if the launching shell
# happened to have .env sourced manually, which silently breaks auth/vault
# access on every fresh terminal.
load_dotenv()

from auth import ALLOWED_ORIGINS, require_auth  # noqa: E402
from routers import panels, search, sessions_v2  # noqa: E402

# No /docs, /redoc or /openapi.json. They were the only routes besides /health
# that answered without the token (found 2026-09-29), and a local single-user
# API has no reader for them. `app.openapi()` still builds the schema in code.
app = FastAPI(title="Noctis OS backend", docs_url=None, redoc_url=None, openapi_url=None)


class CrashesInsideCors:
    """Answer an unhandled exception with a plain 500, inside the CORS layer.

    Starlette turns a crash into its 500 in the outermost layer, outside
    CORSMiddleware, so that response carries no Access-Control-Allow-Origin.
    The browser then withholds it and `fetch` rejects as if the connection had
    dropped: on 2026-09-28 a launch that crashed told the person "the backend
    did not answer" and sent them to `make doctor`, which said it was up.
    Caught here the 500 reaches the frontend as a 500, and its message can
    say so. The traceback still goes to the log, under uvicorn's own logger.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def watch(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, watch)
        except Exception:
            if started:
                raise  # half a response is already out; nothing to replace
            logging.getLogger("uvicorn.error").exception(
                "Exception in ASGI application: %s %s", scope.get("method"), scope.get("path"))
            await JSONResponse({"detail": "Internal Server Error"}, status_code=500)(scope, receive, send)


# Added before CORSMiddleware on purpose: each middleware added wraps the ones
# before it, so this one ends up inside CORS and its 500 gets CORS headers.
app.add_middleware(CrashesInsideCors)

# The frontend is a different origin from this API: the Vite dev server on
# localhost:5180, and the packaged app on tauri://localhost. Both come from
# auth.py's ALLOWED_ORIGINS, the same list the bearer-auth dependency checks,
# so there is one place that decides who is allowed in.
#
# The methods have to cover every route below. PUT and DELETE were missing
# until 2026-09-29, so the browser refused its own preflight for them and
# Settings' prompt save, History's delete and a closed terminal's release
# never left the page: 55 refused preflights in the log, not one PUT or
# DELETE ever arrived. test_auth checks every route's method against this.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(sessions_v2.router, dependencies=[Depends(require_auth)])
app.include_router(panels.router, dependencies=[Depends(require_auth)])
app.include_router(search.router, dependencies=[Depends(require_auth)])


# Deliberately unauthenticated, and the only route that is: a liveness probe
# has to answer before anything is configured, and it returns a constant --
# no vault data, no state, nothing an unauthenticated caller learns beyond
# "the process is up".
@app.get("/health")
def health():
    return {"status": "ok"}
