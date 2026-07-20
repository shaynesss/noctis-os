from fastapi import FastAPI

from routers import mode, nightshift, session

# TODO: bearer-token auth + Origin checking on every route, mandatory per
# SPEC.md EDD "Backend auth is mandatory, not optional" — localhost binding
# alone isn't sufficient (CSRF/DNS-rebinding class of attack). Not scaffolding,
# a real build task.

app = FastAPI(title="Noctis OS backend")

app.include_router(mode.router)
app.include_router(session.router)
app.include_router(nightshift.router)


@app.get("/health")
def health():
    return {"status": "ok"}
