"""Motor de vision sin modelo de lenguaje: geometria fija + OCR + color.

La pantalla "Replicate This Battle Team?" siempre se dibuja igual, asi que en vez
de pedirle a un modelo que interprete la imagen, aqui se localizan las seis
tarjetas por color, se recorta cada dato en su posicion conocida y se pasa por un
OCR clasico. Lo que no es texto no se lee con OCR: el genero y las flechas de la
naturaleza se deciden mirando pixeles.

Ventaja sobre un VLM: es determinista, no puede inventarse un dato, y corre en
una CPU modesta. Los errores que comete son de lectura, y los cazan el
diccionario cerrado de Showdown y los dos checksums de `app/paste.py`.
"""

from __future__ import annotations

import functools
import io
import re

import numpy as np
from PIL import Image

from ..schema import RawMon, RawStats, RawTeam

# --- Geometria, en fracciones de la caja de cada tarjeta -------------------
# Medidas sobre una captura real de 1998x922; al expresarlas como fracciones de
# la tarjeta detectada, valen para cualquier resolucion.

# Los bordes izquierdos empiezan despues del icono de objeto y del de tipo de
# movimiento: si el icono entra en el recorte, el OCR lo lee como una letra.
SPECIES = (0.10, 0.00, 0.42, 0.30)
ABILITY = (0.10, 0.28, 0.55, 0.48)
ITEM    = (0.118, 0.52, 0.55, 0.73)
GENDER  = (0.417, 0.05, 0.452, 0.21)
MOVES_X = (0.655, 0.99)
MOVE_Y  = (0.115, 0.355, 0.590, 0.830)
MOVE_H  = 0.085

# Pestana Stats: tres filas, dos columnas. La segunda columna es la primera
# desplazada; el desplazamiento sale de la separacion entre ambas barras.
STAT_ROW_Y = (0.358, 0.588, 0.818)
STAT_ROW_H = 0.095
COL_OFFSET = 0.4615
# En la pestana Stats no hacen falta posiciones fijas para los numeros: cada
# fila lleva una barra que se localiza por color y sirve de referencia. El
# numero grande queda a su izquierda y el pequeno a su derecha, siempre a la
# misma distancia medida en anchos de barra.
# Medidos en anchos de barra desde su inicio: 0.0 es donde empieza la barra y
# 1.0 donde termina, asi que el numero pequeno vive por encima de 1.0.
BIG_SPAN   = (-1.60, 0.0)
SMALL_SPAN = (1.00, 2.00)
NAME_SPAN  = (-4.9, -1.70)

MAX_SP_PER_STAT = 32
MIN_BAR_WIDTH = 12
# Margen con el que la estimacion por longitud de barra puede desviarse del
# valor real: medido sobre el fixture, el error maximo es de 2 puntos.
BAR_TOLERANCE = 2
BAR_GAP = 4
# En pantalla: columna izquierda HP/Attack/Defense, derecha Sp.Atk/Sp.Def/Speed.
GRID = (("hp", "sp_atk"), ("atk", "sp_def"), ("defense", "speed"))

# Un digito suelto puntua alrededor de 0.5, justo en el corte por defecto de
# RapidOCR, asi que se baja el umbral y se deja filtrar al diccionario cerrado.
TEXT_SCORE = 0.05
MIN_SCORE = 0.30
UPSCALE = 5
# El detector necesita aire por arriba y por abajo para encontrar la linea, pero
# a los lados el margen acerca los iconos vecinos: por eso son distintos.
PAD_X = 4
PAD_Y = 12
TIGHT_MARGIN = 6


@functools.lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    # Este motor usa el detector y el reconocedor por separado para poder
    # acotar primero y leer despues. RapidOCR 1.4 reorganizo esa API, asi que
    # si falta alguna pieza conviene decirlo claro en vez de reventar dentro.
    missing = [name for name in ("text_detector", "text_recognizer")
               if not hasattr(engine, name)]
    if missing:
        import rapidocr_onnxruntime
        version = getattr(rapidocr_onnxruntime, "__version__", "desconocida")
        raise RuntimeError(
            f"rapidocr-onnxruntime {version} no expone {', '.join(missing)}. "
            "Instala la version fijada en requirements.txt (1.2.3)."
        )
    return engine


# --- Deteccion por color ---------------------------------------------------

def _card_mask(arr: np.ndarray) -> np.ndarray:
    r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    return (b > r + 20) & (b > 120) & (r < 200)


