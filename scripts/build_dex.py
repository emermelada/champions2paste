"""Download Pokemon Showdown's canonical names and cache them in data/dex.json.

Showdown is the authority on exact spelling: if a name does not match its
canonical form, the paste will not import. This script runs during the image
build so the container never depends on the internet at run time.
"""

import json
import pathlib
import re
import sys
import urllib.request

BASE = "https://play.pokemonshowdown.com/data"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "dex.json"

# items.js and abilities.js are served as JS modules with unquoted keys, so they
# are not parseable as JSON. All we need are the display names.
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
        # Non-standard forms (CAP, unobtainable) pollute the fuzzy matching.
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

    # Base stats make it possible to recompute each stat's final value and check
    # it against the number in the screenshot: a verification that gives away any
    # reading error.
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
            print(f"ERROR: only {len(values)} entries in {key}, source is broken", file=sys.stderr)
            return 1
        print(f"{key:12} {len(values):5} entries")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dex, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
