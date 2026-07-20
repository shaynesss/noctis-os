from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth import ALLOWED_ORIGIN, require_auth
from routers import mode, nightshift, session

app = FastAPI(title="Noctis OS backend")

# The frontend (Vite dev server) is a different origin from this API even
# though both run on localhost — same auth.py ALLOWED_ORIGIN the bearer-auth
# dependency checks, so there's one place that decides who's allowed in.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(mode.router, dependencies=[Depends(require_auth)])
app.include_router(session.router, dependencies=[Depends(require_auth)])
app.include_router(nightshift.router, dependencies=[Depends(require_auth)])


@app.get("/health")
def health():
    return {"status": "ok"}
