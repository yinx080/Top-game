"""Trocea el sprite sheet de Freepik/Macrovector en cartas sueltas y prepara
la textura de madera para el frontend.

Uso:  python scripts/build_assets.py
Salida: frontend/public/art/cards/*.png  y  frontend/public/art/wood.jpg
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "data/poker-cards-icons-collection/OIUGSZ0.jpg"
WOOD = ROOT / "data/wooden-texture-background-wood-material-pattern/2110.w023.n001.1301B.p1.1301.jpg"
OUT_CARDS = ROOT / "frontend/public/art/cards"
OUT_ART = ROOT / "frontend/public/art"

CARD_W, CARD_H = 300, 426          # tamaño final de cada carta
PAD = 10                           # holgura al recortar antes de ajustar al borde real
SOFT_LO, SOFT_HI = 40, 110         # rampa de alfa sobre la distancia al color de fondo

# Disposición real del sheet (fila x columna)
GRID = [
    ["KD", "KS", "KH", "KC", "AC", "7D", "7S", "7H", "7C"],
    ["QD", "QS", "QH", "QC", "AH", "6D", "6S", "6H", "6C"],
    ["JD", "JS", "JH", "JC", "AS", "5D", "5S", "5H", "5C"],
    ["10D", "10S", "10H", "10C", "AD", "4D", "4S", "4H", "4C"],
    ["9D", "9S", "9H", "9C", "joker", "3D", "3S", "3H", "3C"],
    ["8D", "8S", "8H", "8C", "back", "2D", "2S", "2H", "2C"],
]


def find_bands(flags: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start = None
    for i, on in enumerate(flags):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    if start is not None and len(flags) - start >= min_len:
        out.append((start, len(flags)))
    return out


def detect_grid(arr: np.ndarray, bg: np.ndarray) -> tuple[list, list, int, int]:
    h, w, _ = arr.shape
    mask = np.abs(arr.astype(np.int16) - bg).sum(axis=2) > 60
    top = int(h * 0.10)  # el título ocupa la franja superior
    rows = [(s + top, e + top) for s, e in find_bands(mask[top:].sum(axis=1) > w * 0.02, 50)]
    cols_per_row = [
        find_bands(mask[y0:y1].sum(axis=0) > (y1 - y0) * 0.02, 50) for y0, y1 in rows
    ]
    if len(rows) != len(GRID) or any(len(c) != len(GRID[0]) for c in cols_per_row):
        raise SystemExit(f"Rejilla inesperada: {len(rows)} filas, {[len(c) for c in cols_per_row]} columnas")

    # Normalizamos: las bandas varían unos pocos px segun el dibujo de cada carta.
    card_w = int(np.median([e - s for cols in cols_per_row for s, e in cols]))
    card_h = int(np.median([e - s for s, e in rows]))
    row_centers = [(s + e) // 2 for s, e in rows]
    col_centers = [(s + e) // 2 for s, e in cols_per_row[0]]
    return row_centers, col_centers, card_w, card_h


def card_rgba(region: np.ndarray, bg: np.ndarray) -> Image.Image:
    """Separa la carta del fondo verde recuperando su alfa real.

    Las esquinas redondeadas vienen suavizadas en el JPEG, así que en lugar de
    aplicar una máscara sintética deducimos el alfa de la distancia al color de
    fondo y deshacemos la mezcla (un simple des-matting) para que no quede
    ribete verde al componer la carta sobre el tapete.
    """
    d = np.abs(region.astype(np.float32) - bg).sum(axis=2)
    a = np.clip((d - SOFT_LO) / (SOFT_HI - SOFT_LO), 0.0, 1.0)

    ys, xs = np.nonzero(a > 0.5)
    y0, y1 = ys.min(), ys.max() + 1
    x0, x1 = xs.min(), xs.max() + 1
    region, a = region[y0:y1, x0:x1], a[y0:y1, x0:x1]

    safe = np.maximum(a, 1e-3)[..., None]
    rgb = (region.astype(np.float32) - (1.0 - safe) * bg) / safe
    rgb = np.clip(rgb, 0, 255)

    # Premultiplicamos para reescalar sin arrastrar color de los píxeles vacíos.
    pre = np.dstack([rgb * a[..., None], a[..., None] * 255]).astype(np.uint8)
    small = np.asarray(
        Image.fromarray(pre, "RGBA").resize((CARD_W, CARD_H), Image.LANCZOS)
    ).astype(np.float32)
    sa = np.maximum(small[..., 3:4] / 255.0, 1e-3)
    out = np.dstack([np.clip(small[..., :3] / sa, 0, 255), small[..., 3:4]])
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def main() -> None:
    if not SHEET.exists():
        raise SystemExit(f"No encuentro el sheet en {SHEET}")

    OUT_CARDS.mkdir(parents=True, exist_ok=True)
    sheet = Image.open(SHEET).convert("RGB")
    arr = np.asarray(sheet)

    border = np.concatenate(
        [arr[0:6].reshape(-1, 3), arr[-6:].reshape(-1, 3),
         arr[:, 0:6].reshape(-1, 3), arr[:, -6:].reshape(-1, 3)]
    )
    bg = np.array(Counter(map(tuple, border)).most_common(1)[0][0], dtype=np.int16)
    print(f"fondo del sheet: rgb{tuple(int(c) for c in bg)}")

    row_centers, col_centers, card_w, card_h = detect_grid(arr, bg)
    print(f"carta detectada: {card_w}x{card_h}")

    for r, cy in enumerate(row_centers):
        for c, cx in enumerate(col_centers):
            name = GRID[r][c]
            y0, x0 = cy - card_h // 2 - PAD, cx - card_w // 2 - PAD
            region = arr[y0:y0 + card_h + 2 * PAD, x0:x0 + card_w + 2 * PAD]
            card_rgba(region, bg).save(OUT_CARDS / f"{name}.png", optimize=True)

    print(f"{len(GRID) * len(GRID[0])} cartas escritas en {OUT_CARDS.relative_to(ROOT)}")

    if WOOD.exists():
        wood = Image.open(WOOD).convert("RGB")
        wood.thumbnail((1920, 1920), Image.LANCZOS)
        wood.save(OUT_ART / "wood.jpg", quality=82, optimize=True, progressive=True)
        print(f"madera {wood.size[0]}x{wood.size[1]} -> art/wood.jpg")
    else:
        print("aviso: no encuentro la textura de madera", file=sys.stderr)


if __name__ == "__main__":
    main()
