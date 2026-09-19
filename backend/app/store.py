"""Almacén de salas y difusión por WebSocket.

Decisión de arquitectura: un único proceso FastAPI con las salas en memoria.
No hay cuentas ni persistencia, una partida dura minutos y todo el estado cabe
de sobra en RAM, así que una base de datos sólo añadiría latencia y piezas que
mantener. El acceso a cada sala se serializa con su propio `asyncio.Lock`, de
modo que las mutaciones y la difusión del nuevo estado ocurren de forma atómica
y todos los clientes ven la misma secuencia de eventos.

Si algún día hicieran falta varios procesos, `RoomStore` es la única pieza que
habría que reimplementar (p. ej. sobre Redis con pub/sub para el `broadcast`).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from .config import settings
from .errors import Conflict, NotFound
from .room import Phase, Room, mono
from .security import new_room_code
from .views import room_summary, room_view

log = logging.getLogger("topcard.store")


@dataclass
class RoomRuntime:
    """La sala más lo que necesita para vivir: su lock, sus sockets y la tarea
    que lleva el ritmo del destape."""

    room: Room
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    sockets: dict[str, set[WebSocket]] = field(default_factory=dict)
    reveal_task: asyncio.Task | None = None
    phase_task: asyncio.Task | None = None
    scheduled_deadline: float | None = None
    empty_since: float | None = field(default_factory=mono)

    # ------------------------------------------------------------- conexiones

    def attach(self, player_id: str, socket: WebSocket) -> None:
        self.sockets.setdefault(player_id, set()).add(socket)
        self.empty_since = None

    def detach(self, player_id: str, socket: WebSocket) -> bool:
        """Suelta el socket. Devuelve `True` si al jugador no le queda ninguno."""
        pool = self.sockets.get(player_id)
        if pool is None:
            return True
        pool.discard(socket)
        if pool:
            return False
        del self.sockets[player_id]
        if not self.sockets:
            self.empty_since = mono()
        return True

    # --------------------------------------------------------------- difusión

    async def broadcast(self, event: dict[str, Any] | None = None) -> None:
        """Envía a cada jugador su vista de la sala (y opcionalmente un evento).

        El estado va siempre completo: es un objeto pequeño y evita toda una
        familia de bugs de sincronización por parches perdidos.
        """
        self.schedule_phase_timer()
        dead: list[tuple[str, WebSocket]] = []
        for player_id, pool in list(self.sockets.items()):
            payload: dict[str, Any] = {
                "type": "state",
                "room": room_view(self.room, player_id),
            }
            if event is not None:
                payload["event"] = event
            for socket in list(pool):
                try:
                    await socket.send_json(payload)
                except Exception:  # noqa: BLE001 - socket caído a media escritura
                    dead.append((player_id, socket))
        for player_id, socket in dead:
            self.detach(player_id, socket)

    async def send_to(self, socket: WebSocket, payload: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await socket.send_json(payload)

    # ------------------------------------------------------- ritmo del destape

    def schedule_phase_timer(self) -> None:
        """Deja armado un temporizador que case con el plazo actual de la sala.

        Comprueba también que la tarea siga viva: si la anterior murió (por un
        fallo, o porque terminó sin que el plazo cambiase) hay que rearmarla,
        porque si no la sala se queda sin nadie que cierre la fase y el turno
        no avanza nunca.
        """
        deadline = self.room.phase_deadline
        alive = self.phase_task is not None and not self.phase_task.done()
        if deadline == self.scheduled_deadline and (deadline is None or alive):
            return
        if self.phase_task and self.phase_task is not asyncio.current_task():
            self.phase_task.cancel()
        self.scheduled_deadline = deadline
        self.phase_task = asyncio.create_task(self._run_phase_timer(deadline)) if deadline else None

    async def _run_phase_timer(self, deadline: float) -> None:
        try:
            # `asyncio.sleep` y el plazo comparten el reloj monotónico, pero se
            # vuelve a comprobar de todos modos: dormir "lo que falta" puede
            # quedarse corto por redondeo, y despertar antes de tiempo dejaba
            # la fase sin cerrar y sin temporizador.
            while True:
                remaining = deadline - mono()
                if remaining <= 0:
                    break
                await asyncio.sleep(remaining)
            async with self.lock:
                if self.room.phase_deadline != deadline:
                    return
                if self.room.phase is Phase.PROPOSING:
                    self.room.close_proposals()
                    event = {"kind": "voting_open"}
                elif self.room.phase is Phase.VOTING:
                    self.room.close_voting()
                    event = ({"kind": "topic_chosen", "topic": self.room.topic}
                             if self.room.phase is Phase.PLACING else {"kind": "round_aborted"})
                elif self.room.phase is Phase.PLACING:
                    player = self.room.players.get(self.room.current_player_id)
                    self.room.timeout_turn()
                    # Su valor de retorno dice si se cerró la colocación, no si
                    # el turno venció: eso se mira por el plazo, que `timeout_turn`
                    # siempre mueve (o deja en None al cambiar de fase) cuando actúa.
                    if self.room.phase_deadline == deadline:
                        # No había vencido del todo: rearma en lugar de anunciar
                        # un timeout que no ha ocurrido.
                        self.scheduled_deadline = None
                        self.schedule_phase_timer()
                        return
                    event = {"kind": "turn_timeout", "name": player.name if player else "Jugador"}
                    if self.room.phase is Phase.REVEALING:
                        self.schedule_reveal()
                else:
                    return
                await self.broadcast(event)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            # Que un fallo puntual no deje la sala congelada: el barrendero
            # vuelve a armar el temporizador en la siguiente pasada.
            log.exception("fallo en el temporizador de la sala %s", self.room.code)

    def cancel_timers(self) -> None:
        self.cancel_reveal()
        if self.phase_task:
            self.phase_task.cancel()
        self.phase_task = None
        self.scheduled_deadline = None

    def schedule_reveal(self) -> None:
        """Arranca el cronómetro del destape. La sala ya está en fase REVEALING:
        aquí sólo se decide *cuándo* cae cada carta."""
        if self.reveal_task and not self.reveal_task.done():
            return
        self.reveal_task = asyncio.create_task(self._run_reveal())

    def cancel_reveal(self) -> None:
        if self.reveal_task and not self.reveal_task.done():
            self.reveal_task.cancel()
        self.reveal_task = None

    async def _run_reveal(self) -> None:
        """Destapa las cartas de izquierda a derecha, de la «menor» a la «mayor».

        Lo lleva el servidor y no cada cliente para que todo el mundo vea el
        mismo volteo en el mismo instante.
        """
        try:
            while True:
                await asyncio.sleep(settings.reveal_step)
                async with self.lock:
                    if self.room.phase is not Phase.REVEALING:
                        return
                    index = self.room.reveal_index
                    more = self.room.reveal_next()
                    await self.broadcast({"kind": "reveal", "slot": index})
                if not more:
                    break
            await asyncio.sleep(settings.reveal_tail)
            async with self.lock:
                if self.room.phase is not Phase.REVEALING:
                    return
                self.room.finish_reveal()
                await self.broadcast({"kind": "result", "outcome": self.room.outcome})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("fallo destapando la sala %s", self.room.code)


class RoomStore:
    def __init__(self) -> None:
        self._rooms: dict[str, RoomRuntime] = {}
        self._sweeper: asyncio.Task | None = None

    # --------------------------------------------------------------- consulta

    def get(self, code: str) -> RoomRuntime | None:
        return self._rooms.get(code.upper())

    def require(self, code: str) -> RoomRuntime:
        runtime = self.get(code)
        if runtime is None:
            raise NotFound("no_room", "Esa sala ya no existe.")
        return runtime

    def public_rooms(self) -> list[dict[str, Any]]:
        rooms = [rt.room for rt in self._rooms.values() if not rt.room.is_private]
        rooms.sort(key=lambda r: (-len(r.connected_players), r.created_at))
        return [room_summary(r) for r in rooms]

    def search(self, query: str) -> list[dict[str, Any]]:
        """Busca por nombre o por código, públicas y privadas.

        Las privadas aparecen igual que las públicas (el candado lo pinta el
        cliente con `isPrivate`); lo que no se puede es entrar sin contraseña.
        """
        needle = query.strip().casefold()
        rooms = list(self._rooms.values())
        if needle:
            rooms = [
                rt
                for rt in rooms
                if needle in rt.room.name.casefold() or needle == rt.room.code.casefold()
            ]
        out = [rt.room for rt in rooms]
        out.sort(key=lambda r: (r.is_private, -len(r.connected_players), r.created_at))
        return [room_summary(r) for r in out]

    def hot_topics(self) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        for runtime in self._rooms.values():
            if not runtime.room.is_private:
                counts.update(runtime.room.topic_counts)
        return [{"text": text, "rounds": count} for text, count in counts.most_common(5)]

    # ------------------------------------------------------------------ altas

    def create(
        self, *, name: str, is_private: bool, password: str | None, max_players: int
    ) -> RoomRuntime:
        if len(self._rooms) >= 500:
            raise Conflict("server_busy", "El servidor está lleno de salas, prueba más tarde.")
        for _ in range(50):
            code = new_room_code()
            if code not in self._rooms:
                break
        else:  # pragma: no cover - improbable
            raise Conflict("server_busy", "No he podido generar un código libre.")
        room = Room.create(
            code=code,
            name=name,
            is_private=is_private,
            password=password,
            max_players=max_players,
        )
        runtime = RoomRuntime(room=room)
        self._rooms[code] = runtime
        return runtime

    def drop(self, code: str) -> None:
        runtime = self._rooms.pop(code.upper(), None)
        if runtime is not None:
            runtime.cancel_timers()

    # ------------------------------------------------------------ mantenimiento

    async def start(self) -> None:
        if self._sweeper is None:
            self._sweeper = asyncio.create_task(self._sweep_forever())

    async def stop(self) -> None:
        if self._sweeper is not None:
            self._sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sweeper
            self._sweeper = None
        for runtime in list(self._rooms.values()):
            runtime.cancel_timers()
        self._rooms.clear()

    async def _sweep_forever(self) -> None:
        while True:
            try:
                await asyncio.sleep(settings.sweep_interval)
                await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("fallo en la limpieza de salas")

    async def sweep(self, now: float | None = None) -> None:
        """Expulsa jugadores caídos hace rato y tira las salas abandonadas."""
        now = now or mono()
        for code, runtime in list(self._rooms.items()):
            async with runtime.lock:
                room = runtime.room
                stale = [
                    p.id
                    for p in room.players.values()
                    if not p.connected
                    and p.disconnected_at is not None
                    and now - p.disconnected_at > settings.disconnect_grace
                ]
                for player_id in stale:
                    room.remove_player(player_id)
                    runtime.sockets.pop(player_id, None)

                idle_too_long = now - room.updated_at > settings.idle_room_ttl
                abandoned = (
                    runtime.empty_since is not None
                    and now - runtime.empty_since > settings.empty_room_ttl
                )
                if room.is_empty() or idle_too_long or abandoned:
                    runtime.cancel_timers()
                    self._rooms.pop(code, None)
                    continue
                if stale:
                    # Retirar a un ausente puede cerrar la colocación: si la
                    # sala ha pasado a destapar, hay que arrancar el cronómetro.
                    if room.phase is Phase.REVEALING:
                        runtime.schedule_reveal()
                    await runtime.broadcast({"kind": "players_changed"})
                else:
                    # Red de seguridad: si una sala se quedó sin temporizador
                    # (un fallo inesperado, una cancelación que no se rearmó),
                    # aquí vuelve a armarse en lugar de dejar el turno colgado.
                    runtime.schedule_phase_timer()
                    if room.phase is Phase.REVEALING:
                        # Lo mismo para el destape: retomaría por la carta que
                        # tocase, `reveal_index` no se pierde.
                        runtime.schedule_reveal()


store = RoomStore()
