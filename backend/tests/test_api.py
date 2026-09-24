"""Integración: menú por REST y una partida completa por WebSocket."""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import api as api_module
from app import store as store_module
from app.config import settings as base_settings
from app.main import DIST, create_app


@pytest.fixture(autouse=True)
def fast_reveal(monkeypatch):
    """Acelera el destape para que los tests no esperen segundos reales."""
    quick = dataclasses.replace(base_settings, reveal_step=0.01, reveal_tail=0.01)
    monkeypatch.setattr(store_module, "settings", quick)


@pytest.fixture
def client():
    # Todos los tests salen de la misma «IP», así que sin esto el limitador de
    # creación de salas acabaría rechazando a los últimos del fichero.
    api_module.reset_limits()
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
        values = [entry["card"]["value"] for entry in result["table"] if entry["card"]["code"] != "joker"]
        assert (result["outcome"] == "win") == all(a <= b for a, b in zip(values, values[1:]))


def test_hot_topics_rank_public_rooms_only(client):
    first = create_room(client)
    second = create_room(client)
    private = create_room(client, isPrivate=True, password="1234")
    store_module.store.require(first["code"]).room.topic_counts = {"frutas": 2, "animales": 1}
    store_module.store.require(second["code"]).room.topic_counts = {"animales": 3}
    store_module.store.require(private["code"]).room.topic_counts = {"secreto": 99}
    assert client.get("/api/hot-topics").json()["topics"] == [
        {"text": "animales", "rounds": 4}, {"text": "frutas", "rounds": 2},
    ]


def test_host_timer_changes_are_broadcast_and_used(client):
    host = create_room(client)
    guest = join(client, host["code"], "Beto")
    with (
        client.websocket_connect(f"/ws/{host['code']}?token={host['token']}") as ws_host,
        client.websocket_connect(f"/ws/{host['code']}?token={guest['token']}") as ws_guest,
    ):
        ws_host.send_json({"action": "set_timers", "proposalSeconds": 90, "voteSeconds": 10, "placementSeconds": 45})
        changed = read_until(ws_guest, lambda m: m.get("type") == "state" and m["room"]["proposalSeconds"] == 90)
        assert changed["room"]["voteSeconds"] == 10
        assert changed["room"]["placementSeconds"] == 45
        ws_host.send_json({"action": "start_round"})
        state = read_until(ws_guest, state_with("proposing"))["room"]
        host_state = read_until(ws_host, state_with("proposing"))["room"]
        assert state["phaseDeadline"] is not None
        assert state["phaseDeadline"] == host_state["phaseDeadline"]
        assert 89 <= state["phaseDeadline"] - state["serverNow"] <= 90
        assert state["wins"] == state["winStreak"] == 0


def test_chat_reply_is_validated_and_broadcast(client):
    host = create_room(client)
    guest = join(client, host["code"], "Beto")
    with (
        client.websocket_connect(f"/ws/{host['code']}?token={host['token']}") as ws_host,
        client.websocket_connect(f"/ws/{host['code']}?token={guest['token']}") as ws_guest,
    ):
        ws_host.send_json({"action": "chat", "text": "¿Listos?"})
        original = read_until(ws_guest, lambda m: m.get("event", {}).get("kind") == "chat")["room"]["chat"][-1]
        ws_guest.send_json({"action": "chat", "text": "Sí", "replyToId": original["id"]})
        state = read_until(ws_host, lambda m: m.get("event", {}).get("from") == "Beto")["room"]
        assert state["chat"][-1]["replyTo"] == {"id": original["id"], "playerName": "Ana", "text": "¿Listos?"}
        ws_guest.send_json({"action": "chat", "text": "inválido", "replyToId": True})
        assert read_until(ws_guest, lambda m: m.get("type") == "error")["code"] == "invalid_reply"


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


def test_drawing_reaches_everyone_and_only_the_host_can_clear_it(client):
    host = create_room(client)
    guest = join(client, host["code"], "Beto")

    with (
        client.websocket_connect(f"/ws/{host['code']}?token={host['token']}") as ws_host,
        client.websocket_connect(f"/ws/{host['code']}?token={guest['token']}") as ws_guest,
    ):
        read_until(ws_host, lambda m: m.get("type") == "welcome")
        read_until(ws_guest, lambda m: m.get("type") == "welcome")

        ws_guest.send_json({
            "action": "draw",
            "points": [{"x": 0.1, "y": 0.2}, {"x": 0.5, "y": 0.7}, {"x": 0.8, "y": 0.9}],
            "color": 6,
            "width": 3,
        })
        host_seen = read_until(ws_host, lambda m: m.get("type") == "drawing")["segment"]
        guest_seen = read_until(ws_guest, lambda m: m.get("type") == "drawing")["segment"]
        assert host_seen == guest_seen
        assert host_seen["playerId"] == guest["playerId"]
        assert (host_seen["color"], host_seen["width"]) == (6, 3)

        ws_guest.send_json({"action": "undo_drawing"})
        undone = read_until(
            ws_host,
            lambda m: m.get("type") == "state" and m.get("event", {}).get("kind") == "drawing_undone",
        )
        assert undone["room"]["drawing"] == []
        ws_guest.send_json({"action": "undo_drawing"})
        assert read_until(ws_guest, lambda m: m.get("type") == "error")["code"] == "nothing_to_undo"

        ws_guest.send_json({"action": "clear_drawing"})
        assert read_until(ws_guest, lambda m: m.get("type") == "error")["code"] == "not_host"
        ws_host.send_json({"action": "clear_drawing"})
        cleared = read_until(
            ws_guest,
            lambda m: m.get("type") == "state" and m.get("event", {}).get("kind") == "drawing_cleared",
        )
        assert cleared["room"]["drawing"] == []


