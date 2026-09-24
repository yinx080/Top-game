"""Estado de una sala y máquina de estados de la ronda.

Todo es síncrono y sin E/S: el runtime (`store.py`) es quien serializa los
accesos con un lock por sala y quien difunde los cambios por WebSocket.
"""
from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from .config import settings
from .deck import Card, deal
from .errors import Conflict, Forbidden, GameError, NotFound
from .security import hash_password, new_token, verify_password
from .topics import sample_topics

PALETTE_SIZE = 10
MAX_DRAWING_POINTS = 24


def mono() -> float:
    """Reloj de los plazos de fase y de los cooldowns.

    Monotónico a propósito: es el mismo que usa `asyncio.sleep`, así que el
    temporizador del runtime (`store.py`) y las comprobaciones de plazo de aquí
    no pueden discrepar. Con `time.time()` bastaba un ajuste del reloj del
    sistema, o el redondeo entre ambos relojes, para que un turno venciera
    según un reloj y no según el otro: la ronda se quedaba sin temporizador y
    el jugador ya no podía colocar. `time.time()` se reserva para las marcas
    que se muestran o se comparan entre procesos (fechas de entrada, chat).
    """
    return time.monotonic()


class Phase(str, Enum):
    LOBBY = "lobby"           # esperando jugadores
    PROPOSING = "proposing"   # cada jugador propone un tema (o pasa)
    VOTING = "voting"         # se vota el tema entre los propuestos
    PLACING = "placing"       # se coloca la carta boca abajo, por turnos
    REVEALING = "revealing"   # destape de menor a mayor
    RESULT = "result"         # victoria o derrota


@dataclass(slots=True)
class Player:
    id: str
    name: str
    token: str
    color: int
    joined_at: float
    connected: bool = True
    disconnected_at: float | None = None
    last_chat_at: float = 0.0
    # Estado de ronda
    card: Card | None = None
    placed: bool = False
    in_round: bool = False
    proposal: str | None = None
    proposed: bool = False
    vote: str | None = None
    timed_out: bool = False


@dataclass(slots=True)
class Placement:
    """Una carta sobre la mesa.

    Guarda nombre y color del jugador para que la mesa siga siendo legible
    aunque su dueño abandone la sala a mitad de ronda.
    """

    player_id: str
    player_name: str
    color: int
    card: Card
    answer: str
    revealed: bool = False


@dataclass(slots=True)
class Candidate:
    id: str
    text: str
    author_id: str | None = None
    author_name: str | None = None


@dataclass(slots=True)
class ChatMessage:
    id: int
    player_id: str
    player_name: str
    color: int
    text: str
    at: float
    reply_to: dict | None = None


@dataclass(slots=True)
class DrawingSegment:
    id: int
    player_id: str
    color: int
    width: int
    points: list[tuple[float, float]]
    # Un trazo (de pulsar a soltar) llega troceado en varios segmentos: el
    # número de trazo los agrupa para poder deshacerlo entero.
    stroke: int = 0
    # La goma se guarda como un trazo más que borra lo que tiene debajo, así el
    # orden de pintar y borrar se conserva para quien entra o se reconecta.
    erase: bool = False


def clean_text(text: str, limit: int) -> str:
    """Colapsa espacios y saltos de línea y descarta caracteres de control."""
    collapsed = " ".join(text.split())
    printable = "".join(c for c in collapsed if c.isprintable())
    return printable[:limit].strip()


