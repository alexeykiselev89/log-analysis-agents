from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import router
from app.frontend import router_ui

app = FastAPI(title="AI Log Analysis Agent", version="1.0")
app.include_router(router, prefix="/api")
app.include_router(router_ui)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
