"""Integración: menú por REST y una partida completa por WebSocket."""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import store as store_module
from app.config import settings as base_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def fast_reveal(monkeypatch):
    """Acelera el destape para que los tests no esperen segundos reales."""
    quick = dataclasses.replace(base_settings, reveal_step=0.01, reveal_tail=0.01)
    monkeypatch.setattr(store_module, "settings", quick)


@pytest.fixture
def client():
    store_module.store._rooms.clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    store_module.store._rooms.clear()


def create_room(client, **kwargs):
    body = {"name": "Mesa del salón", "playerName": "Ana", **kwargs}
    response = client.post("/api/rooms", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def join(client, code, name, password=None):
    response = client.post(
        f"/api/rooms/{code}/join", json={"playerName": name, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()


def read_until(ws, predicate, limit=60):
    """Lee mensajes hasta que uno cumpla `predicate`, y lo devuelve."""
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("no llegó el mensaje esperado")


def state_with(phase):
    return lambda m: m.get("type") == "state" and m["room"]["phase"] == phase


# ----------------------------------------------------------------------- menú


def test_public_rooms_show_up_in_the_listing(client):
    create_room(client)
    rooms = client.get("/api/rooms").json()["rooms"]
    assert [r["name"] for r in rooms] == ["Mesa del salón"]
    assert rooms[0]["isPrivate"] is False


def test_private_rooms_are_hidden_from_the_home_listing(client):
    create_room(client, isPrivate=True, password="1234")
    assert client.get("/api/rooms").json()["rooms"] == []


def test_private_rooms_are_findable_in_search_with_their_lock(client):
    seat = create_room(client, name="Solo amigos", isPrivate=True, password="1234")
    found = client.get("/api/rooms/search", params={"q": "amigos"}).json()["rooms"]
    assert len(found) == 1
    assert found[0]["isPrivate"] is True
    assert found[0]["code"] == seat["code"]


def test_search_also_matches_the_room_code(client):
    seat = create_room(client)
    found = client.get("/api/rooms/search", params={"q": seat["code"].lower()}).json()["rooms"]
    assert found[0]["code"] == seat["code"]


def test_joining_a_private_room_needs_the_password(client):
    seat = create_room(client, isPrivate=True, password="1234")
    bad = client.post(
        f"/api/rooms/{seat['code']}/join", json={"playerName": "Beto", "password": "0000"}
    )
    assert bad.status_code == 403
    assert bad.json()["error"]["code"] == "bad_password"
    join(client, seat["code"], "Beto", "1234")


def test_joining_a_missing_room_is_a_404(client):
    response = client.post("/api/rooms/ZZZZZZ/join", json={"playerName": "Ana"})
    assert response.status_code == 404


def test_a_full_room_turns_people_away(client):
    seat = create_room(client, maxPlayers=2)
    join(client, seat["code"], "Beto")
    response = client.post(f"/api/rooms/{seat['code']}/join", json={"playerName": "Cris"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "room_full"


# ------------------------------------------------------------------ websocket


def test_a_bad_token_is_rejected(client):
    seat = create_room(client)
    with client.websocket_connect(f"/ws/{seat['code']}?token=nope") as ws:
        assert ws.receive_json()["code"] == "bad_token"


def test_full_round_from_lobby_to_result(client):
    host = create_room(client)
    guest = join(client, host["code"], "Beto")

    with (
        client.websocket_connect(f"/ws/{host['code']}?token={host['token']}") as ws_host,
        client.websocket_connect(f"/ws/{host['code']}?token={guest['token']}") as ws_guest,
    ):
        read_until(ws_host, lambda m: m.get("type") == "welcome")
        read_until(ws_guest, lambda m: m.get("type") == "welcome")
        read_until(ws_host, lambda m: m.get("type") == "state" and len(m["room"]["players"]) == 2)

        ws_host.send_json({"action": "start_round"})
        read_until(ws_host, state_with("proposing"))
        read_until(ws_guest, state_with("proposing"))

        ws_host.send_json({"action": "propose", "text": "Animales de menos a más grandes"})
        ws_guest.send_json({"action": "propose", "text": None})
        voting = read_until(ws_host, state_with("voting"))
        candidates = voting["room"]["candidates"]
        assert any(c["text"] == "Animales de menos a más grandes" for c in candidates)

        mine = next(c for c in candidates if c["isMine"])
        ws_host.send_json({"action": "vote", "candidateId": mine["id"]})
        read_until(ws_guest, state_with("voting"))
        ws_guest.send_json({"action": "vote", "candidateId": mine["id"]})

        placing = read_until(ws_host, state_with("placing"))
        assert placing["room"]["topic"]["text"] == "Animales de menos a más grandes"
        assert placing["room"]["you"]["card"] is not None

        # Sólo la carta propia viaja al cliente.
        assert all(p.get("card") is None for p in placing["room"]["players"])

        sockets = {host["playerId"]: ws_host, guest["playerId"]: ws_guest}
        state = placing["room"]
        for _ in range(2):
            current = state["currentPlayerId"]
            ws = sockets[current]
            ws.send_json({"action": "place", "slot": 0, "answer": "hormiga"})
            state = read_until(
                ws_host,
                lambda m: m.get("type") == "state"
                and (m["room"]["currentPlayerId"] != current or m["room"]["phase"] != "placing"),
            )["room"]

        result = read_until(ws_host, state_with("result"))["room"]
        assert result["outcome"] in ("win", "lose")
        assert len(result["table"]) == 2
        assert all(entry["revealed"] and entry["card"] for entry in result["table"])
        values = [entry["card"]["value"] for entry in result["table"]]
        assert (result["outcome"] == "win") == (values[0] <= values[1])


def test_you_cannot_place_out_of_turn(client):
    host = create_room(client)
    guest = join(client, host["code"], "Beto")

    with (
        client.websocket_connect(f"/ws/{host['code']}?token={host['token']}") as ws_host,
        client.websocket_connect(f"/ws/{host['code']}?token={guest['token']}") as ws_guest,
    ):
        read_until(ws_host, lambda m: m.get("type") == "welcome")
        read_until(ws_guest, lambda m: m.get("type") == "welcome")

        ws_host.send_json({"action": "start_round"})
        ws_host.send_json({"action": "propose", "text": None})
        ws_guest.send_json({"action": "propose", "text": None})
        voting = read_until(ws_host, state_with("voting"))["room"]
        ws_host.send_json({"action": "vote", "candidateId": voting["candidates"][0]["id"]})
        ws_guest.send_json({"action": "vote", "candidateId": voting["candidates"][0]["id"]})
        placing = read_until(ws_host, state_with("placing"))["room"]

        waiting = ws_guest if placing["currentPlayerId"] == host["playerId"] else ws_host
        waiting.send_json({"action": "place", "slot": 0, "answer": "tarde"})
        error = read_until(waiting, lambda m: m.get("type") == "error")
        assert error["code"] == "not_your_turn"


def test_only_the_host_can_start(client):
    host = create_room(client)
    guest = join(client, host["code"], "Beto")

    with (
        client.websocket_connect(f"/ws/{host['code']}?token={host['token']}"),
        client.websocket_connect(f"/ws/{host['code']}?token={guest['token']}") as ws_guest,
    ):
        read_until(ws_guest, lambda m: m.get("type") == "welcome")
        ws_guest.send_json({"action": "start_round"})
        assert read_until(ws_guest, lambda m: m.get("type") == "error")["code"] == "not_host"


def test_leaving_the_last_seat_drops_the_room(client):
    host = create_room(client)
    with client.websocket_connect(f"/ws/{host['code']}?token={host['token']}") as ws:
        read_until(ws, lambda m: m.get("type") == "welcome")
        ws.send_json({"action": "leave"})
    assert client.get(f"/api/rooms/{host['code']}").status_code == 404


def test_a_guest_cannot_cancel_the_reveal(client):
    """`back_to_lobby` comprueba el anfitrión *antes* de tocar el destape."""
    host = create_room(client)
    guest = join(client, host["code"], "Beto")

    with (
        client.websocket_connect(f"/ws/{host['code']}?token={host['token']}") as ws_host,
        client.websocket_connect(f"/ws/{host['code']}?token={guest['token']}") as ws_guest,
    ):
        read_until(ws_host, lambda m: m.get("type") == "welcome")
        read_until(ws_guest, lambda m: m.get("type") == "welcome")

        ws_host.send_json({"action": "start_round"})
        ws_host.send_json({"action": "propose", "text": None})
        ws_guest.send_json({"action": "propose", "text": None})
        voting = read_until(ws_host, state_with("voting"))["room"]
        ws_host.send_json({"action": "vote", "candidateId": voting["candidates"][0]["id"]})
        ws_guest.send_json({"action": "vote", "candidateId": voting["candidates"][0]["id"]})
        placing = read_until(ws_host, state_with("placing"))["room"]

        sockets = {host["playerId"]: ws_host, guest["playerId"]: ws_guest}
        state = placing
        for _ in range(2):
            current = state["currentPlayerId"]
            sockets[current].send_json({"action": "place", "slot": 0, "answer": "algo"})
            state = read_until(
                ws_host,
                lambda m: m.get("type") == "state"
                and (m["room"]["currentPlayerId"] != current or m["room"]["phase"] != "placing"),
            )["room"]

        ws_guest.send_json({"action": "back_to_lobby"})
        assert read_until(ws_guest, lambda m: m.get("type") == "error")["code"] == "not_host"
        # El destape sigue su curso pese al intento.
        assert read_until(ws_host, state_with("result"))["room"]["outcome"] in ("win", "lose")


def test_chat_reaches_the_other_players(client):
    host = create_room(client)
    guest = join(client, host["code"], "Beto")

    with (
        client.websocket_connect(f"/ws/{host['code']}?token={host['token']}") as ws_host,
        client.websocket_connect(f"/ws/{host['code']}?token={guest['token']}") as ws_guest,
    ):
        read_until(ws_host, lambda m: m.get("type") == "welcome")
        read_until(ws_guest, lambda m: m.get("type") == "welcome")

        ws_host.send_json({"action": "chat", "text": "¿listos?"})
        seen = read_until(
            ws_guest,
            lambda m: m.get("type") == "state" and m["room"]["chat"],
        )
        assert seen["room"]["chat"][-1]["text"] == "¿listos?"
        assert seen["room"]["chat"][-1]["playerName"] == "Ana"
        assert seen["event"]["kind"] == "chat"


def test_an_empty_chat_message_is_refused(client):
    host = create_room(client)
    with client.websocket_connect(f"/ws/{host['code']}?token={host['token']}") as ws:
        read_until(ws, lambda m: m.get("type") == "welcome")
        ws.send_json({"action": "chat", "text": "    "})
        assert read_until(ws, lambda m: m.get("type") == "error")["code"] == "empty_message"
