from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Loads ../.env (VAULT_PATH, NOCTIS_API_TOKEN, PORT) so `make dev` works
# standalone — without this, those vars only exist if the launching shell
# happened to have .env sourced manually, which silently breaks auth/vault
# access on every fresh terminal.
load_dotenv()

from auth import ALLOWED_ORIGINS, require_auth  # noqa: E402
from routers import design_lodge, health, mode, nightshift, panels, search, session, sessions_v2  # noqa: E402

app = FastAPI(title="Noctis OS backend")

# The frontend is a different origin from this API: the Vite dev server on
# localhost:5180, and the packaged app on tauri://localhost. Both come from
# auth.py's ALLOWED_ORIGINS, the same list the bearer-auth dependency checks,
# so there is one place that decides who is allowed in.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(mode.router, dependencies=[Depends(require_auth)])
app.include_router(session.router, dependencies=[Depends(require_auth)])
app.include_router(nightshift.router, dependencies=[Depends(require_auth)])
app.include_router(design_lodge.router, dependencies=[Depends(require_auth)])
app.include_router(sessions_v2.router, dependencies=[Depends(require_auth)])
app.include_router(panels.router, dependencies=[Depends(require_auth)])
app.include_router(search.router, dependencies=[Depends(require_auth)])
app.include_router(health.router, dependencies=[Depends(require_auth)])


# Deliberately unauthenticated, and the only route that is: a liveness probe
# has to answer before anything is configured, and it returns a constant --
# no vault data, no state, nothing an unauthenticated caller learns beyond
# "the process is up". Everything under the /health *router* (/health/strip
# and friends) does carry auth, which makes this pair easy to misread as a
# gap; it is not, but say so here rather than leave the next reader to work
# it out from two files.
@app.get("/health")
def health():
    return {"status": "ok"}