# --------------------------------------------------------------------- seguridad


# Estas rutas sólo existen cuando hay un build del frontend que servir.
needs_dist = pytest.mark.skipif(not DIST.is_dir(), reason="sin frontend/dist (npm run build)")


@needs_dist
def test_the_spa_catch_all_cannot_escape_the_build_folder(client):
    """`/{ruta}` sirve el index, nunca un fichero de fuera de `frontend/dist`."""
    for path in (
        "../../backend/app/config.py",
        "..%2f..%2fbackend%2fapp%2fconfig.py",
        "....//....//backend/app/config.py",
    ):
        response = client.get(f"/{path}")
        assert response.status_code == 404, path
        assert "TOPCARD_CORS_ORIGINS" not in response.text, path
        assert response.headers["content-type"].startswith("text/html"), path


# ------------------------------------------------------------------------- SEO


@needs_dist
def test_only_real_pages_answer_200(client):
    """La portada y las páginas estáticas dan 200; lo inventado, 404 con el juego dentro."""
    assert client.get("/").status_code == 200
    assert client.get("/como-se-juega").status_code == 200
    assert client.get("/legal").status_code == 200

    missing = client.get("/pagina-que-no-existe")
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("text/html")


@needs_dist
def test_a_trailing_slash_redirects_to_the_clean_url(client):
    response = client.get("/como-se-juega/", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/como-se-juega"


@needs_dist
def test_pages_answer_head_requests(client):
    assert client.head("/").status_code == 200
    assert client.head("/como-se-juega").status_code == 200


@needs_dist
def test_seo_files_are_served_with_their_types(client):
    expected = {
        "/robots.txt": "text/plain",
        "/sitemap.xml": "xml",
        "/site.webmanifest": "application/manifest+json",
        "/favicon.ico": "icon",
        "/og-image.jpg": "image/jpeg",
        "/icons/icon-512.png": "image/png",
    }
    for path, content_type in expected.items():
        response = client.get(path)
        assert response.status_code == 200, path
        assert content_type in response.headers["content-type"], path


def test_www_redirects_to_the_bare_domain(client):
    """`www.` se manda al dominio sin él, con la misma ruta y los mismos parámetros."""
    response = client.get(
        "/api/health?probe=1",
        headers={"host": "www.topcards.es"},
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"] == "https://topcards.es/api/health?probe=1"
    assert response.headers["X-Content-Type-Options"] == "nosniff"

    # Sin `www` no hay redirección.
    assert client.get("/api/health", headers={"host": "topcards.es"}).status_code == 200


def test_responses_carry_the_security_headers(client):
    headers = client.get("/api/health").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_an_empty_search_does_not_list_private_rooms(client):
    create_room(client, name="Mesa pública")
    create_room(client, name="Sólo amigos", isPrivate=True, password="clave")

    names = {r["name"] for r in client.get("/api/rooms/search").json()["rooms"]}
    assert names == {"Mesa pública"}
    # Buscándola por su nombre sí aparece: lo que no vale es el listado a pelo.
    found = client.get("/api/rooms/search", params={"q": "amigos"}).json()["rooms"]
    assert [r["name"] for r in found] == ["Sólo amigos"]


def test_guessing_a_room_password_gets_throttled(client):
    seat = create_room(client, isPrivate=True, password="clave-buena")
    code = seat["code"]

    codes = []
    for i in range(12):
        response = client.post(
            f"/api/rooms/{code}/join", json={"playerName": f"Ladrón {i}", "password": "nope"}
        )
        codes.append(response.status_code)
    assert codes[0] == 403
    assert 429 in codes, codes
    # Con la contraseña buena tampoco se entra mientras dura el castigo.
    blocked = client.post(
        f"/api/rooms/{code}/join", json={"playerName": "Beto", "password": "clave-buena"}
    )
    assert blocked.status_code == 429


def test_a_flood_of_websocket_actions_is_cut_off(client):
    from app.ws import WS_FLOOD_STRIKES

    host = create_room(client)
    with client.websocket_connect(f"/ws/{host['code']}?token={host['token']}") as ws:
        read_until(ws, lambda m: m.get("type") == "welcome")
        with pytest.raises(Exception):
            for _ in range(WS_FLOOD_STRIKES * 3):
                ws.send_json({"action": "ping"})
            # El servidor cierra con 4429; leer después revienta.
            for _ in range(WS_FLOOD_STRIKES * 3):
                ws.receive_json()
