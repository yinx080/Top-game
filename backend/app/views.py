"""Serialización de la sala hacia el cliente.

La vista es *por jugador*: aquí es donde se garantiza la regla «los jugadores no
pueden saber las cartas del resto». Una carta sólo viaja al navegador si es la
tuya y aún la tienes en la mano, o si ya se ha destapado sobre la mesa.
"""
from __future__ import annotations

from typing import Any

from .config import settings
from .deck import MAX_VALUE, MIN_VALUE
from .room import DrawingSegment, Phase, Room, mono


def room_summary(room: Room) -> dict[str, Any]:
    """Ficha corta para los listados del menú."""
    return {
        "code": room.code,
        "name": room.name,
        "isPrivate": room.is_private,
        "players": len(room.players),
        "online": len(room.connected_players),
        "maxPlayers": room.max_players,
        "phase": room.phase.value,
        "inGame": room.phase is not Phase.LOBBY,
        "round": room.round_no,
        "createdAt": room.created_at,
    }


def _player_view(room: Room, player_id: str) -> dict[str, Any]:
    player = room.players[player_id]
    return {
        "id": player.id,
        "name": player.name,
        "color": player.color,
        "connected": player.connected,
        "isHost": player.id == room.host_id,
        "inRound": player.in_round,
        "hasCard": player.card is not None and not player.placed,
        "hasPlaced": player.placed,
        "proposed": player.proposed,
        "voted": player.vote is not None,
        "isCurrent": room.current_player_id == player.id,
        "timedOut": player.timed_out,
    }


def _candidates_view(room: Room, viewer_id: str) -> list[dict[str, Any]]:
    voters: dict[str, list[str]] = {c.id: [] for c in room.candidates}
    for player in room.players.values():
        if player.vote in voters:
            voters[player.vote].append(player.id)
    return [
        {
            "id": c.id,
            "text": c.text,
            "isMine": c.author_id == viewer_id,
            "isRandom": c.author_id is None,
            "voters": voters[c.id],
        }
        for c in room.candidates
    ]


def _table_view(room: Room) -> list[dict[str, Any]]:
    return [
        {
            "slot": i,
            "playerId": p.player_id,
            "playerName": p.player_name,
            "color": p.color,
            "answer": p.answer,
            "revealed": p.revealed,
            "card": p.card.as_dict() if p.revealed else None,
        }
        for i, p in enumerate(room.table)
    ]


def _chat_view(room: Room) -> list[dict[str, Any]]:
    return [
        {
            "id": m.id,
            "playerId": m.player_id,
            "playerName": m.player_name,
            "color": m.color,
            "text": m.text,
            "at": m.at,
            "replyTo": m.reply_to,
        }
        for m in room.chat
    ]


def drawing_segment_view(segment: DrawingSegment) -> dict[str, Any]:
    return {
        "id": segment.id,
        "playerId": segment.player_id,
        "color": segment.color,
        "width": segment.width,
        "erase": segment.erase,
        "points": [{"x": x, "y": y} for x, y in segment.points],
    }


def room_view(room: Room, viewer_id: str | None) -> dict[str, Any]:
    viewer = room.players.get(viewer_id) if viewer_id else None

    # La carta propia deja de enviarse en cuanto se coloca: a partir de ahí el
    # jugador sólo ve la mesa con las cartas boca abajo.
    hand = None
    if viewer and viewer.card is not None and not viewer.placed:
        hand = viewer.card.as_dict()

    return {
        "code": room.code,
        "name": room.name,
        "isPrivate": room.is_private,
        "hostId": room.host_id,
        "phase": room.phase.value,
        "round": room.round_no,
        "maxPlayers": room.max_players,
        "minPlayers": settings.min_players,
        "players": [_player_view(room, pid) for pid in room.players],
        "you": None
        if viewer is None
        else {
            "id": viewer.id,
            "name": viewer.name,
            "color": viewer.color,
            "isHost": viewer.id == room.host_id,
            "inRound": viewer.in_round,
            "hasPlaced": viewer.placed,
            "card": hand,
            "proposed": viewer.proposed,
            "proposal": viewer.proposal,
            "vote": viewer.vote,
            "isCurrent": room.current_player_id == viewer.id,
            "timedOut": viewer.timed_out,
        },
        "topic": None
        if room.topic is None
        else {"text": room.topic},
        "candidates": _candidates_view(room, viewer_id or ""),
        "pendingProposals": room.pending_proposals(),
        "pendingVotes": room.pending_votes(),
        "turnOrder": list(room.turn_order),
        "turnIndex": room.turn_index,
        "currentPlayerId": room.current_player_id,
        "table": _table_view(room),
        "revealIndex": room.reveal_index,
        "outcome": room.outcome,
        "breakIndex": room.break_index,
        "failedPlayerIds": room.failed_player_ids,
        "hallOfShame": sorted(room.hall_of_shame.values(), key=lambda p: (-p["failures"], p["name"])),
        "wins": room.wins,
        "winStreak": room.win_streak,
        "bestStreak": room.best_streak,
        "proposalSeconds": room.proposal_seconds,
        "voteSeconds": room.vote_seconds,
        "phaseDeadline": room.phase_deadline,
        # Mismo reloj que `phase_deadline`: el cliente sólo usa la diferencia
        # entre ambos, así que no depende del reloj del navegador ni del huso.
        "serverNow": mono(),
        "placementSeconds": room.placement_seconds,
        "savedTopics": len(room.topic_pool),
        "chat": _chat_view(room),
        "drawing": [drawing_segment_view(segment) for segment in room.drawing],
        "limits": {
            "answer": settings.max_answer_len,
            "topic": settings.max_topic_len,
            "name": settings.max_name_len,
            "chat": settings.max_chat_len,
            "minValue": MIN_VALUE,
            "maxValue": MAX_VALUE,
            "drawingSegments": settings.max_drawing_segments,
        },
    }
