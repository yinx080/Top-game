"""Reglas del juego: ciclo de ronda, temas, colocación y condición de victoria."""
from __future__ import annotations

import contextlib
import pytest

from app.config import settings
from app.deck import RANK_VALUE, Card, build_deck
from app.errors import Conflict, Forbidden, GameError
from app.room import Phase, Room


class FakeSocket:
    """Recoge lo que la sala difunde, para comprobar qué ven los clientes."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


def make_room(names=("Ana", "Beto", "Cris"), **kwargs) -> Room:
    room = Room.create(
        code="TEST01",
        name=kwargs.pop("name", "Sala de pruebas"),
        is_private=kwargs.pop("is_private", False),
        password=kwargs.pop("password", None),
        max_players=kwargs.pop("max_players", 8),
    )
    for name in names:
        player = room.add_player(name)
        room.set_connected(player.id, True)
    return room


def run_topic_phase(room: Room, proposals: dict[str, str | None] | None = None) -> None:
    """Lleva la sala de LOBBY a PLACING pasando por propuesta y votación."""
    room.start_round(room.host_id)
    proposals = proposals or {}
    for player in room.connected_players:
        room.propose_topic(player.id, proposals.get(player.id))
    assert room.phase is Phase.VOTING
    for player in room.connected_players:
        room.vote_topic(player.id, room.candidates[0].id)
    assert room.phase is Phase.PLACING


def force_cards(room: Room, values: list[int]) -> None:
    """Fija la carta de cada jugador en el orden de `turn_order`."""
    ranks = {v: r for r, v in RANK_VALUE.items()}
    for player_id, value in zip(room.turn_order, values):
        room.players[player_id].card = Card(ranks[value], "S")


# --------------------------------------------------------------------- baraja


def test_deck_is_a_full_french_deck():
    deck = build_deck()
    assert len(deck) == 52
    assert len(set(deck)) == 52
    assert min(c.value for c in deck) == 1
    assert max(c.value for c in deck) == 13
    assert Card("A", "S").value < Card("K", "S").value


def test_card_code_matches_asset_name():
    assert Card("10", "H").code == "10H"
    assert Card("A", "S").code == "AS"


# ------------------------------------------------------------------- jugadores


def test_first_player_becomes_host_and_names_are_unique():
    room = make_room(("Ana", "Ana", "Ana"))
    names = [p.name for p in room.players.values()]
    assert names == ["Ana", "Ana (2)", "Ana (3)"]
    assert room.host_id == next(iter(room.players))


def test_new_player_is_offline_until_the_socket_opens():
    room = Room.create(code="X", name="Sala", is_private=False, password=None, max_players=4)
    player = room.add_player("Ana")
    assert not player.connected
    assert room.connected_players == []


def test_room_is_capped():
    room = make_room(("Ana", "Beto"), max_players=2)
    with pytest.raises(Conflict):
        room.add_player("Cris")


def test_private_room_requires_the_right_password():
    room = Room.create(code="X", name="Privada", is_private=True, password="hola", max_players=4)
    with pytest.raises(Forbidden):
        room.add_player("Ana", "adios")
    assert room.add_player("Ana", "hola").name == "Ana"


def test_private_room_needs_a_password_to_exist():
    with pytest.raises(GameError):
        Room.create(code="X", name="Privada", is_private=True, password=None, max_players=4)


def test_host_moves_on_when_the_host_leaves():
    room = make_room()
    host = room.host_id
    room.remove_player(host)
    assert room.host_id != host
    assert room.host_id in room.players


# ----------------------------------------------------------------- fase temas


def test_round_needs_enough_connected_players():
    room = make_room(("Ana",))
    with pytest.raises(Conflict):
        room.start_round(room.host_id)


def test_only_the_host_starts_the_round():
    room = make_room()
    other = [p for p in room.players if p != room.host_id][0]
    with pytest.raises(Forbidden):
        room.start_round(other)


def test_ballot_mixes_proposals_with_at_least_one_random_topic():
    room = make_room()
    room.start_round(room.host_id)
    ids = list(room.players)
    room.propose_topic(ids[0], "Cosas de menos a más caras")
    room.propose_topic(ids[1], "Cosas de menos a más caras")  # duplicado exacto
    room.propose_topic(ids[2], None)                          # pasa
    assert room.phase is Phase.VOTING

    texts = [c.text for c in room.candidates]
    assert texts.count("Cosas de menos a más caras") == 1
    assert any(c.author_id is None for c in room.candidates)
    assert len(room.candidates) >= settings.min_candidates


def test_a_winning_player_topic_is_kept_for_future_rounds():
    room = make_room()
    room.start_round(room.host_id)
    ids = list(room.players)
    room.propose_topic(ids[0], "Postres de menos a más pesados")
    room.propose_topic(ids[1], None)
    room.propose_topic(ids[2], None)

    mine = next(c for c in room.candidates if c.author_id == ids[0])
    for pid in ids:
        room.vote_topic(pid, mine.id)

    assert room.topic == "Postres de menos a más pesados"
    assert room.topic_author == room.players[ids[0]].name
    assert "Postres de menos a más pesados" in room.topic_pool


def test_a_random_topic_is_not_stored_in_the_room_pool():
    room = make_room()
    run_topic_phase(room)
    if room.candidates[0].author_id is None:
        assert room.topic_pool == []


def test_you_cannot_vote_twice():
    room = make_room()
    room.start_round(room.host_id)
    for player in room.connected_players:
        room.propose_topic(player.id, None)
    first = next(iter(room.players))
    room.vote_topic(first, room.candidates[0].id)
    with pytest.raises(Conflict):
        room.vote_topic(first, room.candidates[0].id)


def test_host_can_close_the_phases_without_the_stragglers():
    room = make_room()
    room.start_round(room.host_id)
    room.propose_topic(room.host_id, "Animales de menos a más ruidosos")
    assert room.phase is Phase.PROPOSING
    room.close_proposals()
    assert room.phase is Phase.VOTING
    room.close_voting()  # nadie ha votado: sale uno al azar
    assert room.phase is Phase.PLACING
    assert room.topic


# -------------------------------------------------------------- fase colocar


def test_everyone_gets_one_card_and_a_turn():
    room = make_room()
    run_topic_phase(room)
    assert len(room.turn_order) == 3
    assert sorted(room.turn_order) == sorted(room.players)
    assert all(p.card is not None for p in room.players.values())


def test_turns_are_strict():
    room = make_room()
    run_topic_phase(room)
    not_yet = room.turn_order[1]
    with pytest.raises(Conflict):
        room.place_card(not_yet, 0, "melón")


def test_answer_cannot_be_blank():
    room = make_room()
    run_topic_phase(room)
    with pytest.raises(GameError):
        room.place_card(room.turn_order[0], 0, "   ")


def test_slot_must_exist():
    room = make_room()
    run_topic_phase(room)
    with pytest.raises(GameError):
        room.place_card(room.turn_order[0], 3, "melón")


def test_cards_are_inserted_where_the_player_says():
    room = make_room()
    run_topic_phase(room)
    order = list(room.turn_order)
    room.place_card(order[0], 0, "uno")
    room.place_card(order[1], 0, "dos")     # a la izquierda
    done = room.place_card(order[2], 1, "tres")  # entre las dos
    assert done
    assert [p.answer for p in room.table] == ["dos", "tres", "uno"]


def test_a_placed_card_stops_travelling_to_the_owner():
    from app.views import room_view

    room = make_room()
    run_topic_phase(room)
    first = room.turn_order[0]
    assert room_view(room, first)["you"]["card"] is not None
    room.place_card(first, 0, "uno")
    assert room_view(room, first)["you"]["card"] is None


def test_nobody_sees_anyone_elses_card():
    from app.views import room_view

    room = make_room()
    run_topic_phase(room)
    other = room.turn_order[1]
    view = room_view(room, room.turn_order[0])
    assert all(p.get("card") is None for p in view["players"])
    assert other not in str(view.get("you", {}).get("card"))


def test_host_can_only_skip_a_disconnected_player():
    room = make_room()
    run_topic_phase(room)
    with pytest.raises(Conflict):
        room.skip_turn(room.host_id)

    stuck = room.turn_order[0]
    room.set_connected(stuck, False)
    room.skip_turn(room.host_id)
    assert room.current_player_id != stuck
    assert len(room.turn_order) == 2


# ------------------------------------------------------------ destape y final


def place_all(room: Room, values: list[int], slots: list[int]) -> None:
    force_cards(room, values)
    order = list(room.turn_order)
    for player_id, slot in zip(order, slots):
        room.place_card(player_id, slot, f"palabra-{slot}")


def reveal_all(room: Room) -> None:
    room.begin_reveal()
    while room.reveal_next():
        pass
    room.finish_reveal()


def test_ordered_table_wins():
    room = make_room()
    run_topic_phase(room)
    place_all(room, [5, 9, 7], [0, 1, 1])  # mesa: 5, 7, 9
    reveal_all(room)
    assert [p.card.value for p in room.table] == [5, 7, 9]
    assert room.outcome == "win"
    assert room.break_index is None


def test_a_tie_still_wins():
    room = make_room()
    run_topic_phase(room)
    place_all(room, [4, 4, 9], [0, 1, 2])
    reveal_all(room)
    assert [p.card.value for p in room.table] == [4, 4, 9]
    assert room.outcome == "win"


def test_out_of_order_loses_and_points_at_the_break():
    room = make_room()
    run_topic_phase(room)
    place_all(room, [2, 11, 6], [0, 1, 2])  # mesa: 2, 11, 6
    reveal_all(room)
    assert room.outcome == "lose"
    assert room.break_index == 1


def test_reveal_goes_left_to_right_one_at_a_time():
    room = make_room()
    run_topic_phase(room)
    place_all(room, [3, 8, 5], [0, 1, 1])
    room.begin_reveal()
    room.reveal_next()
    assert [p.revealed for p in room.table] == [True, False, False]
    room.reveal_next()
    assert [p.revealed for p in room.table] == [True, True, False]


def test_next_round_clears_the_table_but_keeps_the_topic_pool():
    room = make_room()
    run_topic_phase(room, {room.host_id: "Ciudades de menos a más frías"})
    # el tema propuesto puede o no ganar; forzamos el fondo para la comprobación
    room.topic_pool.append("Ciudades de menos a más frías")
    place_all(room, [1, 2, 3], [0, 1, 2])
    reveal_all(room)
    assert room.phase is Phase.RESULT

    room.start_round(room.host_id)
    assert room.phase is Phase.PROPOSING
    assert room.table == []
    assert room.outcome is None
    assert room.round_no == 2
    assert "Ciudades de menos a más frías" in room.topic_pool


# --------------------------------------------------------------- abandonos


def test_leaving_mid_round_keeps_the_card_already_on_the_table():
    room = make_room(("Ana", "Beto", "Cris", "Dani"))
    run_topic_phase(room)
    first, expected_next = room.turn_order[0], room.turn_order[1]
    name = room.players[first].name
    room.place_card(first, 0, "manzana")
    room.remove_player(first)

    assert len(room.table) == 1
    assert room.table[0].player_name == name
    # el turno no salta a nadie: sigue tocándole a quien le tocaba
    assert room.current_player_id == expected_next
    assert len(room.turn_order) == 3


def test_dropping_below_the_minimum_aborts_the_round():
    room = make_room()
    run_topic_phase(room)
    for player_id in list(room.players)[:2]:
        room.remove_player(player_id)
    assert room.phase is Phase.LOBBY
    assert room.table == []


def test_a_leaver_closes_the_proposal_phase_for_everyone_else():
    room = make_room()
    room.start_round(room.host_id)
    ids = list(room.players)
    room.propose_topic(ids[0], "Ruidos, de menos a más molestos")
    room.propose_topic(ids[1], None)
    assert room.phase is Phase.PROPOSING
    room.remove_player(ids[2])  # el último rezagado se marcha
    assert room.phase is Phase.VOTING


def test_a_disconnection_closes_the_vote_for_everyone_else():
    room = make_room()
    room.start_round(room.host_id)
    for player in room.connected_players:
        room.propose_topic(player.id, None)
    ids = list(room.players)
    room.vote_topic(ids[0], room.candidates[0].id)
    room.vote_topic(ids[1], room.candidates[0].id)
    assert room.phase is Phase.VOTING
    room.set_connected(ids[2], False)
    assert room.phase is Phase.PLACING


def test_the_last_placer_leaving_opens_the_reveal():
    room = make_room()
    run_topic_phase(room)
    order = list(room.turn_order)
    room.place_card(order[0], 0, "uno")
    room.place_card(order[1], 1, "dos")
    assert room.phase is Phase.PLACING
    room.remove_player(order[2])  # se va sin colocar y ya no queda nadie
    assert room.phase is Phase.REVEALING
    assert len(room.table) == 2


def test_the_current_players_disconnection_does_not_skip_the_turn():
    room = make_room()
    run_topic_phase(room)
    current = room.current_player_id
    room.set_connected(current, False)
    assert room.phase is Phase.PLACING
    assert room.current_player_id == current  # sigue siendo su turno


def test_a_saved_topic_comes_back_as_a_random_candidate():
    room = make_room()
    room.topic_pool.append("Cafés de esta sala, de menos a más cargados")
    room.start_round(room.host_id)
    for player in room.connected_players:
        room.propose_topic(player.id, None)
    texts = [c.text for c in room.candidates]
    assert "Cafés de esta sala, de menos a más cargados" in texts


# -------------------------------------------------------------------- chat


def test_chat_keeps_who_said_what():
    room = make_room()
    ana = next(iter(room.players.values()))
    message = room.post_chat(ana.id, "  ¿empezamos   ya?  ")
    assert message.text == "¿empezamos ya?"   # espacios colapsados
    assert message.player_name == ana.name
    assert message.color == ana.color
    assert room.chat == [message]


def test_chat_rejects_empty_messages():
    room = make_room()
    ana = next(iter(room.players))
    with pytest.raises(GameError):
        room.post_chat(ana, "   \n\t  ")


def test_chat_drops_control_characters():
    room = make_room()
    ana = next(iter(room.players))
    assert room.post_chat(ana, "hola\x00\x07 mundo").text == "hola mundo"


def test_chat_is_rate_limited_per_player():
    room = make_room()
    ids = list(room.players)
    room.post_chat(ids[0], "uno")
    with pytest.raises(Conflict):
        room.post_chat(ids[0], "dos")
    room.post_chat(ids[1], "otro jugador sí puede")  # el límite es por persona


def test_chat_history_is_capped():
    room = make_room()
    ids = list(room.players)
    for n in range(settings.chat_history + 10):
        # Alternamos jugadores para no chocar con el límite de frecuencia.
        room.players[ids[n % 2]].last_chat_at = 0.0
        room.post_chat(ids[n % 2], f"mensaje {n}")
    assert len(room.chat) == settings.chat_history
    assert room.chat[-1].text == f"mensaje {settings.chat_history + 9}"


def test_chat_survives_a_new_round():
    room = make_room()
    room.post_chat(room.host_id, "esto no se borra")
    run_topic_phase(room)
    assert [m.text for m in room.chat] == ["esto no se borra"]


def test_chat_travels_inside_the_room_state():
    from app.views import room_view

    room = make_room()
    ana = next(iter(room.players))
    room.post_chat(ana, "hola a todos")
    chat = room_view(room, ana)["chat"]
    assert [m["text"] for m in chat] == ["hola a todos"]
    assert chat[0]["playerId"] == ana


# ------------------------------------------------------------------ dibujo


def test_drawing_is_validated_attributed_serialized_and_cleared_next_round():
    from app.views import room_view

    room = make_room()
    guest = next(pid for pid in room.players if pid != room.host_id)
    segment = room.add_drawing_segment(
        guest,
        [{"x": 0.123456, "y": 0.2}, {"x": 0.4, "y": 0.5}, {"x": 0.8, "y": 1}],
        7,
        3,
    )

    assert (segment.player_id, segment.color, segment.width) == (guest, 7, 3)
    assert segment.points[0] == (0.1235, 0.2)
    assert room_view(room, room.host_id)["drawing"] == [{
        "id": 1,
        "playerId": guest,
        "color": 7,
        "width": 3,
        "points": [{"x": 0.1235, "y": 0.2}, {"x": 0.4, "y": 0.5}, {"x": 0.8, "y": 1.0}],
    }]

    for bad in (None, True, "0.2", -0.1, 1.1, float("nan"), float("inf")):
        with pytest.raises(GameError, match="trazo"):
            room.add_drawing_segment(guest, [{"x": bad, "y": 0.2}, {"x": 0.8, "y": 0.9}], 0, 2)
    with pytest.raises(GameError):
        room.add_drawing_segment(guest, [{"x": 0.2, "y": 0.2}] * 2, 0, 2)
    for bad_color, bad_width in ((10, 2), (True, 2), (0, 0), (0, 4), (0, "2")):
        with pytest.raises(GameError):
            room.add_drawing_segment(
                guest, [{"x": 0, "y": 0}, {"x": 1, "y": 1}], bad_color, bad_width,
            )
    with pytest.raises(Forbidden):
        room.clear_drawing(guest)

    room.start_round(room.host_id)
    assert room.drawing == []
    assert room.drawing_seq == 1


def test_host_can_clear_drawing_without_reusing_segment_ids():
    room = make_room()
    room.add_drawing_segment(room.host_id, [{"x": 0, "y": 0}, {"x": 1, "y": 1}], 0, 1)
    room.clear_drawing(room.host_id)
    assert room.drawing == []
    assert room.add_drawing_segment(
        room.host_id, [{"x": 0, "y": 1}, {"x": 1, "y": 0}], 2, 3,
    ).id == 2


@pytest.mark.parametrize("joker_slot", [0, 1, 2])
@pytest.mark.parametrize("values, outcome", [([3, 9], "win"), ([9, 3], "lose")])
def test_joker_fits_anywhere_but_does_not_hide_other_errors(joker_slot, values, outcome):
    room = make_room()
    run_topic_phase(room)
    cards = [Card(str(value), "S") for value in values]
    cards.insert(joker_slot, Card("joker", ""))
    for index, (pid, card) in enumerate(zip(room.turn_order, cards)):
        room.players[pid].card = card
        room.place_card(pid, index, "palabra")
    reveal_all(room)
    assert room.outcome == outcome
    assert room.table[joker_slot].player_id not in room.failed_player_ids
    assert len(room.failed_player_ids) == (0 if outcome == "win" else 2)
    assert cards[joker_slot].as_dict()["code"] == "joker"


def test_joker_deal_probability_and_unique_cards(monkeypatch):
    import random
    from app.deck import deal

    rng = random.Random(42)
    monkeypatch.setattr(rng, "random", lambda: 0.009)
    cards = deal(10, rng)
    assert sum(card.is_joker for card in cards) == 1
    assert len(cards) == len(set(cards)) == 10
    monkeypatch.setattr(rng, "random", lambda: 0.01)
    assert not any(card.is_joker for card in deal(10, rng))


def test_streaks_and_all_failures_survive_rounds_and_departures():
    room = make_room(("Ana", "Beto", "Cris", "Dani", "Eva"))
    for _ in range(2):
        run_topic_phase(room)
        place_all(room, [1, 2, 3, 4, 5], [0, 1, 2, 3, 4])
        reveal_all(room)
        room.finish_reveal()  # un resultado repetido no vuelve a sumar
    assert (room.wins, room.win_streak, room.best_streak) == (2, 2, 2)
    run_topic_phase(room)
    place_all(room, [2, 1, 3, 5, 4], [0, 1, 2, 3, 4])
    reveal_all(room)
    expected = [p.player_id for i, p in enumerate(room.table) if i != 2]
    assert room.failed_player_ids == expected
    assert (room.wins, room.win_streak, room.best_streak) == (2, 0, 2)
    room.finish_reveal()
    assert all(p["failures"] == 1 for p in room.hall_of_shame.values())
    room.remove_player(expected[0])
    room.back_to_lobby(room.host_id)
    assert set(room.hall_of_shame) == set(expected)
    assert room.failed_player_ids == []
    assert room.wins == 2
    run_topic_phase(room)
    place_all(room, [4, 3, 2, 1], [0, 1, 2, 3])
    reveal_all(room)
    assert all(room.hall_of_shame[pid]["failures"] == 2 for pid in expected[1:])


def test_timer_settings_validate_permissions_ranges_and_phase():
    room = make_room()
    guest = next(pid for pid in room.players if pid != room.host_id)
    with pytest.raises(Forbidden):
        room.set_timers(guest, 30, 20)
    for value in (None, True, 4, 301, 5.5, "30"):
        with pytest.raises(GameError):
            room.set_timers(room.host_id, value, 30)
    room.set_timers(room.host_id, 60, 15)
    room.start_round(room.host_id)
    assert room.phase_deadline is not None
    with pytest.raises(Conflict):
        room.set_timers(room.host_id, 30, 30)
    room.abort_round()
    assert room.phase_deadline is None
    assert (room.proposal_seconds, room.vote_seconds) == (60, 15)


@pytest.mark.asyncio
async def test_phase_timers_advance_without_messages_and_cancel_on_abort():
    import asyncio
    from app.store import RoomRuntime

    room = make_room()
    runtime = RoomRuntime(room)
    room.proposal_seconds = room.vote_seconds = 0.01
    try:
        room.start_round(room.host_id)
        await runtime.broadcast()

        async def wait_for_placing():
            while room.phase is not Phase.PLACING:
                await asyncio.sleep(0.001)

        await asyncio.wait_for(wait_for_placing(), timeout=1)
        assert room.phase_deadline is not None
        assert runtime.phase_task is not None
        assert sum(room.topic_counts.values()) == 1
        room.abort_round()
        room.start_round(room.host_id)
        await runtime.broadcast()
        timer = runtime.phase_task
        room.abort_round()
        await runtime.broadcast()
        await asyncio.sleep(0.03)
        assert room.phase is Phase.LOBBY
        assert timer.cancelled()
    finally:
        runtime.cancel_timers()


def test_placement_deadlines_reset_only_when_the_turn_changes(monkeypatch):
    from app import room as room_module

    now = 1000.0
    monkeypatch.setattr(room_module.time, "monotonic", lambda: now)
    room = make_room(("Ana", "Beto", "Cris", "Dani"))
    run_topic_phase(room)
    first, second, third, fourth = room.turn_order
    assert room.phase_deadline == 1030
    now += 3
    room.place_card(first, 0, "Una frase mucho más larga que antes")
    assert room.phase_deadline == 1033
    now += 2
    room.set_connected(second, False)
    room.set_connected(second, True)
    room.remove_player(fourth)
    assert room.phase_deadline == 1033
    room.remove_player(second)
    assert room.current_player_id == third
    assert room.phase_deadline == 1035
    room.place_card(third, 1, "final")
    assert room.phase is Phase.REVEALING
    assert room.phase_deadline is None


def test_expired_turn_cannot_place_and_advances_once(monkeypatch):
    from app import room as room_module

    now = 1000.0
    monkeypatch.setattr(room_module.time, "monotonic", lambda: now)
    room = make_room()
    run_topic_phase(room)
    first, second, _ = room.turn_order
    room.timeout_turn()  # aún tiene tiempo
    assert room.current_player_id == first
    now = 1030
    with pytest.raises(Conflict, match="agotado"):
        room.place_card(first, 0, "demasiado tarde")
    room.timeout_turn()
    assert room.current_player_id == second
    assert room.players[first].timed_out
    assert room.players[first].card is None
    assert room.phase_deadline == 1060
    room.timeout_turn()
    assert room.current_player_id == second
    now = 1060
    room.timeout_turn()
    now = 1090
    room.timeout_turn()
    assert room.phase is Phase.LOBBY  # nadie colocó
    assert room.phase_deadline is None
    assert room.wins == 0


@pytest.mark.asyncio
async def test_last_placement_timeout_starts_reveal(monkeypatch):
    import asyncio
    import dataclasses
    from app import store as store_module

    quick = dataclasses.replace(settings, reveal_step=0.001, reveal_tail=0.001)
    monkeypatch.setattr(store_module, "settings", quick)
    room = make_room()
    run_topic_phase(room)
    first, second, last = room.turn_order
    force_cards(room, [1, 2, 3])
    room.place_card(first, 0, "uno")
    room.place_card(second, 1, "dos")
    room.phase_deadline = 1  # plazo ya vencido
    runtime = store_module.RoomRuntime(room)
    try:
        await runtime.broadcast()
        async def wait_for_result():
            while room.phase is not Phase.RESULT:
                await asyncio.sleep(0.001)
        await asyncio.wait_for(wait_for_result(), timeout=1)
        assert room.players[last].timed_out
        assert len(room.table) == 2
        assert room.outcome == "win"
        assert runtime.phase_task is None
    finally:
        runtime.cancel_timers()


def test_anonymous_topics_and_long_texts_are_serialized_without_authors():
    from app.views import room_view

    room = make_room()
    host = room.host_id
    guest = next(pid for pid in room.players if pid != host)
    text = "Una escala bastante más detallada " + "x" * 140
    assert 70 < len(text) <= settings.max_topic_len
    room.start_round(host)
    room.propose_topic(host, text)
    room.close_proposals()
    candidates = room_view(room, guest)["candidates"]
    assert any(c["text"] == text for c in candidates)
    assert all("author" not in c and "authorId" not in c for c in candidates)
    mine = next(c for c in room.candidates if c.author_id == host)
    for pid in list(room.players):
        room.vote_topic(pid, mine.id)
    assert room_view(room, guest)["topic"] == {"text": text}
    answer = "Una respuesta larga con detalles que antes no cabían en el límite"
    first = room.current_player_id
    room.place_card(first, 0, answer)
    assert room.table[0].answer == answer
    room.place_card(room.current_player_id, 1, "x" * 100)
    assert len(room.table[1].answer) == settings.max_answer_len
    room.abort_round()
    room.start_round(host)
    room.propose_topic(host, "x" * 250)
    assert len(room.players[host].proposal) == settings.max_topic_len


def test_chat_replies_keep_a_server_owned_flat_quote():
    from app.views import room_view

    room = make_room()
    first, second, third = list(room.players)
    original = room.post_chat(first, "¿Dónde pondrías un melón?")
    reply = room.post_chat(second, "En el medio", original.id)
    nested = room.post_chat(third, "De acuerdo", reply.id)
    assert reply.reply_to == {"id": original.id, "playerName": original.player_name, "text": original.text}
    assert nested.reply_to == {"id": reply.id, "playerName": reply.player_name, "text": reply.text}
    room.chat.remove(original)
    assert room_view(room, third)["chat"][0]["replyTo"]["text"] == original.text
    room.players[second].last_chat_at = 0
    for bad in (True, "2", {}, 1.5):
        with pytest.raises(GameError):
            room.post_chat(second, "respuesta", bad)
    with pytest.raises(GameError):
        room.post_chat(second, "respuesta", original.id)


def test_host_can_edit_each_turn_duration_without_resetting_elapsed_time(monkeypatch):
    from app import room as room_module
    from app.views import room_view

    now = 1000.0
    monkeypatch.setattr(room_module.time, "monotonic", lambda: now)
    room = make_room()
    assert room.placement_seconds == 30
    run_topic_phase(room)
    first, second, _ = room.turn_order
    guest = next(pid for pid in room.players if pid != room.host_id)
    now += 8
    with pytest.raises(Forbidden):
        room.set_timers(guest, room.proposal_seconds, room.vote_seconds, 60)
    for invalid in (None, True, 0, 301, 5.5, "60"):
        with pytest.raises(GameError):
            room.set_timers(room.host_id, room.proposal_seconds, room.vote_seconds, invalid)
    room.set_timers(room.host_id, room.proposal_seconds, room.vote_seconds, 60)
    assert room.phase_deadline == 1060  # quedan 52, no 60
    assert room_view(room, guest)["placementSeconds"] == 60
    assert room_view(room, guest)["phaseDeadline"] == 1060
    now += 2
    room.set_timers(room.host_id, room.proposal_seconds, room.vote_seconds, 20)
    assert room.phase_deadline == 1020  # quedan 10
    room.place_card(first, 0, "respuesta")
    assert room.current_player_id == second
    assert room.phase_deadline == 1030  # el nuevo turno tiene 20 segundos completos
    room.set_timers(room.host_id, room.proposal_seconds, room.vote_seconds, 40)
    assert room.phase_deadline == 1050
    with pytest.raises(Conflict):
        room.set_timers(room.host_id, room.proposal_seconds + 1, room.vote_seconds, 40)


@pytest.mark.asyncio
async def test_editing_duration_cancels_old_timer_and_shortening_can_expire_now():
    import asyncio
    import time
    from app.store import RoomRuntime

    room = make_room()
    run_topic_phase(room)
    first = room.current_player_id
    runtime = RoomRuntime(room)
    try:
        await runtime.broadcast()
        original_task = runtime.phase_task
        deadline = room.phase_deadline
        room.set_timers(room.host_id, room.proposal_seconds, room.vote_seconds, 60)
        await runtime.broadcast()
        await asyncio.sleep(0)
        assert original_task.cancelled()
        assert room.phase_deadline == deadline + 30
        # Han pasado 20 segundos desde el inicio de un turno de 60.
        room.phase_deadline = time.monotonic() + 40
        room.set_timers(room.host_id, room.proposal_seconds, room.vote_seconds, 5)
        await runtime.broadcast()
        async def wait_for_timeout():
            while room.current_player_id == first:
                await asyncio.sleep(0.001)
        await asyncio.wait_for(wait_for_timeout(), timeout=1)
        assert room.players[first].timed_out
        assert 4 < room.phase_deadline - time.monotonic() <= 5
    finally:
        runtime.cancel_timers()


@pytest.mark.asyncio
async def test_timer_waking_up_early_still_expires_the_turn(monkeypatch):
    """Regresión: el temporizador despertaba antes de tiempo y dejaba la sala
    muerta.

    Los plazos iban en `time.time()` y la espera en el reloj monotónico de
    `asyncio.sleep`. Si el primero se quedaba corto, `timeout_turn()` no hacía
    nada, el plazo no cambiaba y por tanto no se rearmaba ningún temporizador:
    nadie volvía a pasar el turno y `place_card` rechazaba para siempre con
    `turn_expired`, así que al jugador no le quedaba más que salirse.
    """
    import asyncio

    from app.room import mono
    from app.store import RoomRuntime

    room = make_room()
    run_topic_phase(room)
    runtime = RoomRuntime(room)
    first = room.current_player_id
    socket = FakeSocket()
    runtime.attach(first, socket)
    room.phase_deadline = mono() + 0.05
    deadline = room.phase_deadline

    real_sleep = asyncio.sleep
    calls = []

    async def early_sleep(delay):
        # Despierta siempre antes de tiempo, como haría un reloj desajustado.
        calls.append(delay)
        await real_sleep(min(delay, 0.01))

    monkeypatch.setattr(asyncio, "sleep", early_sleep)
    try:
        await asyncio.wait_for(runtime._run_phase_timer(deadline), timeout=2)
    finally:
        monkeypatch.undo()
        runtime.cancel_timers()

    assert len(calls) > 1, "debería haber reintentado en vez de darlo por vencido"
    assert room.players[first].timed_out
    assert room.current_player_id != first
    assert room.phase_deadline != deadline
    # Y, sobre todo, los clientes tienen que enterarse: saltar el turno por
    # dentro sin difundir el evento dejaba la partida congelada en pantalla.
    kinds = [p.get("event", {}).get("kind") for p in socket.sent]
    assert "turn_timeout" in kinds, kinds
    assert socket.sent[-1]["room"]["currentPlayerId"] != first


@pytest.mark.asyncio
async def test_dead_phase_timer_is_rearmed_even_with_the_same_deadline():
    """Si la tarea del temporizador muere, hay que volver a armarla: antes se
    comparaba sólo el plazo y una sala sin temporizador se quedaba colgada."""
    import asyncio

    from app.store import RoomRuntime

    room = make_room()
    run_topic_phase(room)
    runtime = RoomRuntime(room)
    try:
        await runtime.broadcast()
        first_task = runtime.phase_task
        assert first_task is not None

        # La tarea muere sin que el plazo cambie (un fallo, una cancelación...).
        first_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await first_task
        assert runtime.scheduled_deadline == room.phase_deadline

        runtime.schedule_phase_timer()
        assert runtime.phase_task is not first_task
        assert not runtime.phase_task.done()
    finally:
        runtime.cancel_timers()


@pytest.mark.asyncio
async def test_sweep_rearms_a_room_left_without_timer():
    """El barrendero es la última red: recupera una sala sin temporizador."""
    import asyncio

    from app.store import RoomStore

    store = RoomStore()
    runtime = store.create(name="Sala", is_private=False, password=None, max_players=8)
    for name in ("Ana", "Beto", "Cris"):
        player = runtime.room.add_player(name)
        runtime.room.set_connected(player.id, True)
    run_topic_phase(runtime.room)
    try:
        await runtime.broadcast()
        task = runtime.phase_task
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        await store.sweep()

        assert runtime.phase_task is not task
        assert not runtime.phase_task.done()
    finally:
        runtime.cancel_timers()
