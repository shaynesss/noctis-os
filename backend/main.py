from fastapi import Depends, FastAPI

from auth import require_auth
from routers import mode, nightshift, session

app = FastAPI(title="Noctis OS backend")

app.include_router(mode.router, dependencies=[Depends(require_auth)])
app.include_router(session.router, dependencies=[Depends(require_auth)])
app.include_router(nightshift.router, dependencies=[Depends(require_auth)])


@app.get("/health")
def health():
    return {"status": "ok"}
