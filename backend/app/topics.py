"""Fondo de temas para el top de cada ronda.

La lista es la misma que `data/hot_topics.md`, el fondo que se juega en las
salas; se mantiene aquí embebida porque la carpeta `data/` no viaja en la
imagen de Docker. Si se edita el `.md`, hay que reflejarlo aquí.
"""
from __future__ import annotations

import random

DEFAULT_TOPICS: tuple[str, ...] = (
    "Quesitos de la uni.",
    "Películas.",
    "Frases que se puedan decir en la cama y en clase.",
    "Coches.",
    "Sitios para salir de fiesta.",
    "Profesores.",
    "Combate mas interesante X vs Y.",
    "Parejas X & Y.",
    "Hermanas.",
    "Famoso más payasos.",
    "Top fantasmada.",
    "Bebidas.",
)


def sample_topics(
    pool: list[str], count: int, exclude: set[str], rng: random.Random | None = None
) -> list[str]:
    """Saca `count` temas distintos del fondo de la sala más los predeterminados."""
    rng = rng or random
    seen = {t.casefold() for t in exclude}

    def fresh(items) -> list[str]:
        out: list[str] = []
        for topic in items:
            key = topic.casefold()
            if key not in seen:
                seen.add(key)
                out.append(topic)
        return out

    room = fresh(pool)
    base = fresh(DEFAULT_TOPICS)
    rng.shuffle(room)
    rng.shuffle(base)

    # Los temas que la sala ha ganado alguna vez ocupan hasta la mitad de los
    # huecos; el resto sale del fondo predeterminado.
    take = min(len(room), max(1, count // 2))
    picked = room[:take] + base[: count - take]
    if len(picked) < count:
        picked += room[take:][: count - len(picked)]
    rng.shuffle(picked)
    return picked[:count]
