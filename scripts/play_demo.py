"""Juega una partida entera contra un servidor Top Card ya levantado.

Sirve como humo de extremo a extremo (REST + WebSocket reales, no TestClient) y
como demo: deja una sala pública abierta si se pasa `--keep`.

    python scripts/play_demo.py --players 4
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import urllib.error
import urllib.request

import websockets

WORDS = [
    "hormiga", "gorrión", "conejo", "lince", "jabalí", "caballo", "oso",
    "rinoceronte", "elefante", "ballena", "secuoya", "montaña",
]


def post(url: str, body: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:  # pragma: no cover - diagnóstico
        sys.exit(f"{url} -> {error.code}: {error.read().decode()}")


class Player:
    def __init__(self, base: str, seat: dict, name: str) -> None:
        self.base = base
        self.seat = seat
        self.name = name
        self.room: dict | None = None
        self.ws: websockets.ClientConnection | None = None

    async def open(self) -> None:
        url = f"{self.base.replace('http', 'ws')}/ws/{self.seat['code']}?token={self.seat['token']}"
        self.ws = await websockets.connect(url)

    async def send(self, **payload) -> None:
        assert self.ws
        await self.ws.send(json.dumps(payload))

    async def pump(self) -> dict:
        """Lee un mensaje y actualiza el estado local."""
        assert self.ws
        message = json.loads(await self.ws.recv())
        if message["type"] == "state":
            self.room = message["room"]
        elif message["type"] == "error":
            print(f"  ⚠ {self.name}: {message['message']}")
        return message

    async def until(self, predicate, limit: int = 400) -> dict:
        """Devuelve el estado en cuanto cumpla `predicate`, ya lo cumpla ahora."""
        if self.room and predicate(self.room):
            return self.room
        for _ in range(limit):
            await self.pump()
            if self.room and predicate(self.room):
                return self.room
        raise SystemExit(f"{self.name}: la sala nunca llegó al estado esperado")


async def run(base: str, count: int, keep: bool, smart: bool) -> None:
    names = ["Ana", "Beto", "Cris", "Dani", "Eva", "Fran", "Gema", "Hugo"][:count]

    host_seat = post(f"{base}/api/rooms", {"name": "Mesa de prueba", "playerName": names[0]})
    code = host_seat["code"]
    print(f"Sala {code} creada por {names[0]}")

    players = [Player(base, host_seat, names[0])]
    for name in names[1:]:
        players.append(Player(base, post(f"{base}/api/rooms/{code}/join", {"playerName": name}), name))

    for player in players:
        await player.open()
    for player in players:
        await player.until(lambda room: len(room["players"]) == count)
    print(f"{count} jugadores conectados")

    host = players[0]
    await host.send(action="start_round")
    for player in players:
        await player.until(lambda room: room["phase"] == "proposing")

    await host.send(action="propose", text="Animales, del más pequeño al más grande")
    for player in players[1:]:
        await player.send(action="propose", text=None)
    for player in players:
        await player.until(lambda room: room["phase"] == "voting")

    ballot = host.room["candidates"]
    print("Papeleta:", " | ".join(c["text"] for c in ballot))
    mine = next(c for c in ballot if c["isMine"])
    for player in players:
        await player.send(action="vote", candidateId=mine["id"])
    for player in players:
        await player.until(lambda room: room["phase"] in ("placing", "lobby"))

    print(f"Tema elegido: {host.room['topic']['text']} (de {host.room['topic']['author']})")

    by_id = {p.seat["playerId"]: p for p in players}
    placed_values: list[int] = []
    for _ in range(count):
        await host.until(lambda room: room["phase"] != "placing" or room["currentPlayerId"])
        if host.room["phase"] != "placing":
            break
        current = by_id[host.room["currentPlayerId"]]
        await current.until(lambda room: room["phase"] == "placing" and room["you"]["card"])
        card = current.room["you"]["card"]
        table = current.room["table"]
        if smart:
            # «Hace trampas» mirando su propia carta: sirve para comprobar la
            # rama de victoria de punta a punta.
            slot = sum(1 for entry in placed_values[:] if entry <= card["value"])
            placed_values.insert(slot, card["value"])
            word = WORDS[min(card["value"] - 1, len(WORDS) - 1)]
        else:
            slot = random.randint(0, len(table))
            word = random.choice(WORDS)
        print(f"  {current.name} coloca {card['code']} (valor {card['value']}) en la posición {slot} · «{word}»")
        await current.send(action="place", slot=slot, answer=word)
        await host.until(
            lambda room: room["phase"] != "placing" or room["currentPlayerId"] != current.seat["playerId"]
        )

    result = await host.until(lambda room: room["phase"] == "result")
    values = [entry["card"]["value"] for entry in result["table"]]
    words = [entry["answer"] for entry in result["table"]]
    print(f"Mesa: {' → '.join(f'{w}({v})' for w, v in zip(words, values))}")
    print(f"Resultado: {'VICTORIA' if result['outcome'] == 'win' else 'DERROTA'}", end="")
    print(f" (se rompe en la posición {result['breakIndex']})" if result["breakIndex"] is not None else "")

    expected = "win" if all(a <= b for a, b in zip(values, values[1:])) else "lose"
    assert result["outcome"] == expected, "el veredicto no cuadra con las cartas"
    if smart:
        assert result["outcome"] == "win", "colocando bien tendría que ganar"

    # La regla clave: nadie ve la carta del resto antes de destaparla.
    for player in players:
        assert all(p.get("card") is None for p in player.room["players"])

    if keep:
        print(f"\nSala {code} en marcha: abre http://127.0.0.1:8000/#/room/{code}")
        await asyncio.Future()
    for player in players:
        await player.send(action="leave")
        assert player.ws
        await player.ws.close()
    print("\n✔ partida completa sin incidencias")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--keep", action="store_true", help="deja la sala abierta al terminar")
    parser.add_argument("--smart", action="store_true", help="coloca bien a propósito (debe ganar)")
    args = parser.parse_args()
    asyncio.run(run(args.base, max(2, min(args.players, 8)), args.keep, args.smart))


if __name__ == "__main__":
    main()
