"""El modelo de estadisticas de Pokemon Champions y su traduccion a Showdown.

Champions no usa EVs ni IVs al estilo clasico:

- Cada estadistica admite de 0 a 32 **SP**, y el total del Pokemon es siempre 66.
- No hay IVs: equivalen a 31 en todas.
- La naturaleza no se nombra; se lee de las flechas junto a cada estadistica
  (rojas hacia arriba = potenciada, azules hacia abajo = reducida).
- Los combates son a nivel 50.

La equivalencia con Showdown (1 SP = 8 EVs, tope de 252) esta verificada contra
las seis tarjetas de `tests/fixtures/`: los 36 valores mostrados en pantalla se
reproducen exactamente con esta formula.
"""

from __future__ import annotations

import math

from . import dex

LEVEL = 50
MAX_SP_PER_STAT = 32
MAX_SP_TOTAL = 66
EV_PER_SP = 8
MAX_EV_PER_STAT = 252
MAX_EV_TOTAL = 508      # el tope del sistema clasico de EVs

# Filas: estadistica potenciada. Columnas: estadistica reducida.
_NATURE_STATS = ["atk", "defense", "sp_atk", "sp_def", "speed"]
_NATURE_GRID = [
    ["Hardy",  "Lonely",  "Adamant", "Naughty", "Brave"],
    ["Bold",   "Docile",  "Impish",  "Lax",     "Relaxed"],
    ["Modest", "Mild",    "Bashful", "Rash",    "Quiet"],
    ["Calm",   "Gentle",  "Careful", "Quirky",  "Sassy"],
    ["Timid",  "Hasty",   "Jolly",   "Naive",   "Serious"],
]


def nature_from_arrows(boosted: str | None, hindered: str | None) -> str | None:
    """Traduce las flechas de la pestana Stats al nombre de la naturaleza.

    Sin flechas la naturaleza es neutra: Showdown ya asume neutra cuando el paste
    no lleva linea de naturaleza, asi que devolvemos None y se omite.
    """
    if boosted not in _NATURE_STATS or hindered not in _NATURE_STATS:
        return None
    name = _NATURE_GRID[_NATURE_STATS.index(boosted)][_NATURE_STATS.index(hindered)]
    return None if name in {"Hardy", "Docile", "Bashful", "Quirky", "Serious"} else name


def sp_to_evs(sp: dict[str, int]) -> dict[str, int]:
    """Traduce SP a la escala clasica de EVs (1 SP = 8 EVs, tope 252).

    Se usa siempre para recalcular las estadisticas, porque la formula del juego
    opera en esa escala. Para el paste solo se emplea en modo `legacy`.
    """
    return {key: min(value * EV_PER_SP, MAX_EV_PER_STAT) for key, value in sp.items()}


def paste_evs(sp: dict[str, int], legacy: bool = False) -> dict[str, int]:
    """Los valores que van en la linea EVs del paste.

    Los formatos de Champions en Showdown usan la propia escala del juego: hasta
    32 por estadistica y 66 en total. Por eso lo normal es emitir los SP tal
    cual. `legacy` produce la escala antigua de EVs para calculadoras y formatos
    que todavia esperan 0-252.
    """
    return sp_to_evs(sp) if legacy else dict(sp)


def stat_value(base: int, ev: int, key: str, nature_mult: float) -> int:
    """Valor final de una estadistica a nivel 50 con IVs perfectos."""
    core = (2 * base + 31 + ev // 4) * LEVEL // 100
    if key == "hp":
        return core + LEVEL + 10
    return math.floor((core + 5) * nature_mult)


def expected_stats(species: str, evs: dict[str, int],
                   boosted: str | None, hindered: str | None) -> dict[str, int] | None:
    """Recalcula las seis estadisticas, o None si no conocemos la especie."""
    base = dex.BASE_STATS.get(species)
    if base is None:
        return None
    out = {}
    for index, key in enumerate(dex.STAT_ORDER):
        mult = 1.1 if key == boosted else 0.9 if key == hindered else 1.0
        out[key] = stat_value(base[index], evs.get(key, 0), key, mult)
    return out
