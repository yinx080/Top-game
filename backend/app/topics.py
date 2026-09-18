"""Temas predeterminados para el top de cada ronda.

Cada tema es una escala: la carta baja es el extremo izquierdo y la alta el
derecho, así que la redacción siempre dice hacia dónde crece.
"""
from __future__ import annotations

import random

DEFAULT_TOPICS: tuple[str, ...] = (
    "Animales, del más pequeño al más grande",
    "Animales, del menos al más peligroso",
    "Comidas, de menos a más picante",
    "Comidas, de menos a más sana",
    "Postres, de menos a más empalagoso",
    "Bebidas, de menos a más refrescante",
    "Cosas, de menos a más caras",
    "Trabajos, de menos a más estresantes",
    "Trabajos, de peor a mejor pagados",
    "Superpoderes, de menos a más útiles",
    "Miedos, del menos al más común",
    "Planes de sábado, de peor a mejor",
    "Inventos, de menos a más importantes",
    "Deportes, de menos a más duros",
    "Películas, de peor a mejor final",
    "Canciones, de menos a más pegadizas",
    "Videojuegos, de menos a más difíciles",
    "Excusas, de menos a más creíbles",
    "Ciudades, de menos a más turísticas",
    "Países, del más pequeño al más grande",
    "Idiomas, de menos a más difíciles de aprender",
    "Asignaturas, de menos a más aburridas",
    "Series, de menos a más largas",
    "Animales marinos, del menos al más profundo",
    "Objetos de casa, de menos a más usados",
    "Aplicaciones del móvil, de menos a más adictivas",
    "Dolores, de menos a más insoportables",
    "Sonidos, de menos a más molestos",
    "Olores, de peor a mejor",
    "Colores, de menos a más llamativos",
    "Frutas, de menos a más dulces",
    "Medios de transporte, de menos a más rápidos",
    "Tareas de casa, de menos a más odiadas",
    "Regalos, de peor a mejor recibido",
    "Mascotas, de menos a más fáciles de cuidar",
    "Criaturas mitológicas, de menos a más temibles",
    "Épocas de la historia, de la más antigua a la más reciente",
    "Cosas frágiles, de menos a más rompibles",
    "Momentos del día, de peor a mejor",
    "Palabras, de la más corta a la más larga",
    "Materiales, de menos a más duros",
    "Redes sociales, de menos a más tóxicas",
    "Herramientas, de menos a más peligrosas",
    "Planetas, del más cercano al más lejano del Sol",
    "Situaciones, de menos a más vergonzosas",
    "Villanos de ficción, de menos a más malvados",
    "Alturas, de la más baja a la más alta",
    "Temperaturas, de la más fría a la más caliente",
    "Meses del año, de peor a mejor",
    "Personajes históricos, del más antiguo al más reciente",
    "Bebidas, de menos a más cafeína",
    "Plantas, de menos a más fáciles de mantener vivas",
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
