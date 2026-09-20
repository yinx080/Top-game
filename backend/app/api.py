"""API REST: listar, buscar, crear y entrar en salas.

Todo lo que ocurre dentro de una partida viaja por WebSocket (`ws.py`); aquí
sólo está lo que se hace desde el menú.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from .config import settings
from .deck import MAX_VALUE, MIN_VALUE
from .errors import Forbidden
from .ratelimit import RateLimiter, client_key
from .store import store
from .topics import DEFAULT_TOPICS
from .views import room_summary

router = APIRouter(prefix="/api")

# Crear sala es lo más caro que puede pedir un anónimo (ocupa un código y un
# hueco de los 500 del servidor). El margen es generoso a propósito: detrás de
# un mismo NAT puede haber varios amigos abriendo mesas a la vez.
_creates = RateLimiter(rate=0.2, burst=15)
# Entrar es barato, salvo cuando la sala es privada: ahí cada intento cuesta un
# PBKDF2. El cubo por IP frena el goteo normal...
_joins = RateLimiter(rate=1.0, burst=20)
# ...y este, por sala, es el que impide reventar la contraseña desde muchas IP:
# 8 fallos seguidos y la puerta se cierra un rato para todos los que no aciertan.
_passwords = RateLimiter(rate=1 / 15, burst=8)


def reset_limits() -> None:
    """Vacía los contadores. Sólo lo usan los tests, que comparten una IP."""
    for limiter in (_creates, _joins, _passwords):
        limiter._buckets.clear()


class CreateRoomIn(BaseModel):
    name: str = Field(min_length=1, max_length=settings.max_room_name_len)
    playerName: str = Field(min_length=1, max_length=settings.max_name_len)
    isPrivate: bool = False
    password: str | None = Field(default=None, max_length=settings.max_password_len)
    maxPlayers: int = Field(default=settings.default_max_players, ge=2, le=settings.max_players_cap)


class JoinRoomIn(BaseModel):
    playerName: str = Field(min_length=1, max_length=settings.max_name_len)
    password: str | None = Field(default=None, max_length=settings.max_password_len)


class SeatOut(BaseModel):
    code: str
    playerId: str
    token: str
    room: dict


@router.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "publicRooms": len(store.public_rooms())}


@router.get("/config")
async def config() -> dict[str, object]:
    """Lo que el cliente necesita saber antes de entrar en ninguna sala."""
    return {
        "minPlayers": settings.min_players,
        "maxPlayers": settings.max_players_cap,
        "defaultMaxPlayers": settings.default_max_players,
        "limits": {
            "name": settings.max_name_len,
            "roomName": settings.max_room_name_len,
            "topic": settings.max_topic_len,
            "answer": settings.max_answer_len,
        },
        "deck": {"minValue": MIN_VALUE, "maxValue": MAX_VALUE},
        "sampleTopics": DEFAULT_TOPICS[:6],
    }


@router.get("/rooms")
async def list_rooms() -> dict[str, object]:
    return {"rooms": store.public_rooms()}


@router.get("/hot-topics")
async def hot_topics() -> dict[str, object]:
    return {"topics": store.hot_topics()}


@router.get("/rooms/search")
async def search_rooms(q: str = "") -> dict[str, object]:
    # Sin texto se devuelven sólo las públicas: una búsqueda vacía no debe ser
    # un listado completo de las salas privadas que hay abiertas.
    q = q[: settings.max_room_name_len]
    if not q.strip():
        return {"rooms": store.public_rooms()}
    return {"rooms": store.search(q)}


@router.get("/rooms/{code}")
async def get_room(code: str) -> dict[str, object]:
    return room_summary(store.require(code).room)


@router.post("/rooms", response_model=SeatOut, status_code=201)
async def create_room(request: Request, body: CreateRoomIn) -> SeatOut:
    _creates.check(
        client_key(request),
        "Has creado muchas salas seguidas. Espera un minuto antes de abrir otra.",
    )
    runtime = store.create(
        name=body.name,
        is_private=body.isPrivate,
        password=body.password,
        max_players=body.maxPlayers,
    )
    try:
        player = runtime.room.add_player(body.playerName, body.password)
    except Exception:
        store.drop(runtime.room.code)
        raise
    return SeatOut(
        code=runtime.room.code,
        playerId=player.id,
        token=player.token,
        room=room_summary(runtime.room),
    )


@router.post("/rooms/{code}/join", response_model=SeatOut)
async def join_room(request: Request, code: str, body: JoinRoomIn) -> SeatOut:
    _joins.check(client_key(request), "Demasiados intentos. Prueba dentro de unos segundos.")
    runtime = store.require(code)
    guarded = runtime.room.is_private
    if guarded:
        # Se mira *antes* de comprobar la contraseña: si no, el propio PBKDF2
        # del intento fallido sería el trabajo que el atacante quiere provocar.
        _passwords.check(
            runtime.room.code,
            "Demasiados intentos con esa sala. Espera un poco antes de volver a probar.",
            consume=False,
        )
    try:
        player = runtime.room.add_player(body.playerName, body.password)
    except Forbidden:
        _passwords.allow(runtime.room.code)
        raise
    return SeatOut(
        code=runtime.room.code,
        playerId=player.id,
        token=player.token,
        room=room_summary(runtime.room),
    )
