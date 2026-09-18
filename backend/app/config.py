"""Ajustes del servidor (todo configurable por variables de entorno)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)


@dataclass(frozen=True, slots=True)
class Settings:
    # Límites de sala
    min_players: int = 2
    max_players_cap: int = 10
    default_max_players: int = 8

    # Longitudes aceptadas
    max_name_len: int = 16
    max_room_name_len: int = 28
    max_topic_len: int = 70
    max_answer_len: int = 28
    max_password_len: int = 32
    max_chat_len: int = 160

    # Chat de sala
    chat_history: int = 40      # mensajes que se conservan (van en cada estado)
    chat_cooldown: float = 0.5  # segundos mínimos entre mensajes de un jugador

    # Votación de tema
    min_candidates: int = 3
    max_candidates: int = 6

    # Ritmo del destape (segundos)
    reveal_step: float = 1.25
    reveal_tail: float = 1.1

    # Mantenimiento
    disconnect_grace: float = 180.0   # se expulsa al jugador tras este tiempo caído
    empty_room_ttl: float = 120.0     # sala sin nadie conectado
    idle_room_ttl: float = 3 * 3600.0 # sala sin actividad
    sweep_interval: float = 20.0

    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS


def load_settings() -> Settings:
    origins = os.environ.get("TOPCARD_CORS_ORIGINS")
    return Settings(
        min_players=_int("TOPCARD_MIN_PLAYERS", 2),
        max_players_cap=_int("TOPCARD_MAX_PLAYERS", 10),
        reveal_step=_float("TOPCARD_REVEAL_STEP", 1.25),
        disconnect_grace=_float("TOPCARD_DISCONNECT_GRACE", 180.0),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip())
        if origins
        else DEFAULT_CORS_ORIGINS,
    )


settings = load_settings()
