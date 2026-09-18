"""Errores de dominio: el transporte (REST o WS) decide cómo presentarlos."""
from __future__ import annotations


class GameError(Exception):
    """Acción rechazada por las reglas o por el estado de la sala."""

    status = 400

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NotFound(GameError):
    status = 404


class Forbidden(GameError):
    status = 403


class Conflict(GameError):
    status = 409
