from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from mse_viewer.web.routes import browse, home, log, review, upload


def create_app() -> FastAPI:
    # Surface INFO-level diagnostics from our packages (ingest pipeline logs
    # per-ref keyword resolution) — uvicorn already wires up the root handler.
    logging.getLogger("mse_viewer").setLevel(logging.INFO)

    app = FastAPI(title="mse-viewer", version="0.1.0")

    static_dir = Path(__file__).resolve().parent / "web" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(home.router)
    app.include_router(upload.router)
    app.include_router(review.router)
    app.include_router(browse.router)
    app.include_router(log.router)
    return app


app = create_app()
