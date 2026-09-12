"""Vision engine with no language model: fixed geometry + OCR + colour.

The "Replicate This Battle Team?" screen is always drawn the same way, so rather
than asking a model to interpret the image, this locates the six cards by colour,
crops each piece of data at its known position and runs classic OCR over it.
Anything that is not text is not read with OCR: gender and the nature arrows are
decided by looking at pixels.

The advantage over a VLM: it is deterministic, it cannot invent a value, and it
runs on a modest CPU. The mistakes it makes are reading mistakes, and those are
caught by Showdown's closed vocabulary and the two checksums in `app/paste.py`.
"""

from __future__ import annotations

import functools
import io
import re

import numpy as np
from PIL import Image

from ..schema import RawMon, RawStats, RawTeam

# --- Geometry, as fractions of each card's box -----------------------------
# Measured on a real 1998x922 screenshot; expressed as fractions of the detected
# card, they hold for any resolution.

# The left edges start after the item icon and the move-type icon: if an icon
# creeps into the crop, OCR reads it as a letter.
SPECIES = (0.10, 0.00, 0.42, 0.30)
ABILITY = (0.10, 0.28, 0.55, 0.48)
ITEM    = (0.118, 0.52, 0.55, 0.73)
GENDER  = (0.417, 0.05, 0.452, 0.21)
MOVES_X = (0.655, 0.99)
MOVE_Y  = (0.115, 0.355, 0.590, 0.830)
MOVE_H  = 0.085

# Stats tab: three rows, two columns.
STAT_ROW_Y = (0.358, 0.588, 0.818)
STAT_ROW_H = 0.095

# The numbers need no fixed positions: every row carries a bar that is located
# by colour and serves as the reference. The large number sits to its left and
# the small one to its right, always the same distance away measured in bar
# widths. 0.0 is where the bar starts and 1.0 where it ends, so the small number
# lives beyond 1.0.
BIG_SPAN   = (-1.60, 0.0)
SMALL_SPAN = (1.00, 2.00)
NAME_SPAN  = (-4.9, -1.70)

MAX_SP_PER_STAT = 32
MIN_BAR_WIDTH = 12
# How far the bar-length estimate may stray from the real value: measured over
# the fixture, the maximum error is 2 points.
BAR_TOLERANCE = 2
BAR_GAP = 4
# On screen: left column HP/Attack/Defense, right column Sp.Atk/Sp.Def/Speed.
GRID = (("hp", "sp_atk"), ("atk", "sp_def"), ("defense", "speed"))

# A lone digit scores around 0.5, right at RapidOCR's default cut-off, so the
# threshold is lowered and the closed vocabulary does the filtering instead.
TEXT_SCORE = 0.05
MIN_SCORE = 0.30
UPSCALE = 5
# The detector needs headroom above and below to find the line, but at the sides
# any margin drags in neighbouring icons: hence the two different values.
PAD_X = 4
PAD_Y = 12
TIGHT_MARGIN = 6


@functools.lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    # This engine drives the detector and the recogniser separately so it can
    # narrow down first and read afterwards. RapidOCR 1.4 reorganised that API,
    # so if a piece is missing it is better to say so clearly than to blow up
    # somewhere deep inside.
    missing = [name for name in ("text_detector", "text_recognizer")
               if not hasattr(engine, name)]
    if missing:
        import rapidocr_onnxruntime
        version = getattr(rapidocr_onnxruntime, "__version__", "unknown")
        raise RuntimeError(
            f"rapidocr-onnxruntime {version} does not expose {', '.join(missing)}. "
            "Install the version pinned in requirements.txt (1.2.3)."
        )
    return engine


# --- Colour-based detection ------------------------------------------------

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
    """The six cards, in the order the game numbers them (1-6)."""
    height, width, _ = arr.shape
    mask = _card_mask(arr)

    columns = _spans(mask.sum(axis=0) > height * 0.08, int(width * 0.08))
    # The Team ID banner is purple too, but far shorter than a card, so it is
    # discarded by height.
    rows = [s for s in _spans(mask.sum(axis=1) > width * 0.10, int(height * 0.06))
            if s[1] - s[0] > height * 0.10]

    if len(columns) != 2 or len(rows) != 3:
        raise ValueError(
            f"Expected a 2x3 grid of cards and found {len(columns)}x{len(rows)}. "
            "Is this a screenshot of the 'Replicate This Battle Team?' screen?"
        )
    return [(x0, y0, x1, y1) for y0, y1 in rows for x0, x1 in columns]


