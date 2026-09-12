"""Descarga los nombres canonicos de Pokemon Showdown y los cachea en data/dex.json.

Showdown es la autoridad sobre la ortografia exacta: si un nombre no coincide con
su forma canonica, el paste no importa. Este script se ejecuta en el build de la
imagen para que el contenedor no dependa de internet en tiempo de ejecucion.
"""

import json
import pathlib
import re
import sys
import urllib.request

BASE = "https://play.pokemonshowdown.com/data"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "dex.json"

# items.js y abilities.js se sirven como modulos JS con claves sin comillas, asi
# que no son JSON parseable. Solo necesitamos los nombres de display.
NAME_RE = re.compile(r'\bname:"((?:[^"\\]|\\.)*)"')


def fetch(path: str) -> str:
    req = urllib.request.Request(f"{BASE}/{path}", headers={"User-Agent": "champions2paste"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def names_from_json(path: str) -> list[str]:
    return [name for name, _ in entries_from_json(path)]


def entries_from_json(path: str) -> list[tuple[str, dict]]:
    data = json.loads(fetch(path))
    out = []
    for key, entry in data.items():
        if not isinstance(entry, dict):
            continue
        # Las formas no estandar (CAP, no obtenibles) ensucian el fuzzy matching.
        if entry.get("isNonstandard") in {"CAP", "Custom"}:
            continue
        name = entry.get("name")
        if name:
            out.append((name, entry))
    return out


def names_from_js(path: str) -> list[str]:
    return NAME_RE.findall(fetch(path))


def main() -> int:
    pokedex = entries_from_json("pokedex.json")

    # Las estadisticas base permiten recalcular el valor final de cada stat y
    # contrastarlo con el numero que muestra la captura: una verificacion que
    # delata cualquier error de lectura.
    base_stats = {
        name: [entry["baseStats"][k] for k in ("hp", "atk", "def", "spa", "spd", "spe")]
        for name, entry in pokedex
        if isinstance(entry.get("baseStats"), dict)
    }

    dex = {
        "species": sorted({name for name, _ in pokedex}),
        "moves": sorted(set(names_from_json("moves.json"))),
        "items": sorted(set(names_from_js("items.js"))),
        "abilities": sorted(set(names_from_js("abilities.js"))),
    }

    dex["base_stats"] = base_stats

    for key, values in dex.items():
        if len(values) < 50:
            print(f"ERROR: solo {len(values)} entradas en {key}, fuente rota", file=sys.stderr)
            return 1
        print(f"{key:12} {len(values):5} entradas")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dex, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"escrito {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
