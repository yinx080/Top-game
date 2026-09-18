"""Canal en tiempo real de una sala.

El cliente manda acciones (`{"action": "place", ...}`) y el servidor responde
difundiendo el estado completo de la sala a todos los jugadores, más un evento
suelto para que la interfaz sepa qué animar o qué sonido disparar.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .errors import Conflict, GameError
from .room import Phase, Player, Room
from .store import RoomRuntime, store

log = logging.getLogger("topcard.ws")
router = APIRouter()

CLOSE_NO_ROOM = 4404
CLOSE_BAD_TOKEN = 4401
CLOSE_REMOVED = 4403


def _find_by_token(room: Room, token: str) -> Player | None:
    if not token:
        return None
    for player in room.players.values():
        if secrets.compare_digest(player.token, token):
            return player
    return None


async def _announce_phase(runtime: RoomRuntime) -> None:
    """Difunde el estado con el evento que corresponda a la fase recién abierta."""
    room = runtime.room
    if room.phase is Phase.VOTING:
        await runtime.broadcast({"kind": "voting_open"})
    elif room.phase is Phase.PLACING:
        await runtime.broadcast({"kind": "topic_chosen", "topic": room.topic})
    elif room.phase is Phase.REVEALING:
        runtime.schedule_reveal()
        await runtime.broadcast({"kind": "reveal_start"})
    elif room.phase is Phase.LOBBY:
        await runtime.broadcast({"kind": "round_aborted"})


async def _after_departure(runtime: RoomRuntime, before: Phase) -> None:
    """Que alguien se vaya puede cerrar la fase en curso: anúnciala si ha cambiado."""
    if runtime.room.phase is not before:
        await _announce_phase(runtime)


async def _dispatch(
    runtime: RoomRuntime, player_id: str, action: str, data: dict[str, Any]
) -> None:
    room = runtime.room

    if action in ("start_round", "next_round"):
        room.start_round(player_id)
        await runtime.broadcast({"kind": "round_started", "round": room.round_no})

    elif action == "propose":
        text = data.get("text")
        room.propose_topic(player_id, text if isinstance(text, str) else None)
        if room.phase is Phase.PROPOSING:
            await runtime.broadcast({"kind": "proposal_sent"})
        else:
            await _announce_phase(runtime)

    elif action == "vote":
        candidate_id = str(data.get("candidateId") or "")
        room.vote_topic(player_id, candidate_id)
        if room.phase is Phase.VOTING:
            await runtime.broadcast({"kind": "vote_cast"})
        else:
            await _announce_phase(runtime)

    elif action == "place":
        try:
            slot = int(data.get("slot"))
        except (TypeError, ValueError):
            raise GameError("bad_slot", "Esa posición no existe en la mesa.") from None
        answer = str(data.get("answer") or "")
        room.place_card(player_id, slot, answer)
        await runtime.broadcast({"kind": "card_placed", "slot": slot})
        if room.phase is not Phase.PLACING:
            await _announce_phase(runtime)

    elif action == "chat":
        message = room.post_chat(player_id, str(data.get("text") or ""))
        await runtime.broadcast(
            {"kind": "chat", "messageId": message.id, "from": message.player_name}
        )

    elif action == "force":
        # El anfitrión cierra la fase sin esperar a los rezagados.
        room.ensure_host(player_id)
        if room.phase is Phase.PROPOSING:
            room.close_proposals()
        elif room.phase is Phase.VOTING:
            room.close_voting()
        else:
            raise Conflict("wrong_phase", "Esta fase no se puede adelantar.")
        await _announce_phase(runtime)

    elif action == "skip_turn":
        room.skip_turn(player_id)
        await runtime.broadcast({"kind": "turn_skipped"})
        if room.phase is not Phase.PLACING:
            await _announce_phase(runtime)

    elif action == "back_to_lobby":
        room.back_to_lobby(player_id)  # comprueba que quien pide es el anfitrión
        runtime.cancel_reveal()
        await runtime.broadcast({"kind": "back_to_lobby"})

    elif action == "kick":
        room.ensure_host(player_id)
        target_id = str(data.get("playerId") or "")
        if target_id == player_id:
            raise Conflict("cannot_kick_self", "No puedes expulsarte a ti mismo.")
        target = room.player_or_404(target_id)
        name = target.name
        before = room.phase
        room.remove_player(target_id)
        for socket in runtime.sockets.pop(target_id, set()):
            await runtime.send_to(
                socket, {"type": "error", "code": "kicked", "message": "Te han expulsado de la sala."}
            )
            await _safe_close(socket, CLOSE_REMOVED)
        await runtime.broadcast({"kind": "player_left", "name": name})
        await _after_departure(runtime, before)
        if room.is_empty():
            store.drop(room.code)

    else:
        raise GameError("unknown_action", f"No sé qué hacer con «{action}».")


async def _safe_close(socket: WebSocket, code: int) -> None:
    try:
        await socket.close(code=code)
    except Exception:  # noqa: BLE001 - ya estaba cerrado
        pass


@router.websocket("/ws/{code}")
async def game_socket(websocket: WebSocket, code: str, token: str = Query(default="")) -> None:
    await websocket.accept()

    runtime = store.get(code)
    if runtime is None:
        await websocket.send_json({"type": "error", "code": "no_room", "message": "Esa sala ya no existe."})
        await _safe_close(websocket, CLOSE_NO_ROOM)
        return

    player = _find_by_token(runtime.room, token)
    if player is None:
        await websocket.send_json(
            {"type": "error", "code": "bad_token", "message": "Vuelve a entrar en la sala."}
        )
        await _safe_close(websocket, CLOSE_BAD_TOKEN)
        return

    player_id, player_name = player.id, player.name
    async with runtime.lock:
        runtime.attach(player_id, websocket)
        runtime.room.set_connected(player_id, True)
        await runtime.send_to(
            websocket,
            {"type": "welcome", "playerId": player_id, "code": runtime.room.code},
        )
        await runtime.broadcast({"kind": "player_online", "name": player_name})

    try:
        while True:
            try:
                message = await websocket.receive_json()
            except (ValueError, TypeError):
                await runtime.send_to(
                    websocket,
                    {"type": "error", "code": "bad_message", "message": "Mensaje ilegible."},
                )
                continue

            if not isinstance(message, dict):
                continue
            action = str(message.get("action") or "")

            if action == "ping":
                await runtime.send_to(websocket, {"type": "pong"})
                continue

            if action == "leave":
                async with runtime.lock:
                    before = runtime.room.phase
                    runtime.room.remove_player(player_id)
                    runtime.sockets.pop(player_id, None)
                    await runtime.broadcast({"kind": "player_left", "name": player_name})
                    await _after_departure(runtime, before)
                break

            async with runtime.lock:
                if player_id not in runtime.room.players:
                    await _safe_close(websocket, CLOSE_REMOVED)
                    return
                try:
                    await _dispatch(runtime, player_id, action, message)
                except GameError as exc:
                    await runtime.send_to(
                        websocket,
                        {"type": "error", "code": exc.code, "message": exc.message},
                    )
                except Exception:  # noqa: BLE001
                    log.exception("acción %r reventó en la sala %s", action, runtime.room.code)
                    await runtime.send_to(
                        websocket,
                        {
                            "type": "error",
                            "code": "server_error",
                            "message": "Algo ha fallado en el servidor.",
                        },
                    )
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("conexión caída en la sala %s", code)
    finally:
        async with runtime.lock:
            gone = runtime.detach(player_id, websocket)
            if gone and player_id in runtime.room.players:
                before = runtime.room.phase
                runtime.room.set_connected(player_id, False)
                await runtime.broadcast({"kind": "player_offline", "name": player_name})
                await _after_departure(runtime, before)
            if runtime.room.is_empty():
                runtime.cancel_reveal()
                store.drop(runtime.room.code)
        await _safe_close(websocket, 1000)


@router.websocket("/ws")
async def missing_code(websocket: WebSocket) -> None:  # pragma: no cover - ayuda al despistado
    await websocket.accept()
    await websocket.send_json(
        {"type": "error", "code": "no_room", "message": "Falta el código de sala en la URL."}
    )
    await _safe_close(websocket, CLOSE_NO_ROOM)
