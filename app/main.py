import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.endpoints import router
from app.frontend import router_ui


app = FastAPI(title="AI Log Analysis Agent", version="1.0")

# Include API and UI routes
app.include_router(router, prefix="/api")
app.include_router(router_ui)

# Conditionally mount the `/static` route only if the directory exists
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")