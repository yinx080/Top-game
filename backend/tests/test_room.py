"""Reglas del juego: ciclo de ronda, temas, colocación y condición de victoria."""
from __future__ import annotations

import pytest

from app.config import settings
from app.deck import RANK_VALUE, Card, build_deck
from app.errors import Conflict, Forbidden, GameError
from app.room import Phase, Room


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
