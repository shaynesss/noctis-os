from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Loads ../.env (VAULT_PATH, NOCTIS_API_TOKEN, PORT) so `make dev` works
# standalone — without this, those vars only exist if the launching shell
# happened to have .env sourced manually, which silently breaks auth/vault
# access on every fresh terminal.
load_dotenv()

from auth import ALLOWED_ORIGIN, require_auth  # noqa: E402
from routers import health, mode, nightshift, session  # noqa: E402

app = FastAPI(title="Noctis OS backend")

# The frontend (Vite dev server) is a different origin from this API even
# though both run on localhost — same auth.py ALLOWED_ORIGIN the bearer-auth
# dependency checks, so there's one place that decides who's allowed in.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(mode.router, dependencies=[Depends(require_auth)])
app.include_router(session.router, dependencies=[Depends(require_auth)])
app.include_router(nightshift.router, dependencies=[Depends(require_auth)])
app.include_router(health.router, dependencies=[Depends(require_auth)])


@app.get("/health")
def health():
    return {"status": "ok"}
