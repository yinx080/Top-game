"""Bots para jugar a Top Card tú desde el navegador.

Dos formas de usarlo:

  # 1) Creas tú la sala en el navegador y metes bots con su código.
  #    Eres el anfitrión: tú decides cuándo empieza cada ronda.
  python scripts/bots.py --code AB3K9P --bots 3

  # 2) Los bots abren la sala y te pasan el enlace. El bot anfitrión
  #    arranca la ronda en cuanto entras, y encadena las siguientes.
  python scripts/bots.py --bots 3

Se paran con Ctrl+C.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import random
import sys
import urllib.error
import urllib.request

import websockets

NAMES = ["Robo-Ana", "Robo-Beto", "Robo-Cris", "Robo-Dani", "Robo-Eva", "Robo-Fran", "Robo-Gema"]

# Una palabra por valor de carta (1..13). Los bots eligen la que corresponde a
# su carta, así que sus respuestas son coherentes con lo que han colocado.
WORDS_BY_VALUE = [
    "microbio", "hormiga", "abeja", "gorrión", "ardilla", "conejo", "zorro",
    "lobo", "jabalí", "caballo", "oso", "elefante", "ballena",
]

TOPIC_IDEAS = [
    "Animales, del más pequeño al más grande",
    "Cosas de casa, de menos a más ruidosas",
    "Excusas, de menos a más creíbles",
    "Comidas, de menos a más pesadas",
    "Planes de domingo, de peor a mejor",
    "Miedos, de menos a más racionales",
]


def http(url: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode()
        sys.exit(f"\n{url} -> {error.code}\n{detail}\n")
    except urllib.error.URLError as error:
        sys.exit(f"\nNo llego al servidor en {url} ({error.reason}).\n"
                 f"¿Está levantado el backend? .\\dev.ps1\n")


class Bot:
    def __init__(self, base: str, seat: dict, name: str, pace: float) -> None:
        self.base = base
        self.seat = seat
        self.name = name
        self.pace = pace
        self.room: dict | None = None
        self.ws: websockets.ClientConnection | None = None
        # Evita repetir una acción mientras aún no ha llegado su confirmación.
        self.done: set[tuple[int, str]] = set()
        self.is_host_bot = False
        self.bot_ids: set[str] = set()
        self.starting = False
        self.tasks: set[asyncio.Task] = set()

    @property
    def id(self) -> str:
        return self.seat["playerId"]

    async def send(self, **payload) -> None:
        if self.ws:
            await self.ws.send(json.dumps(payload))

    async def run(self) -> None:
        url = f"{self.base.replace('http', 'ws', 1)}/ws/{self.seat['code']}?token={self.seat['token']}"
        async with websockets.connect(url) as ws:
            self.ws = ws
            async for raw in ws:
                message = json.loads(raw)
                if message["type"] == "state":
                    self.room = message["room"]
                    await self.react()
                elif message["type"] == "error":
                    # Normalmente es una carrera inofensiva («ya has votado»).
                    print(f"  · {self.name}: {message['message']}")

    def once(self, action: str) -> bool:
        """True la primera vez que se pide `action` en esta ronda."""
        assert self.room
        key = (self.room["round"], action)
        if key in self.done:
            return False
        self.done.add(key)
        return True

    async def react(self) -> None:
        """Decide qué hacer con el estado recién recibido.

        Las acciones salen como tareas aparte: si esperásemos aquí, el bot
        dejaría de leer el socket mientras «piensa».
        """
        room = self.room
        assert room
        you = room["you"]
        phase = room["phase"]

        if phase == "lobby":
            self.done.clear()
            self.schedule_round_start()

        elif phase == "proposing" and not you["proposed"] and self.once("propose"):
            # Uno de cada tres bots pasa, para que la papeleta varíe.
            text = None if random.random() < 0.34 else random.choice(TOPIC_IDEAS)
            self.later(self.send(action="propose", text=text))

        elif phase == "voting" and not you["vote"] and self.once("vote"):
            choice = random.choice(room["candidates"])["id"]
            self.later(self.send(action="vote", candidateId=choice))

        elif phase == "placing" and you["isCurrent"] and not you["hasPlaced"] and self.once("place"):
            self.later(self.place(room))

        elif phase == "result":
            self.schedule_round_start()

    def later(self, coro) -> None:
        """Lanza la acción tras una pausa corta, sin bloquear la lectura."""

        async def run() -> None:
            await asyncio.sleep(self.pace * random.uniform(0.6, 1.6))
            with contextlib.suppress(Exception):
                await coro

        self.tasks.add(asyncio.create_task(run()))

    async def place(self, room: dict) -> None:
        card = room["you"]["card"]
        if not card:
            return
        value = card["value"]
        low, high = room["limits"]["minValue"], room["limits"]["maxValue"]
        table = room["table"]

        # Juega honesto: reparte su valor sobre los huecos disponibles y le suma
        # algo de ruido para que se equivoque de vez en cuando, como todos.
        share = (value - low) / max(high - low, 1)
        slot = round(share * len(table) + random.uniform(-0.6, 0.6))
        slot = max(0, min(len(table), slot))

        word = WORDS_BY_VALUE[min(value, len(WORDS_BY_VALUE)) - 1]
        print(f"  {self.name} coloca en la posición {slot} y dice «{word}»")
        await self.send(action="place", slot=slot, answer=word)

    def humans_present(self, room: dict) -> bool:
        return any(p["connected"] and p["id"] not in self.bot_ids for p in room["players"])

    def schedule_round_start(self) -> None:
        """Sólo el bot anfitrión (modo «los bots abren la sala») lanza rondas."""
        room = self.room
        assert room
        if not self.is_host_bot or not room["you"]["isHost"] or self.starting:
            return
        if not self.humans_present(room) or len(room["players"]) < room["minPlayers"]:
            return

        self.starting = True
        # En `result` damos tiempo a mirar las cartas antes de la siguiente.
        delay = 7.0 if room["phase"] == "result" else 2.0

        async def run() -> None:
            try:
                await asyncio.sleep(delay)
                if self.room and self.room["phase"] in ("lobby", "result"):
                    await self.send(action="start_round")
            finally:
                self.starting = False

        self.tasks.add(asyncio.create_task(run()))


async def main_async(args: argparse.Namespace) -> None:
    base = args.base.rstrip("/")
    count = max(1, min(args.bots, len(NAMES)))
    names = random.sample(NAMES, count)

    if args.code:
        code = args.code.strip().upper()
        http(f"{base}/api/rooms/{code}")  # 404 claro si no existe
        seats = [http(f"{base}/api/rooms/{code}/join",
                      {"playerName": name, "password": args.password}) for name in names]
        host_bot = None
        print(f"\n{count} bots dentro de la sala {code}.")
        print("Eres el anfitrión: pulsa «Empezar ronda» en el navegador.\n")
    else:
        first = http(f"{base}/api/rooms",
                     {"name": "Mesa con bots", "playerName": names[0], "isPrivate": False,
                      "maxPlayers": min(8, count + 3)})
        code = first["code"]
        seats = [first] + [http(f"{base}/api/rooms/{code}/join", {"playerName": name})
                           for name in names[1:]]
        host_bot = 0
        print(f"\nSala {code} abierta por los bots.")
        print(f"Entra aquí:  {base}/#/room/{code}")
        print("La ronda arranca sola en cuanto te sientes a la mesa.\n")

    bots = [Bot(base, seat, name, args.pace) for seat, name in zip(seats, names)]
    bot_ids = {bot.id for bot in bots}
    for index, bot in enumerate(bots):
        bot.bot_ids = bot_ids
        bot.is_host_bot = index == host_bot

    tasks = [asyncio.create_task(bot.run()) for bot in bots]
    try:
        await asyncio.gather(*tasks)
    finally:
        for bot in bots:
            with contextlib.suppress(Exception):
                await bot.send(action="leave")
        for task in tasks:
            task.cancel()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="servidor (por defecto :8000)")
    parser.add_argument("--code", help="código de una sala ya creada por ti")
    parser.add_argument("--password", help="contraseña, si la sala es privada")
    parser.add_argument("--bots", type=int, default=3, help="cuántos bots (por defecto 3)")
    parser.add_argument("--pace", type=float, default=1.6, help="segundos que tardan en reaccionar")
    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nBots retirados.")


if __name__ == "__main__":
    main()
