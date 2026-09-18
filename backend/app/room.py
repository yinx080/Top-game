"""Estado de una sala y máquina de estados de la ronda.

Todo es síncrono y sin E/S: el runtime (`store.py`) es quien serializa los
accesos con un lock por sala y quien difunde los cambios por WebSocket.
"""
from __future__ import annotations

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
    # Estado de ronda
    card: Card | None = None
    placed: bool = False
    in_round: bool = False
    proposal: str | None = None
    proposed: bool = False
    vote: str | None = None


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


def clean_text(text: str, limit: int) -> str:
    return " ".join(text.split())[:limit].strip()


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
    updated_at: float = field(default_factory=time.time)

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
            disconnected_at=time.time(),
        )
        self.players[player.id] = player
        if not self.host_id:
            self.host_id = player.id
        self.touch()
        return player

    def remove_player(self, player_id: str) -> None:
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
        player.disconnected_at = None if connected else time.time()
        if not connected:
            self.advance_if_everyone_acted()
        self.touch()

    def touch(self) -> None:
        self.updated_at = time.time()

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
        for player in self.players.values():
            player.card = None
            player.placed = False
            player.in_round = False
            player.proposal = None
            player.proposed = False
            player.vote = None
        self.topic = None
        self.topic_author = None
        self.candidates = []
        self.turn_order = []
        self.turn_index = 0
        self.table = []
        self.reveal_index = 0
        self.outcome = None
        self.break_index = None

    # ------------------------------------------------------------ fase de tema

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
        self.phase = Phase.VOTING
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
        if target is not None:
            target.in_round = False
            target.card = None
        self.turn_order.pop(self.turn_index)
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
        values = [p.card.value for p in self.table]
        # El empate no rompe el orden: sólo falla si una carta es mayor que la
        # que tiene a su derecha.
        self.break_index = next(
            (i for i in range(len(values) - 1) if values[i] > values[i + 1]), None
        )
        self.outcome = "lose" if self.break_index is not None else "win"
        self.phase = Phase.RESULT
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