def detect_tab(arr: np.ndarray) -> str:
    """Return 'moves' or 'stats' depending on which tab is highlighted green."""
    height, width, _ = arr.shape
    band = arr[int(height * 0.14):int(height * 0.20)]
    r, g, b = band[:, :, 0], band[:, :, 1], band[:, :, 2]
    green = (g > 190) & (r > 140) & (r < 235) & (b < 120)

    if not green.any():
        raise ValueError("Cannot find the highlighted tab: is the image cropped?")
    centre = np.argwhere(green)[:, 1].mean() / width
    return "moves" if centre < 0.5 else "stats"


# --- OCR: one global detection pass and batched recognition ----------------
# Calling OCR region by region costs ~230 ms per crop and there are over a
# hundred of them. The detector over the whole image takes 0.6 s once, and the
# recogniser in a batch drops to 3 ms per crop: two orders of magnitude.


def _box(card, fx0, fy0, fx1, fy1,
         pad_x: int = PAD_X, pad_y: int = PAD_Y) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = card
    w, h = x1 - x0, y1 - y0
    return (x0 + int(fx0 * w) - pad_x, y0 + int(fy0 * h) - pad_y,
            x0 + int(fx1 * w) + pad_x, y0 + int(fy1 * h) + pad_y)


def _detect(arr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Text boxes across the whole screenshot, as upright rectangles."""
    found = _engine().text_detector(np.asarray(arr, dtype=np.uint8))
    boxes = found[0] if isinstance(found, tuple) else found
    out = []
    for box in boxes if boxes is not None else []:
        pts = np.asarray(box)
        out.append((int(pts[:, 0].min()), int(pts[:, 1].min()),
                    int(pts[:, 0].max()), int(pts[:, 1].max())))
    return out


def _tighten(region, detected) -> tuple[int, int, int, int]:
    """Shrink a region down to the text boxes it contains.

    The recogniser degrades if the crop carries a lot of empty background, so it
    is trimmed to whatever the detector marked as text. If it marked nothing, the
    region is returned as-is and the recogniser gets to try anyway.
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
    """Recognise a list of crops in a single pass."""
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


# --- Reading each tab ------------------------------------------------------

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
    """Pink arrows pointing up and blue ones pointing down give the nature.

    Decided by counting pixels, with no OCR: in the band holding each stat's name
    there is no other pink or blue element.
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
            # The "up" arrow is not pure red but pink (~246,96,137), so it is
            # identified by the distance between its red and green channels.
            up = int(((r > 200) & (g < 150) & (r - g > 80) & (b < 200)).sum())
            down = int(((b > 190) & (g > 140) & (g < 215) & (r < 140)).sum())
            if up > best_up:
                boosted, best_up = key, up
            if down > best_down:
                hindered, best_down = key, down
    return boosted, hindered


def _bar_spans(arr: np.ndarray, card, row: float) -> list[tuple[int, int, float]]:
    """A row's two bars: (start, end, orange fraction).

    The bar is the only dark or saturated-orange element in the row, so it is
    isolated by colour. Using it as the reference avoids depending on all six
    cards being detected at exactly the same width: a couple of pixels of
    difference was enough for the crop to cut off the last digit.
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

    # The orange and grey halves can end up separated by a pixel of
    # antialiasing; without joining them, one bar would read as two.
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
    # The species is read here too: without it, a lone Stats screenshot would
    # yield no usable Pokemon at all.
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
                # Two independent measurements of the same value: the number that
                # was read, and how much of the bar is filled. A lone zero is what
                # OCR reads worst, and when it stays silent the bar decides: empty
                # means zero points. When they disagree by more than the bar can
                # err, OCR has dropped or invented a digit (a "17" read as "7"),
                # and the bar wins.
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


# --- Merging both tabs -----------------------------------------------------

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
            # Two screenshots of the same tab are the same screen: the second
            # adds nothing, so the first one is kept.
            by_tab.setdefault(tab, reader(image, arr, cards))

        if "moves" in by_tab and "stats" in by_tab:
            mons = [_merge(s, m, _MOVES_FIELDS)
                    for s, m in zip(by_tab["stats"], by_tab["moves"])]
        elif "moves" in by_tab:
            mons = by_tab["moves"]
        else:
            mons = by_tab["stats"]

        return RawTeam(pokemon=[m for m in mons if m.species])
