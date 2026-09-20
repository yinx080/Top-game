"""Limitadores de caudal en memoria.

El servidor no tiene cuentas ni base de datos, así que tampoco hay dónde
apuntar quién abusa: basta con un cubo de fichas por clave (una IP, un código
de sala, una conexión) que se rellena solo con el tiempo. Ocupa nada, se limpia
en cada uso y, al vivir en el mismo proceso que las salas, no añade piezas que
mantener.

Cubre tres cosas concretas:

* crear salas a lo bestia hasta llenar el servidor,
* probar contraseñas de una sala privada una detrás de otra (además, cada
  intento cuesta un PBKDF2 de 40k vueltas, así que también sería una forma
  barata de quemar la CPU del proceso),
* inundar el WebSocket de acciones, que se difunden a todos los jugadores.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .errors import GameError


class TooManyRequests(GameError):
    status = 429


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


@dataclass(slots=True)
class RateLimiter:
    """Cubo de fichas: `burst` acciones de golpe y `rate` por segundo después.

    `cost` permite cobrar más caro un intento concreto (por ejemplo, una
    contraseña fallida frente a una acertada).
    """

    rate: float
    burst: float
    _buckets: dict[str, _Bucket] = field(default_factory=dict, repr=False)
    _last_sweep: float = field(default=0.0, repr=False)

    def allow(
        self, key: str, cost: float = 1.0, *, consume: bool = True, now: float | None = None
    ) -> bool:
        """¿Queda cupo para esta acción? Con `consume=False` sólo se consulta."""
        now = now if now is not None else time.monotonic()
        self._sweep(now)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=self.burst, updated=now)
            self._buckets[key] = bucket
        bucket.tokens = min(self.burst, bucket.tokens + (now - bucket.updated) * self.rate)
        bucket.updated = now
        if bucket.tokens < cost:
            return False
        if consume:
            bucket.tokens -= cost
        return True

    def check(self, key: str, message: str, cost: float = 1.0, *, consume: bool = True) -> None:
        """Igual que `allow`, pero levantando el error que entiende la API."""
        if not self.allow(key, cost, consume=consume):
            raise TooManyRequests("too_many_requests", message)

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)

    def _sweep(self, now: float) -> None:
        """Tira los cubos ya llenos: sin esto el diccionario crecería sin fin."""
        if now - self._last_sweep < 60.0:
            return
        self._last_sweep = now
        full_since = self.burst / self.rate if self.rate else 0.0
        for key, bucket in list(self._buckets.items()):
            if now - bucket.updated > full_since:
                del self._buckets[key]


def client_key(request) -> str:
    """Identifica a quien llama, para contar sus peticiones.

    Detrás de un proxy esto es la IP que el proxy diga (uvicorn arranca con
    `--proxy-headers`), así que es orientativo: sirve para frenar el abuso
    tonto, no para bloquear a nadie a conciencia. Lo que protege la contraseña
    de una sala es el contador por sala, que no depende de la IP.
    """
    client = getattr(request, "client", None)
    return client.host if client and client.host else "desconocido"
