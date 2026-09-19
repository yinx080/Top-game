"""Baraja francesa y valores de carta."""
from __future__ import annotations

import random
from dataclasses import dataclass

# El README numera el As como 1 y la K como 12. Mantenemos esa intención (As la
# carta más baja, K la más alta) pero con la baraja francesa completa: son 13
# rangos, así que la K vale 13. Un rango extra sólo reparte mejor los valores
# entre los jugadores y no cambia ninguna regla.
RANKS: tuple[str, ...] = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS: tuple[str, ...] = ("S", "H", "D", "C")
SUIT_NAMES = {"S": "picas", "H": "corazones", "D": "diamantes", "C": "tréboles"}

RANK_VALUE = {rank: i + 1 for i, rank in enumerate(RANKS)}
MIN_VALUE = 1
MAX_VALUE = len(RANKS)
JOKER_CHANCE = 0.01


@dataclass(frozen=True, slots=True)
class Card:
    rank: str
    suit: str

    @property
    def value(self) -> int:
        return 0 if self.is_joker else RANK_VALUE[self.rank]

    @property
    def is_joker(self) -> bool:
        return self.rank == "joker"

    @property
    def code(self) -> str:
        """Identificador que coincide con el nombre del PNG (`KD`, `10H`, `AS`)."""
        return "joker" if self.is_joker else f"{self.rank}{self.suit}"

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code, "rank": self.rank, "suit": self.suit, "value": self.value}


def build_deck() -> list[Card]:
    return [Card(rank, suit) for suit in SUITS for rank in RANKS]


def deal(count: int, rng: random.Random | None = None) -> list[Card]:
    """Reparte `count` cartas distintas de una baraja barajada.

    Dos jugadores pueden recibir el mismo valor con palos distintos: el empate
    está contemplado en las reglas y sigue contando como victoria.
    """
    deck = build_deck()
    rng = rng or random
    rng.shuffle(deck)
    if count > len(deck):
        raise ValueError("no hay cartas suficientes en la baraja")
    cards = deck[:count]
    if cards and rng.random() < JOKER_CHANCE:
        cards[rng.randrange(len(cards))] = Card("joker", "")
    return cards
