"""Normalizacion de nombres contra el vocabulario cerrado de Showdown.

Esta es la pieza que hace que el paste sea *valido* y no solo plausible. Un
modelo de vision leyendo una captura devuelve texto aproximado ("Rillabom",
"Assault Vest " con espacio, "Landorus-T"); Showdown rechaza cualquier cosa que
no sea la ortografia exacta. Aqui cada cadena extraida se ancla al nombre
canonico mas cercano, o se marca como dudosa para que el usuario la revise.
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

# Orden en que Showdown espera las estadisticas en las lineas EVs / IVs.
STAT_ORDER = ["hp", "atk", "defense", "sp_atk", "sp_def", "speed"]
STAT_LABELS = {
    "hp": "HP", "atk": "Atk", "defense": "Def",
    "sp_atk": "SpA", "sp_def": "SpD", "speed": "Spe",
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def to_id(value: str) -> str:
    """Equivalente al `toID` de Showdown: minusculas sin nada que no sea alfanumerico."""
    return _NON_ALNUM.sub("", value.lower())


@dataclass(frozen=True)
class Match:
    """Resultado de anclar una cadena leida al vocabulario canonico."""

    value: str | None          # nombre canonico, o None si no hubo candidato
    raw: str                   # lo que devolvio el modelo de vision
    exact: bool                # True si coincidio sin necesidad de fuzzy

    @property
    def uncertain(self) -> bool:
        return self.value is None or not self.exact


class Vocabulary:
    """Un conjunto cerrado de nombres validos con busqueda tolerante a erratas."""

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

        # El umbral escala con la longitud: una errata de un caracter pesa mucho
        # mas en "watar" (0.80 de parecido con "water") que en un nombre largo,
        # mientras que aflojar el listen en cadenas de 3-4 letras haria que "Ice"
        # casara con media docena de movimientos distintos.
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
            f"Falta {DEX_PATH}. Ejecuta `python scripts/build_dex.py` para generarlo."
        )
    data = json.loads(DEX_PATH.read_text(encoding="utf-8"))
    global BASE_STATS
    BASE_STATS = data.pop("base_stats", {})
    vocab = {key: Vocabulary(values) for key, values in data.items()}
    vocab["natures"] = Vocabulary(NATURES)
    vocab["tera"] = Vocabulary(TERA_TYPES)
    return vocab


BASE_STATS: dict[str, list[int]] = {}   # especie -> [HP, Atk, Def, SpA, SpD, Spe]

VOCAB = _load()

species = VOCAB["species"]
moves = VOCAB["moves"]
items = VOCAB["items"]
abilities = VOCAB["abilities"]
natures = VOCAB["natures"]
tera = VOCAB["tera"]
