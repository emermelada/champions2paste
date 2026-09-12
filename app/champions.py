"""Pokemon Champions' stat model and its translation to Showdown.

Champions does not use classic EVs or IVs:

- Each stat takes 0 to 32 **SP**, and a Pokemon's total is always 66.
- There are no IVs: they are equivalent to 31 across the board.
- The nature is never named; it is read from the arrows beside each stat
  (pink pointing up = boosted, blue pointing down = hindered).
- Battles are at level 50.

The equivalence with Showdown (1 SP = 8 EVs, capped at 252) is verified against
the six cards in `tests/fixtures/`: all 36 on-screen values are reproduced
exactly by this formula.
"""

from __future__ import annotations

import math

from . import dex

LEVEL = 50
MAX_SP_PER_STAT = 32
MAX_SP_TOTAL = 66
EV_PER_SP = 8
MAX_EV_PER_STAT = 252
MAX_EV_TOTAL = 508      # the cap of the classic EV system

# Rows: boosted stat. Columns: hindered stat.
_NATURE_STATS = ["atk", "defense", "sp_atk", "sp_def", "speed"]
_NATURE_GRID = [
    ["Hardy",  "Lonely",  "Adamant", "Naughty", "Brave"],
    ["Bold",   "Docile",  "Impish",  "Lax",     "Relaxed"],
    ["Modest", "Mild",    "Bashful", "Rash",    "Quiet"],
    ["Calm",   "Gentle",  "Careful", "Quirky",  "Sassy"],
    ["Timid",  "Hasty",   "Jolly",   "Naive",   "Serious"],
]


def nature_from_arrows(boosted: str | None, hindered: str | None) -> str | None:
    """Turn the Stats tab arrows into a nature name.

    With no arrows the nature is neutral, and Showdown already assumes neutral
    when a paste carries no nature line, so we return None and omit it.
    """
    if boosted not in _NATURE_STATS or hindered not in _NATURE_STATS:
        return None
    name = _NATURE_GRID[_NATURE_STATS.index(boosted)][_NATURE_STATS.index(hindered)]
    return None if name in {"Hardy", "Docile", "Bashful", "Quirky", "Serious"} else name


def sp_to_evs(sp: dict[str, int]) -> dict[str, int]:
    """Translate SP into the classic EV scale (1 SP = 8 EVs, capped at 252).

    Always used to recompute stats, because the game's formula operates on that
    scale. For the paste itself it is only used in `legacy` mode.
    """
    return {key: min(value * EV_PER_SP, MAX_EV_PER_STAT) for key, value in sp.items()}


def paste_evs(sp: dict[str, int], legacy: bool = False) -> dict[str, int]:
    """The values that go on the paste's EVs line.

    Champions formats on Showdown use the game's own scale: up to 32 per stat and
    66 in total, so emitting the SP as-is is the normal case. `legacy` produces
    the old EV scale for calculators and formats that still expect 0-252.
    """
    return sp_to_evs(sp) if legacy else dict(sp)


def stat_value(base: int, ev: int, key: str, nature_mult: float) -> int:
    """A stat's final value at level 50 with perfect IVs."""
    core = (2 * base + 31 + ev // 4) * LEVEL // 100
    if key == "hp":
        return core + LEVEL + 10
    return math.floor((core + 5) * nature_mult)


def expected_stats(species: str, evs: dict[str, int],
                   boosted: str | None, hindered: str | None) -> dict[str, int] | None:
    """Recompute all six stats, or None if the species is unknown."""
    base = dex.BASE_STATS.get(species)
    if base is None:
        return None
    out = {}
    for index, key in enumerate(dex.STAT_ORDER):
        mult = 1.1 if key == boosted else 0.9 if key == hindered else 1.0
        out[key] = stat_value(base[index], evs.get(key, 0), key, mult)
    return out