def _spans(flags: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    out, start = [], None
    for i, value in enumerate(list(flags) + [False]):
        if value and start is None:
            start = i
        elif not value and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    return out


def detect_cards(arr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Las seis tarjetas, en el orden en que las numera el juego (1-6)."""
    height, width, _ = arr.shape
    mask = _card_mask(arr)

    columns = _spans(mask.sum(axis=0) > height * 0.08, int(width * 0.08))
    # La barra del Team ID tambien es morada pero es mucho mas baja que una
    # tarjeta, asi que se descarta por altura.
    rows = [s for s in _spans(mask.sum(axis=1) > width * 0.10, int(height * 0.06))
            if s[1] - s[0] > height * 0.10]

    if len(columns) != 2 or len(rows) != 3:
        raise ValueError(
            f"Esperaba una rejilla de 2x3 tarjetas y encontre {len(columns)}x{len(rows)}. "
            "¿Es una captura de la pantalla 'Replicate This Battle Team?'"
        )
    return [(x0, y0, x1, y1) for y0, y1 in rows for x0, x1 in columns]


def detect_tab(arr: np.ndarray) -> str:
    """Devuelve 'moves' o 'stats' segun que pestana este resaltada en verde."""
    height, width, _ = arr.shape
    band = arr[int(height * 0.14):int(height * 0.20)]
    r, g, b = band[:, :, 0], band[:, :, 1], band[:, :, 2]
    green = (g > 190) & (r > 140) & (r < 235) & (b < 120)

    if not green.any():
        raise ValueError("No encuentro la pestana resaltada: ¿esta recortada la imagen?")
    centre = np.argwhere(green)[:, 1].mean() / width
    return "moves" if centre < 0.5 else "stats"


# --- OCR: una deteccion global y reconocimiento en lote -------------------
# Llamar al OCR region por region cuesta ~230 ms por recorte y hay mas de cien.
# El detector sobre la imagen completa tarda 0.6 s una sola vez, y el
# reconocedor en lote baja a 3 ms por recorte: dos ordenes de magnitud.


def _box(card, fx0, fy0, fx1, fy1,
         pad_x: int = PAD_X, pad_y: int = PAD_Y) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = card
    w, h = x1 - x0, y1 - y0
    return (x0 + int(fx0 * w) - pad_x, y0 + int(fy0 * h) - pad_y,
            x0 + int(fx1 * w) + pad_x, y0 + int(fy1 * h) + pad_y)


def _detect(arr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Cajas de texto de toda la captura, como rectangulos rectos."""
    found = _engine().text_detector(np.asarray(arr, dtype=np.uint8))
    boxes = found[0] if isinstance(found, tuple) else found
    out = []
    for box in boxes if boxes is not None else []:
        pts = np.asarray(box)
        out.append((int(pts[:, 0].min()), int(pts[:, 1].min()),
                    int(pts[:, 0].max()), int(pts[:, 1].max())))
    return out


def _tighten(region, detected) -> tuple[int, int, int, int]:
    """Ajusta una region a las cajas de texto que contiene.

    El reconocedor se degrada si el recorte lleva mucho fondo vacio, asi que se
    recorta a lo que el detector marco como texto. Si no marco nada, se devuelve
    la region tal cual y que el reconocedor lo intente.
    """
    rx0, ry0, rx1, ry1 = region
    inside = [b for b in detected
              if rx0 <= (b[0] + b[2]) / 2 <= rx1 and ry0 <= (b[1] + b[3]) / 2 <= ry1]
    if not inside:
        return region
    return (max(rx0, min(b[0] for b in inside) - TIGHT_MARGIN),
            max(ry0, min(b[1] for b in inside) - TIGHT_MARGIN),
            min(rx1, max(b[2] for b in inside) + TIGHT_MARGIN),
            min(ry1, max(b[3] for b in inside) + TIGHT_MARGIN))


def _recognise(image: Image.Image, boxes: list) -> list[str]:
    """Reconoce una lista de recortes de una sola pasada."""
    crops, index = [], []
    for i, box in enumerate(boxes):
        if box is None:
            continue
        crop = image.crop(box)
        if crop.width < 4 or crop.height < 4:
            continue
        crops.append(np.asarray(
            crop.resize((crop.width * UPSCALE, crop.height * UPSCALE), Image.LANCZOS)))
        index.append(i)

    texts = [""] * len(boxes)
    if not crops:
        return texts

    out = _engine().text_recognizer(crops)
    rows = out[0] if isinstance(out, tuple) else out
    for i, row in zip(index, rows):
        if row and row[0] and float(row[1]) >= MIN_SCORE:
            texts[i] = " ".join(str(row[0]).split())
    return texts


def _as_int(text: str) -> int | None:
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


# --- Lectura de cada pestana ----------------------------------------------

def _gender(arr: np.ndarray, card) -> str | None:
    x0, y0, x1, y1 = _box(card, *GENDER, pad_x=0, pad_y=0)
    patch = arr[max(y0, 0):y1, max(x0, 0):x1]
    if patch.size == 0:
        return None
    r, g, b = patch[:, :, 0], patch[:, :, 1], patch[:, :, 2]
    female = int(((r > 170) & (g < 90) & (b < 90)).sum())
    male = int(((b > 170) & (r < 120) & (g < 160)).sum())
    if max(female, male) < 12:
        return None
    return "F" if female > male else "M"


def _arrows(arr: np.ndarray, card, rows_bars) -> tuple[str | None, str | None]:
    """Las flechas rosas hacia arriba y azules hacia abajo dan la naturaleza.

    Se deciden contando pixeles, sin OCR: en la banda del nombre de cada
    estadistica no hay ningun otro elemento rosa ni azul.
    """
    boosted = hindered = None
    best_up = best_down = 12
    for (row, keys), bars in zip(zip(STAT_ROW_Y, GRID), rows_bars):
        _, y0, _, y1 = _box(card, 0.0, row - STAT_ROW_H, 1.0, row + STAT_ROW_H,
                            pad_x=0, pad_y=0)
        for bar, key in zip(bars, keys):
            x0, _, x1, _ = _span_box(bar, NAME_SPAN, y0, y1)
            patch = arr[max(y0, 0):y1, max(x0, 0):max(x1, 0)]
            if patch.size == 0:
                continue
            r, g, b = patch[:, :, 0], patch[:, :, 1], patch[:, :, 2]
            # La flecha "hacia arriba" no es roja pura sino rosa (~246,96,137),
            # asi que se identifica por la distancia entre rojo y verde.
            up = int(((r > 200) & (g < 150) & (r - g > 80) & (b < 200)).sum())
            down = int(((b > 190) & (g > 140) & (g < 215) & (r < 140)).sum())
            if up > best_up:
                boosted, best_up = key, up
            if down > best_down:
                hindered, best_down = key, down
    return boosted, hindered


def _bar_spans(arr: np.ndarray, card, row: float) -> list[tuple[int, int, float]]:
    """Las dos barras de una fila: (inicio, fin, fraccion naranja).

    La barra es el unico elemento oscuro o naranja saturado de la fila, asi que
    se aisla por color. Usarla como referencia evita depender de que las seis
    tarjetas se detecten con exactamente el mismo ancho: un par de pixeles de
    diferencia bastaban para que el recorte cortase el ultimo digito.
    """
    x0, y0, x1, y1 = _box(card, 0.0, row - STAT_ROW_H, 1.0, row + STAT_ROW_H,
                          pad_x=0, pad_y=0)
    patch = arr[max(y0, 0):y1, max(x0, 0):x1]
    if patch.size == 0:
        return []

    r, g, b = patch[:, :, 0], patch[:, :, 1], patch[:, :, 2]
    orange = (r > 165) & (g > 70) & (g < 185) & (b < 135) & (r - b > 70)
    grey = (r < 115) & (g < 120) & (b < 165) & (b > r)
    bar = orange | grey

    # La parte naranja y la gris pueden quedar separadas por un pixel de
    # antialiasing; sin unirlas, una barra se leeria como dos.
    merged: list[list[int]] = []
    for start, end in _spans(bar.any(axis=0), 3):
        if merged and start - merged[-1][1] <= BAR_GAP:
            merged[-1][1] = end
        else:
            merged.append([start, end])

    out = []
    for start, end in merged:
        if end - start < MIN_BAR_WIDTH:
            continue
        column = orange[:, start:end].any(axis=0)
        filled = (float(np.argwhere(column).max() + 1) / (end - start)
                  if column.any() else 0.0)
        out.append((x0 + start, x0 + end, filled))
    return out


def _span_box(bar: tuple[int, int, float], span: tuple[float, float],
              y0: int, y1: int) -> tuple[int, int, int, int]:
    bx0, bx1, _ = bar
    width = bx1 - bx0
    return (int(bx0 + span[0] * width), y0, int(bx0 + span[1] * width), y1)


def read_moves_tab(image: Image.Image, arr: np.ndarray, cards) -> list[RawMon]:
    detected = _detect(arr)
    regions = []
    for card in cards:
        regions.append(_tighten(_box(card, *SPECIES), detected))
        regions.append(_tighten(_box(card, *ABILITY), detected))
        regions.append(_tighten(_box(card, *ITEM), detected))
        for y in MOVE_Y:
            regions.append(_tighten(
                _box(card, MOVES_X[0], y - MOVE_H, MOVES_X[1], y + MOVE_H), detected))

    texts = _recognise(image, regions)
    mons = []
    for i, card in enumerate(cards):
        species, ability, item, *moves = texts[i * 7:(i + 1) * 7]
        mons.append(RawMon(
            species=species,
            ability=ability or None,
            item=item or None,
            gender=_gender(arr, card),
            moves=[m for m in moves if m],
        ))
    return mons


def read_stats_tab(image: Image.Image, arr: np.ndarray, cards) -> list[RawMon]:
    # La especie tambien se lee aqui: sin ella una captura suelta de Stats no
    # daria ningun Pokemon utilizable.
    detected = _detect(arr)
    species = _recognise(image, [_tighten(_box(card, *SPECIES), detected)
                                 for card in cards])

    boxes, plan = [], []
    for card in cards:
        rows_bars = [_bar_spans(arr, card, row) for row in STAT_ROW_Y]
        for (row, keys), bars in zip(zip(STAT_ROW_Y, GRID), rows_bars):
            _, y0, _, y1 = _box(card, 0.0, row - STAT_ROW_H, 1.0, row + STAT_ROW_H,
                                pad_x=0, pad_y=PAD_Y)
            for index, key in enumerate(keys):
                bar = bars[index] if index < len(bars) else None
                if bar is None:
                    boxes += [None, None]
                    plan.append((key, None))
                    continue
                boxes.append(_span_box(bar, BIG_SPAN, y0, y1))
                boxes.append(_span_box(bar, SMALL_SPAN, y0, y1))
                plan.append((key, bar[2]))
        plan.append(("__arrows__", rows_bars))

    texts = _recognise(image, boxes)
    mons, cursor, slot = [], 0, 0
    for index, card in enumerate(cards):
        sp, stats = {}, {}
        for _ in range(6):
            key, fill = plan[cursor]
            cursor += 1
            stats[key] = _as_int(texts[slot])
            if fill is None:
                sp[key] = None
            else:
                # Un cero suelto es lo que peor lee el OCR. Cuando calla, manda
                # la barra: vacia son cero puntos, y si tiene naranja su
                # longitud da una estimacion que el checksum de 66 contrastara.
                # Dos medidas independientes del mismo dato: el numero leido y
                # la longitud rellena de la barra. Si discrepan mas de lo que la
                # barra puede errar, el OCR ha perdido o inventado un digito
                # (un "17" leido como "7"), y manda la barra.
                estimate = round(fill * MAX_SP_PER_STAT)
                value = _as_int(texts[slot + 1])
                sp[key] = (estimate if value is None
                           or abs(value - estimate) > BAR_TOLERANCE else value)
            slot += 2

        rows_bars = plan[cursor][1]
        cursor += 1
        boosted, hindered = _arrows(arr, card, rows_bars)
        mons.append(RawMon(species=species[index], sp=RawStats(**sp),
                           stats=RawStats(**stats),
                           boosted_stat=boosted, hindered_stat=hindered))
    return mons


# --- Fusion de ambas pestanas ---------------------------------------------

_STATS_FIELDS = ("sp", "stats", "boosted_stat", "hindered_stat")
_MOVES_FIELDS = ("ability", "item", "gender", "moves")


def _merge(base: RawMon, other: RawMon, fields) -> RawMon:
    data = base.model_dump()
    for name in fields:
        data[name] = getattr(other, name)
    if not data.get("species"):
        data["species"] = other.species
    return RawMon.model_validate(data)


class OcrBackend:
    name = "ocr"

    def extract(self, images: list[tuple[str, bytes]]) -> RawTeam:
        by_tab: dict[str, list[RawMon]] = {}

        for _, data in images:
            image = Image.open(io.BytesIO(data)).convert("RGB")
            arr = np.asarray(image).astype(int)
            tab = detect_tab(arr)
            cards = detect_cards(arr)
            reader = read_moves_tab if tab == "moves" else read_stats_tab
            # Dos capturas de la misma pestana son la misma pantalla: la segunda
            # no anade nada, asi que se conserva la primera.
            by_tab.setdefault(tab, reader(image, arr, cards))

        if "moves" in by_tab and "stats" in by_tab:
            mons = [_merge(s, m, _MOVES_FIELDS)
                    for s, m in zip(by_tab["stats"], by_tab["moves"])]
        elif "moves" in by_tab:
            mons = by_tab["moves"]
        else:
            mons = by_tab["stats"]

        return RawTeam(pokemon=[m for m in mons if m.species])
