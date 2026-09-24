"""Aplicación FastAPI de Top Card."""
from __future__ import annotations

import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .config import settings
from .errors import GameError
from .store import store
from .ws import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

DIST = (Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()

# Las imágenes slim de Linux no traen este tipo en su tabla y el manifest de la
# web saldría como `application/octet-stream`.
mimetypes.add_type("application/manifest+json", ".webmanifest")

# Cabeceras de seguridad para todo lo que sale del servidor. Lo único de fuera
# que carga el juego son las tipografías de Google (`index.html`); las cartas y
# los sonidos viajan en el propio build, así que el resto puede ir cerrado.
FONT_CSS = "https://fonts.googleapis.com"
FONT_FILES = "https://fonts.gstatic.com"
CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    # `unsafe-inline` es inevitable: React pinta los colores de cada jugador en
    # el atributo `style` de cada elemento.
    f"style-src 'self' 'unsafe-inline' {FONT_CSS}; "
    "script-src 'self'; "
    "connect-src 'self' ws: wss:; "
    f"font-src 'self' data: {FONT_FILES}; "
    "media-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
}


def safe_dist_file(relative: str) -> Path | None:
    """Resuelve una ruta pedida por el navegador dentro de `frontend/dist`.

    `DIST / relative` no vale por sí solo: con `..`, o con una ruta absoluta,
    `pathlib` se sale de la carpeta y serviría cualquier fichero de la máquina.
    Aquí se resuelve y se comprueba que el resultado sigue colgando de `DIST`.
    """
    if not relative or "\x00" in relative:
        return None
    try:
        candidate = (DIST / relative).resolve()
    except (OSError, ValueError):
        return None
    if candidate != DIST and DIST not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


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

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

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

        # HEAD también: hay rastreadores y generadores de vistas previas que
        # preguntan así antes de descargar, y sin él reciben un 405.
        @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        async def spa(full_path: str) -> Response:
            # Una ruta de API que no existe es un 404, no el index: devolver el
            # HTML enmascararía errores del cliente.
            if full_path.startswith(("api/", "ws/")):
                raise HTTPException(status_code=404, detail="not_found")
            candidate = safe_dist_file(full_path)
            if candidate is not None:
                return FileResponse(candidate)

            # Las páginas SEO estáticas pueden vivir como `ruta/index.html`
            # dentro del build y seguir usando URLs limpias, por ejemplo
            # `/como-se-juega` en vez de `/como-se-juega/index.html`. Con la
            # barra final se redirige a la limpia: una sola URL por página.
            clean_path = full_path.strip("/")
            if clean_path:
                section_index = safe_dist_file(f"{clean_path}/index.html")
                if section_index is not None:
                    if full_path.endswith("/"):
                        return RedirectResponse(f"/{clean_path}", status_code=301)
                    return FileResponse(section_index)

            # El juego sólo vive en `/` (las salas van por hash). Cualquier otra
            # ruta es un 404 de verdad para los buscadores, aunque el cuerpo
            # siga siendo el juego para que la persona no se quede en blanco.
            status = 200 if not clean_path else 404
            return FileResponse(DIST / "index.html", status_code=status)

    return app


app = create_app()
