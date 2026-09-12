"""Name normalisation against Showdown's closed vocabulary.

This is the piece that makes the paste *valid* rather than merely plausible. OCR
reading a screenshot returns approximate text ("Rillabom", "Assault Vest " with a
trailing space, "Landorus-T"); Showdown rejects anything that is not the exact
spelling. Here every extracted string is anchored to the nearest canonical name,
or flagged as doubtful so the user can review it.
"""

from __future__ import annotations

import difflib
import json
import pathlib
import re
from dataclasses import dataclass

DEX_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "dex.json"

NATURES = [
    "Adamant", "Bashful", "Bold", "Brave", "Calm", "Careful", "Docile", "Gentle",
    "Hardy", "Hasty", "Impish", "Jolly", "Lax", "Lonely", "Mild", "Modest",
    "Naive", "Naughty", "Quiet", "Quirky", "Rash", "Relaxed", "Sassy", "Serious", "Timid",
]

TERA_TYPES = [
    "Bug", "Dark", "Dragon", "Electric", "Fairy", "Fighting", "Fire", "Flying",
    "Ghost", "Grass", "Ground", "Ice", "Normal", "Poison", "Psychic", "Rock",
    "Steel", "Stellar", "Water",
]

# The order Showdown expects stats in on the EVs / IVs lines.
STAT_ORDER = ["hp", "atk", "defense", "sp_atk", "sp_def", "speed"]
STAT_LABELS = {
    "hp": "HP", "atk": "Atk", "defense": "Def",
    "sp_atk": "SpA", "sp_def": "SpD", "speed": "Spe",
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def to_id(value: str) -> str:
    """Showdown's `toID`: lowercase, stripped of everything non-alphanumeric."""
    return _NON_ALNUM.sub("", value.lower())


@dataclass(frozen=True)
class Match:
    """The result of anchoring a read string to the canonical vocabulary."""

    value: str | None          # canonical name, or None if nothing came close
    raw: str                   # what the vision engine returned
    exact: bool                # True if it matched without needing fuzzy search

    @property
    def uncertain(self) -> bool:
        return self.value is None or not self.exact


class Vocabulary:
    """A closed set of valid names with typo-tolerant lookup."""

    def __init__(self, names: list[str]) -> None:
        self.names = names
        self._by_id = {to_id(n): n for n in names}
        self._ids = list(self._by_id)

    def match(self, raw: str | None) -> Match:
        if not raw or not raw.strip():
            return Match(None, raw or "", False)

        raw = raw.strip()
        key = to_id(raw)
        if key in self._by_id:
            return Match(self._by_id[key], raw, True)

        # The threshold scales with length: a one-character typo weighs far more
        # in "watar" (0.80 similar to "water") than in a long name, while
        # loosening the bar on 3-4 letter strings would make "Ice" match half a
        # dozen different moves.
        length = len(key)
        if length <= 4:
            cutoff = 0.85
        elif length <= 8:
            cutoff = 0.78
        else:
            cutoff = 0.72
        near = difflib.get_close_matches(key, self._ids, n=1, cutoff=cutoff)
        if near:
            return Match(self._by_id[near[0]], raw, False)

        return Match(None, raw, False)


def _load() -> dict[str, Vocabulary]:
    if not DEX_PATH.exists():
        raise RuntimeError(
            f"{DEX_PATH} is missing. Run `python scripts/build_dex.py` to generate it."
        )
    data = json.loads(DEX_PATH.read_text(encoding="utf-8"))
    global BASE_STATS
    BASE_STATS = data.pop("base_stats", {})
    vocab = {key: Vocabulary(values) for key, values in data.items()}
    vocab["natures"] = Vocabulary(NATURES)
    vocab["tera"] = Vocabulary(TERA_TYPES)
    return vocab


BASE_STATS: dict[str, list[int]] = {}   # species -> [HP, Atk, Def, SpA, SpD, Spe]

VOCAB = _load()

species = VOCAB["species"]
moves = VOCAB["moves"]
items = VOCAB["items"]
abilities = VOCAB["abilities"]
natures = VOCAB["natures"]
tera = VOCAB["tera"]
