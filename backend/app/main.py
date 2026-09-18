"""Aplicación FastAPI de Top Card."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .config import settings
from .errors import GameError
from .store import store
from .ws import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.start()
    try:
        yield
    finally:
        await store.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Top Card",
        version="1.0.0",
        description="Servidor del juego cooperativo Top Card.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(GameError)
    async def game_error_handler(_: Request, exc: GameError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    app.include_router(api_router)
    app.include_router(ws_router)

    # En producción el mismo proceso sirve el frontend compilado; en desarrollo
    # esta carpeta no existe y se usa el servidor de Vite con su proxy.
    if DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
        app.mount("/art", StaticFiles(directory=DIST / "art"), name="art")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> FileResponse:
            candidate = DIST / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(DIST / "index.html")

    return app


app = create_app()
