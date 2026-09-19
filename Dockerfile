# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# 1) Frontend: compila React/Vite a frontend/dist (incluye public/art).
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# El typecheck vive en CI; aquí sólo interesa el bundle.
RUN npx vite build


# ---------------------------------------------------------------------------
# 2) Runtime: un único proceso uvicorn sirve la API, el WebSocket y el build.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
# main.py busca el build en <raíz>/frontend/dist
COPY --from=frontend /build/dist/ frontend/dist/

RUN useradd --create-home --uid 10001 topcard && chown -R topcard:topcard /app
USER topcard

WORKDIR /app/backend
EXPOSE 8000

# Railway inyecta $PORT; en local vale el 8000 por defecto.
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
