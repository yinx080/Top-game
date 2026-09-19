"""API REST: listar, buscar, crear y entrar en salas.

Todo lo que ocurre dentro de una partida viaja por WebSocket (`ws.py`); aquí
sólo está lo que se hace desde el menú.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .config import settings
from .deck import MAX_VALUE, MIN_VALUE
from .store import store
from .topics import DEFAULT_TOPICS
from .views import room_summary

router = APIRouter(prefix="/api")


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
    return {"rooms": store.search(q)}


@router.get("/rooms/{code}")
async def get_room(code: str) -> dict[str, object]:
    return room_summary(store.require(code).room)


@router.post("/rooms", response_model=SeatOut, status_code=201)
async def create_room(body: CreateRoomIn) -> SeatOut:
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
async def join_room(code: str, body: JoinRoomIn) -> SeatOut:
    runtime = store.require(code)
    player = runtime.room.add_player(body.playerName, body.password)
    return SeatOut(
        code=runtime.room.code,
        playerId=player.id,
        token=player.token,
        room=room_summary(runtime.room),
    )