@dataclass(slots=True)
class Room:
    code: str
    name: str
    is_private: bool
    password_salt: str | None
    password_hash: str | None
    max_players: int
    host_id: str = ""
    created_at: float = field(default_factory=time.time)
    # Se compara sólo como intervalo (sala inactiva), así que va en el
    # reloj monotónico; `created_at` se muestra al cliente y sigue siendo
    # una fecha real.
    updated_at: float = field(default_factory=mono)

    players: dict[str, Player] = field(default_factory=dict)
    phase: Phase = Phase.LOBBY
    round_no: int = 0

    topic: str | None = None
    topic_author: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    topic_pool: list[str] = field(default_factory=list)

    turn_order: list[str] = field(default_factory=list)
    turn_index: int = 0
    table: list[Placement] = field(default_factory=list)
    reveal_index: int = 0

    outcome: str | None = None
    break_index: int | None = None
    failed_player_ids: list[str] = field(default_factory=list)
    hall_of_shame: dict[str, dict] = field(default_factory=dict)
    wins: int = 0
    win_streak: int = 0
    best_streak: int = 0
    proposal_seconds: int = 45
    vote_seconds: int = 30
    placement_seconds: int = settings.placement_seconds
    phase_deadline: float | None = None
    topic_counts: dict[str, int] = field(default_factory=dict)

    # El chat vive fuera de la ronda: no se borra al empezar una nueva.
    chat: list[ChatMessage] = field(default_factory=list)
    chat_seq: int = 0

    # El dibujo dura una ronda y se conserva para quien se reconecta.
    drawing: list[DrawingSegment] = field(default_factory=list)
    drawing_seq: int = 0
    drawing_stroke_seq: int = 0
    drawing_strokes: dict[str, int] = field(default_factory=dict)

    rng: random.Random = field(default_factory=random.Random, repr=False)

    # ---------------------------------------------------------------- creación

    @classmethod
    def create(
        cls,
        *,
        code: str,
        name: str,
        is_private: bool,
        password: str | None,
        max_players: int,
    ) -> "Room":
        name = clean_text(name, settings.max_room_name_len)
        if not name:
            raise GameError("invalid_room_name", "La sala necesita un nombre.")
        if is_private:
            if not password:
                raise GameError("password_required", "Una sala privada necesita contraseña.")
            salt, digest = hash_password(password[: settings.max_password_len])
        else:
            salt = digest = None
        max_players = max(settings.min_players, min(max_players, settings.max_players_cap))
        return cls(
            code=code,
            name=name,
            is_private=is_private,
            password_salt=salt,
            password_hash=digest,
            max_players=max_players,
        )

    def check_password(self, password: str | None) -> None:
        if not self.is_private:
            return
        assert self.password_salt and self.password_hash
        if not password or not verify_password(password, self.password_salt, self.password_hash):
            raise Forbidden("bad_password", "Contraseña incorrecta.")

    # ---------------------------------------------------------------- jugadores

    @property
    def connected_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.connected]

    @property
    def current_player_id(self) -> str | None:
        if self.phase is not Phase.PLACING or self.turn_index >= len(self.turn_order):
            return None
        return self.turn_order[self.turn_index]

    def player_or_404(self, player_id: str) -> Player:
        player = self.players.get(player_id)
        if player is None:
            raise NotFound("no_player", "Ese jugador ya no está en la sala.")
        return player

    def _unique_name(self, name: str) -> str:
        taken = {p.name.casefold() for p in self.players.values()}
        if name.casefold() not in taken:
            return name
        for n in range(2, 100):
            candidate = f"{name} ({n})"
            if candidate.casefold() not in taken:
                return candidate
        return name

    def _free_color(self) -> int:
        used = {p.color for p in self.players.values()}
        for i in range(PALETTE_SIZE):
            if i not in used:
                return i
        return len(self.players) % PALETTE_SIZE

    def add_player(self, name: str, password: str | None = None) -> Player:
        self.check_password(password)
        name = clean_text(name, settings.max_name_len)
        if not name:
            raise GameError("invalid_name", "Escribe un nombre para entrar.")
        if len(self.players) >= self.max_players:
            raise Conflict("room_full", "La sala está llena.")
        player = Player(
            id=new_token()[:12],
            name=self._unique_name(name),
            token=new_token(),
            color=self._free_color(),
            joined_at=time.time(),
            # Se marca conectado cuando abre el WebSocket; hasta entonces no
            # cuenta para arrancar la ronda y el barrendero lo retira si no
            # llega nunca.
            connected=False,
            disconnected_at=mono(),
        )
        self.players[player.id] = player
        if not self.host_id:
            self.host_id = player.id
        self.touch()
        return player

    def remove_player(self, player_id: str) -> None:
        was_current = self.current_player_id == player_id
        player = self.players.pop(player_id, None)
        if player is None:
            return
        if player_id in self.turn_order:
            index = self.turn_order.index(player_id)
            self.turn_order.pop(index)
            if index < self.turn_index:
                self.turn_index -= 1
        if self.host_id == player_id:
            successor = next(iter(self.connected_players), None)
            if successor is None:
                successor = next(iter(self.players.values()), None)
            self.host_id = successor.id if successor else ""
        self._settle_after_departure()
        if was_current and self.phase is Phase.PLACING:
            self.phase_deadline = mono() + self.placement_seconds
        self.touch()

    def _settle_after_departure(self) -> None:
        """Reajusta la ronda cuando alguien se va a mitad de partida."""
        if self.phase in (Phase.LOBBY, Phase.RESULT):
            return
        if len(self.connected_players) < settings.min_players:
            self.abort_round()
            return
        self.advance_if_everyone_acted()

    def advance_if_everyone_acted(self) -> None:
        """Cierra la fase si ya no queda nadie de quien esperar respuesta.

        Hace falta porque marcharse o caerse también «resuelve» el turno de
        alguien: sin esto, que el último rezagado se desconecte dejaría la sala
        esperando indefinidamente.
        """
        if self.phase is Phase.PROPOSING and not self.pending_proposals():
            self.close_proposals()
        elif self.phase is Phase.VOTING and not self.pending_votes():
            self.close_voting()
        elif self.phase is Phase.PLACING:
            self._close_placing_if_done()

    def set_connected(self, player_id: str, connected: bool) -> None:
        player = self.players.get(player_id)
        if player is None:
            return
        player.connected = connected
        player.disconnected_at = None if connected else mono()
        if not connected:
            self.advance_if_everyone_acted()
        self.touch()

    def touch(self) -> None:
        self.updated_at = mono()

    # ------------------------------------------------------------- ciclo ronda

    def ensure_host(self, player_id: str) -> None:
        if player_id != self.host_id:
            raise Forbidden("not_host", "Sólo el anfitrión puede hacer eso.")

    def start_round(self, player_id: str) -> None:
        self.ensure_host(player_id)
        if self.phase not in (Phase.LOBBY, Phase.RESULT):
            raise Conflict("round_running", "La ronda ya está en marcha.")
        if len(self.connected_players) < settings.min_players:
            raise Conflict(
                "not_enough_players",
                f"Hacen falta al menos {settings.min_players} jugadores conectados.",
            )
        self._reset_round()
        self.phase = Phase.PROPOSING
        self.phase_deadline = mono() + self.proposal_seconds
        self.round_no += 1
        self.touch()

    def abort_round(self) -> None:
        self._reset_round()
        self.phase = Phase.LOBBY
        self.touch()

    def back_to_lobby(self, player_id: str) -> None:
        self.ensure_host(player_id)
        self.abort_round()

    def _reset_round(self) -> None:
        self.phase_deadline = None
        self.failed_player_ids = []
        for player in self.players.values():
            player.card = None
            player.placed = False
            player.in_round = False
            player.proposal = None
            player.proposed = False
            player.vote = None
            player.timed_out = False
        self.topic = None
        self.topic_author = None
        self.candidates = []
        self.turn_order = []
        self.turn_index = 0
        self.table = []
        self.reveal_index = 0
        self.outcome = None
        self.break_index = None
        self.drawing = []
        self.drawing_strokes = {}

    # ------------------------------------------------------------ fase de tema

    def set_timers(
        self, player_id: str, proposal_seconds: int, vote_seconds: int,
        placement_seconds: int = settings.placement_seconds,
    ) -> None:
        self.ensure_host(player_id)
        if self.phase not in (Phase.LOBBY, Phase.RESULT, Phase.PLACING):
            raise Conflict("round_running", "Cambia los tiempos entre rondas.")
        if self.phase is Phase.PLACING and (proposal_seconds != self.proposal_seconds
                                           or vote_seconds != self.vote_seconds):
            raise Conflict("round_running", "Durante un turno sólo puedes cambiar el tiempo de colocación.")
        if any(type(value) is not int or not 5 <= value <= 300
               for value in (proposal_seconds, vote_seconds, placement_seconds)):
            raise GameError("invalid_timer", "Los tiempos deben ser enteros entre 5 y 300 segundos.")
        if self.phase is Phase.PLACING and self.phase_deadline is not None:
            # Conserva el inicio del turno: editar la duración no reinicia el reloj.
            self.phase_deadline += placement_seconds - self.placement_seconds
        self.proposal_seconds = proposal_seconds
        self.vote_seconds = vote_seconds
        self.placement_seconds = placement_seconds
        self.touch()

    def propose_topic(self, player_id: str, text: str | None) -> Phase:
        """Registra la propuesta (o el paso) de un jugador.

        En cuanto han contestado todos los conectados se abre la votación sola.
        """
        if self.phase is not Phase.PROPOSING:
            raise Conflict("wrong_phase", "Ahora no toca proponer tema.")
        player = self.player_or_404(player_id)
        if player.proposed:
            raise Conflict("already_proposed", "Ya has enviado tu propuesta.")
        cleaned = clean_text(text or "", settings.max_topic_len)
        player.proposal = cleaned or None
        player.proposed = True
        self.touch()
        if not self.pending_proposals():
            self.close_proposals()
        return self.phase

    def close_proposals(self) -> None:
        if self.phase is not Phase.PROPOSING:
            raise Conflict("wrong_phase", "Ahora no toca cerrar las propuestas.")
        self.candidates = []
        seen: set[str] = set()
        for player in self.connected_players:
            if not player.proposal:
                continue
            key = player.proposal.casefold()
            if key in seen:
                continue
            seen.add(key)
            self.candidates.append(
                Candidate(
                    id=f"c{len(self.candidates)}",
                    text=player.proposal,
                    author_id=player.id,
                    author_name=player.name,
                )
            )
        # Siempre entra al menos un tema sorpresa, salvo que la papeleta ya esté llena.
        wanted = max(settings.min_candidates - len(self.candidates), 1)
        room_left = max(settings.max_candidates - len(self.candidates), 0)
        for text in sample_topics(self.topic_pool, min(wanted, room_left), seen, self.rng):
            self.candidates.append(Candidate(id=f"c{len(self.candidates)}", text=text))
        # El orden de la papeleta tampoco identifica a quien propuso cada tema.
        self.rng.shuffle(self.candidates)
        for i, candidate in enumerate(self.candidates):
            candidate.id = f"c{i}"
        self.phase = Phase.VOTING
        self.phase_deadline = mono() + self.vote_seconds
        self.touch()

    def vote_topic(self, player_id: str, candidate_id: str) -> Phase:
        if self.phase is not Phase.VOTING:
            raise Conflict("wrong_phase", "Ahora no toca votar.")
        player = self.player_or_404(player_id)
        if player.vote is not None:
            raise Conflict("already_voted", "Ya has votado.")
        if not any(c.id == candidate_id for c in self.candidates):
            raise NotFound("no_candidate", "Ese tema ya no está en la votación.")
        player.vote = candidate_id
        self.touch()
        if not self.pending_votes():
            self.close_voting()
        return self.phase

    def tally(self) -> dict[str, int]:
        counts = {c.id: 0 for c in self.candidates}
        for player in self.players.values():
            if player.vote in counts:
                counts[player.vote] += 1
        return counts

    def close_voting(self) -> None:
        if self.phase is not Phase.VOTING:
            raise Conflict("wrong_phase", "Ahora no toca cerrar la votación.")
        if not self.candidates:
            self.candidates = [
                Candidate(id="c0", text=text)
                for text in sample_topics(self.topic_pool, 1, set(), self.rng)
            ]
        counts = self.tally()
        best = max(counts.values())
        winner_id = self.rng.choice([cid for cid, votes in counts.items() if votes == best])
        winner = next(c for c in self.candidates if c.id == winner_id)

        self.topic = winner.text
        self.topic_author = winner.author_name
        # Un tema propuesto por un jugador que gana la votación se queda en la
        # sala y podrá salir como tema aleatorio en rondas futuras.
        if winner.author_id:
            known = {t.casefold() for t in self.topic_pool}
            if winner.text.casefold() not in known:
                self.topic_pool.append(winner.text)
                del self.topic_pool[:-40]
        self._deal()
        if self.phase is Phase.PLACING:
            key = winner.text.casefold()
            self.topic_counts[key] = self.topic_counts.get(key, 0) + 1

    # --------------------------------------------------------- fase de colocar

    def _deal(self) -> None:
        participants = self.connected_players
        if len(participants) < settings.min_players:
            self.abort_round()
            return
        for player, card in zip(participants, deal(len(participants), self.rng)):
            player.card = card
            player.in_round = True
            player.placed = False
        self.turn_order = [p.id for p in participants]
        self.rng.shuffle(self.turn_order)
        self.turn_index = 0
        self.table = []
        self.phase = Phase.PLACING
        self.phase_deadline = mono() + self.placement_seconds
        self.touch()

    def place_card(self, player_id: str, slot: int, answer: str) -> bool:
        """Coloca la carta boca abajo en `slot`.

        Devuelve `True` si con esto se cierra la colocación y la sala pasa a
        destapar; el runtime sólo tiene que llevar el ritmo del volteo.
        """
        if self.phase is not Phase.PLACING:
            raise Conflict("wrong_phase", "Ahora no toca colocar carta.")
        player = self.player_or_404(player_id)
        if self.current_player_id != player_id:
            raise Conflict("not_your_turn", "No es tu turno.")
        if self.phase_deadline is not None and mono() >= self.phase_deadline:
            raise Conflict("turn_expired", "Se ha agotado el tiempo de tu turno.")
        if player.card is None or player.placed:
            raise Conflict("no_card", "No tienes carta que colocar.")
        if not 0 <= slot <= len(self.table):
            raise GameError("bad_slot", "Esa posición no existe en la mesa.")
        cleaned = clean_text(answer, settings.max_answer_len)
        if not cleaned:
            raise GameError("empty_answer", "Di una palabra para acompañar a la carta.")

        self.table.insert(
            slot,
            Placement(
                player_id=player.id,
                player_name=player.name,
                color=player.color,
                card=player.card,
                answer=cleaned,
            ),
        )
        player.placed = True
        self.turn_index += 1
        self.phase_deadline = mono() + self.placement_seconds
        self.touch()
        return self._close_placing_if_done()

    def skip_turn(self, player_id: str) -> bool:
        """El anfitrión salta el turno de alguien que se ha caído."""
        self.ensure_host(player_id)
        if self.phase is not Phase.PLACING:
            raise Conflict("wrong_phase", "No hay ningún turno que saltar.")
        current = self.current_player_id
        if current is None:
            return True
        target = self.players.get(current)
        if target is not None and target.connected:
            raise Conflict("player_online", "Ese jugador sigue conectado: espera a que coloque.")
        return self._skip_current_turn()

    def timeout_turn(self) -> bool:
        """Salta exclusivamente el turno cuyo plazo ha vencido."""
        if (self.phase is not Phase.PLACING or self.phase_deadline is None
                or mono() < self.phase_deadline):
            return False
        return self._skip_current_turn(timed_out=True)

    def _skip_current_turn(self, timed_out: bool = False) -> bool:
        target = self.players.get(self.current_player_id)
        if target is not None:
            target.in_round = False
            target.card = None
            target.timed_out = timed_out
        self.turn_order.pop(self.turn_index)
        self.phase_deadline = mono() + self.placement_seconds
        self.touch()
        return self._close_placing_if_done()

    def _close_placing_if_done(self) -> bool:
        """Si ya no queda nadie por colocar, abre el destape (o aborta la ronda
        si no llegó a haber cartas sobre la mesa)."""
        if self.turn_index < len(self.turn_order):
            return False
        if not self.table:
            self.abort_round()
            return False
        self.begin_reveal()
        return True

    # -------------------------------------------------------------- destapado

    def begin_reveal(self) -> None:
        self.phase = Phase.REVEALING
        self.phase_deadline = None
        self.reveal_index = 0
        self.touch()

    def reveal_next(self) -> bool:
        """Destapa la siguiente carta. Devuelve `True` si aún quedan más."""
        if self.reveal_index < len(self.table):
            self.table[self.reveal_index].revealed = True
            self.reveal_index += 1
        self.touch()
        return self.reveal_index < len(self.table)

    def finish_reveal(self) -> None:
        if self.phase is not Phase.REVEALING:
            return
        ranked = [(i, p) for i, p in enumerate(self.table) if not p.card.is_joker]
        values = [p.card.value for _, p in ranked]
        # El empate no rompe el orden: sólo falla si una carta es mayor que la
        # que tiene a su derecha.
        self.break_index = next(
            (ranked[i][0] for i in range(len(values) - 1) if values[i] > values[i + 1]), None
        )
        self.failed_player_ids = [p.player_id for (_, p), expected in zip(ranked, sorted(values))
                                  if p.card.value != expected]
        for _, p in ranked:
            if p.player_id in self.failed_player_ids:
                record = self.hall_of_shame.setdefault(p.player_id, {
                    "playerId": p.player_id, "name": p.player_name, "color": p.color, "failures": 0,
                })
                record["failures"] += 1
        self.outcome = "lose" if self.break_index is not None else "win"
        if self.outcome == "win":
            self.wins += 1
            self.win_streak += 1
            self.best_streak = max(self.best_streak, self.win_streak)
        else:
            self.win_streak = 0
        self.phase = Phase.RESULT
        self.touch()

    # -------------------------------------------------------------------- chat

    def post_chat(self, player_id: str, text: str, reply_to_id: int | None = None) -> ChatMessage:
        """Publica un mensaje en el chat de la sala.

        Se guarda sólo una cola corta: el historial viaja dentro del estado de
        la sala, así que quien entra a mitad de partida ve el hilo reciente sin
        necesidad de un canal aparte.
        """
        player = self.player_or_404(player_id)
        cleaned = clean_text(text, settings.max_chat_len)
        if not cleaned:
            raise GameError("empty_message", "Escribe algo antes de enviarlo.")

        reply_to = None
        if reply_to_id is not None:
            if type(reply_to_id) is not int:
                raise GameError("invalid_reply", "La referencia al mensaje no es válida.")
            original = next((m for m in self.chat if m.id == reply_to_id), None)
            if original is None:
                raise NotFound("no_message", "Ese mensaje ya no está en el historial.")
            # Una cita plana sobrevive al recorte del historial sin anidar respuestas.
            reply_to = {"id": original.id, "playerName": original.player_name, "text": original.text}

        now = mono()
        if now - player.last_chat_at < settings.chat_cooldown:
            raise Conflict("too_fast", "Espera un momento entre mensaje y mensaje.")
        player.last_chat_at = now

        self.chat_seq += 1
        message = ChatMessage(
            id=self.chat_seq,
            player_id=player.id,
            player_name=player.name,
            color=player.color,
            text=cleaned,
            at=now,
            reply_to=reply_to,
        )
        self.chat.append(message)
        del self.chat[: -settings.chat_history]
        self.touch()
        return message

    # --------------------------------------------------------------- dibujo

    def add_drawing_segment(
        self, player_id: str, points: object, color: object, width: object,
        erase: object = False, start: object = True,
    ) -> DrawingSegment:
        if type(erase) is not bool or type(start) is not bool:
            raise GameError("invalid_drawing", "Ese trazo no es válido.")
        if type(color) is not int or not 0 <= color < PALETTE_SIZE:
            raise GameError("invalid_drawing", "Ese trazo no es válido.")
        if type(width) is not int or width not in (1, 2, 3):
            raise GameError("invalid_drawing", "Ese grosor de pincel no es válido.")
        if not isinstance(points, list) or not 2 <= len(points) <= MAX_DRAWING_POINTS:
            raise GameError("invalid_drawing", "Ese trazo no es válido.")

        clean_points: list[tuple[float, float]] = []
        for point in points:
            if not isinstance(point, dict):
                raise GameError("invalid_drawing", "Ese trazo no es válido.")
            x, y = point.get("x"), point.get("y")
            if any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
                   for value in (x, y)):
                raise GameError("invalid_drawing", "Ese trazo no es válido.")
            clean_points.append((round(float(x), 4), round(float(y), 4)))
        if len(set(clean_points)) == 1:
            raise GameError("invalid_drawing", "El trazo necesita algo de longitud.")
        if len(self.drawing) >= settings.max_drawing_segments:
            raise Conflict("drawing_full", "La mesa está llena de dibujos. Pide al anfitrión que la limpie.")

        player = self.player_or_404(player_id)
        if start or player.id not in self.drawing_strokes:
            self.drawing_stroke_seq += 1
            self.drawing_strokes[player.id] = self.drawing_stroke_seq
        self.drawing_seq += 1
        segment = DrawingSegment(
            id=self.drawing_seq,
            player_id=player.id,
            color=color,
            width=width,
            points=clean_points,
            stroke=self.drawing_strokes[player.id],
            erase=erase,
        )
        self.drawing.append(segment)
        self.touch()
        return segment

    def undo_drawing(self, player_id: str) -> None:
        """Quita el último trazo propio (pincel o goma), con todos sus segmentos."""
        player = self.player_or_404(player_id)
        own = [segment.stroke for segment in self.drawing if segment.player_id == player.id]
        if not own:
            raise Conflict("nothing_to_undo", "No te queda ningún trazo que deshacer.")
        last = max(own)
        self.drawing = [
            segment for segment in self.drawing
            if segment.player_id != player.id or segment.stroke != last
        ]
        self.touch()

    def clear_own_drawing(self, player_id: str) -> None:
        """Borra todo lo que ha pintado un jugador sin tocar lo de los demás."""
        player = self.player_or_404(player_id)
        remaining = [segment for segment in self.drawing if segment.player_id != player.id]
        if len(remaining) == len(self.drawing):
            raise Conflict("nothing_to_undo", "No tienes nada pintado en la mesa.")
        self.drawing = remaining
        self.touch()

    def clear_drawing(self, player_id: str) -> None:
        self.ensure_host(player_id)
        self.drawing = []
        self.drawing_strokes = {}
        self.touch()

    # ---------------------------------------------------------------- helpers

    def _pending(self, predicate: Callable[[Player], bool]) -> list[str]:
        return [p.id for p in self.connected_players if predicate(p)]

    def pending_proposals(self) -> list[str]:
        return self._pending(lambda p: not p.proposed)

    def pending_votes(self) -> list[str]:
        return self._pending(lambda p: p.vote is None)

    def is_empty(self) -> bool:
        return not self.players

    def nobody_connected(self) -> bool:
        return not self.connected_players
