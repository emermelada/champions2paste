"""Pruebas de la tuberia de normalizacion y renderizado.

Sin dependencias externas: `python tests/test_pipeline.py`.
El fixture es una captura real de Pokemon Champions (Regulation M-C).
"""

from __future__ import annotations

import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import champions, dex, paste
from app.schema import RawTeam

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def test_real_team() -> None:
    """El equipo de las dos capturas reales debe salir sin una sola correccion."""
    data = json.loads((FIXTURES / "team.expected.json").read_text())
    team = RawTeam.model_validate(data["team"])
    mons = paste.normalize_team(team)
    text = paste.render_team(mons, data["level"])

    check(len(mons) == 6, f"esperados 6 Pokemon, hay {len(mons)}")

    warnings = [w for mon in mons for w in mon["warnings"]]
    check(not warnings, f"las capturas reales no deberian generar avisos: {warnings}")

    # El equipo lleva una piedra mega: Champions permite megaevolucion y la
    # habilidad del paste debe ser la de la forma base, no la de la mega.
    check("Salamence (F) @ Salamencite" in text, "falta la linea de Salamence con su piedra")
    check("Ability: Intimidate" in text, "Salamence debe conservar Intimidate, no Aerilate")

    check(text.count("Level: 50") == 6, "los seis deben llevar nivel 50")
    check("IVs:" not in text, "Champions no tiene IVs: no debe emitirse la linea")
    check("- Kowtow Cleave" in text and "- High Horsepower" in text, "faltan movimientos")


def test_champions_stat_rules() -> None:
    """Los SP se emiten en la escala del juego y suman 66 en todos."""
    data = json.loads((FIXTURES / "team.expected.json").read_text())
    mons = paste.normalize_team(RawTeam.model_validate(data["team"]))

    for mon in mons:
        name = mon["species"]["value"]
        total = sum(mon["sp"].values())
        check(total == champions.MAX_SP_TOTAL, f"{name}: los SP suman {total}, no 66")
        check(max(mon["sp"].values()) <= champions.MAX_SP_PER_STAT,
              f"{name}: alguna estadistica pasa de 32 SP")
        check(mon["evs"] == mon["sp"], f"{name}: por defecto el paste lleva los SP en crudo")

    text = paste.render_team(mons)
    check("EVs: 9 HP / 25 SpA / 32 Spe" in text, "Salamence debe llevar sus SP tal cual")
    check("Timid Nature" in text, "Salamence: +Spe/-Atk es Timid")
    check("Modest Nature" in text, "Sylveon: +SpA/-Atk es Modest")
    check(text.count("Adamant Nature") == 3, "tres del equipo son Adamant")


def test_stats_match_screenshot() -> None:
    """Recalcular las estadisticas debe reproducir los numeros de la captura.

    Es la verificacion que cierra el circulo: si los SP, la especie o las flechas
    se hubieran leido mal, el valor recalculado dejaria de cuadrar.
    """
    data = json.loads((FIXTURES / "team.expected.json").read_text())
    for entry in data["team"]["pokemon"]:
        evs = champions.sp_to_evs({k: v for k, v in entry["sp"].items()})
        got = champions.expected_stats(
            entry["species"], evs, entry["boosted_stat"], entry["hindered_stat"]
        )
        check(got == entry["stats"],
              f"{entry['species']}: recalculado {got} frente a la captura {entry['stats']}")


def test_legacy_scale() -> None:
    """En escala clasica cada SP vale 8 EVs, con tope de 252."""
    data = json.loads((FIXTURES / "team.expected.json").read_text())
    mons = paste.normalize_team(RawTeam.model_validate(data["team"]), legacy=True)
    salamence = mons[0]
    check(salamence["evs"]["speed"] == 252, "32 SP se topan en 252 EVs, no 256")
    check(salamence["evs"]["hp"] == 72, "9 SP son 72 EVs")
    check(any("508" in w for w in salamence["warnings"]),
          "en escala clasica hay que avisar de que se pasa de 508")


def test_sp_checksum() -> None:
    """Un total distinto de 66 delata un numero mal leido."""
    team = RawTeam.model_validate({"pokemon": [{
        "species": "Incineroar", "moves": ["Fake Out"],
        "sp": {"hp": 32, "atk": 32, "defense": 0, "sp_atk": 0, "sp_def": 0, "speed": 0},
    }]})
    warnings = " ".join(paste.normalize_team(team)[0]["warnings"])
    check("66" in warnings, "un total de 64 SP debe avisarse")

    team = RawTeam.model_validate({"pokemon": [{
        "species": "Incineroar", "moves": ["Fake Out"],
        "sp": {"hp": 40, "atk": 26, "defense": 0, "sp_atk": 0, "sp_def": 0, "speed": 0},
    }]})
    warnings = " ".join(paste.normalize_team(team)[0]["warnings"])
    check("32" in warnings, "40 SP en una estadistica supera el tope y debe avisarse")


def test_nature_grid() -> None:
    """La rejilla de naturalezas cubre las 20 combinaciones no neutras."""
    stats = ["atk", "defense", "sp_atk", "sp_def", "speed"]
    seen = {champions.nature_from_arrows(u, d) for u in stats for d in stats}
    check(None in seen, "las combinaciones neutras deben dar None")
    check(len(seen - {None}) == 20, f"esperadas 20 naturalezas, hay {len(seen - {None})}")


def test_canonical_round_trip() -> None:
    """Todo nombre canonico debe reconocerse tal cual, sin pasar por el fuzzy."""
    for label, vocab in [("especies", dex.species), ("movimientos", dex.moves),
                         ("objetos", dex.items), ("habilidades", dex.abilities)]:
        bad = [n for n in vocab.names if (m := vocab.match(n)).value != n or not m.exact]
        check(not bad, f"{label}: {len(bad)} no hacen round-trip, p.ej. {bad[:3]}")


def test_typo_recovery() -> None:
    """Ante el error tipico de OCR (un caracter perdido) debe recuperar el nombre."""
    random.seed(7)
    for label, vocab in [("especies", dex.species), ("movimientos", dex.moves),
                         ("objetos", dex.items), ("habilidades", dex.abilities)]:
        ok = total = 0
        for name in vocab.names:
            letters = [i for i, c in enumerate(name) if c.isalpha()]
            if len(letters) < 4:
                continue
            i = random.choice(letters)
            total += 1
            ok += vocab.match(name[:i] + name[i + 1:]).value == name
        rate = ok / total
        check(rate >= 0.99, f"{label}: solo recupera el {rate:.1%}, por debajo del 99%")


def test_no_silent_drops() -> None:
    """Un valor irreconocible se avisa; nunca desaparece sin mas."""
    team = RawTeam.model_validate({"pokemon": [{
        "species": "Incineroar", "item": "Zzzzzz", "tera_type": "Qqqqqq",
        "ability": "Intimidate", "moves": ["Fake Out"],
    }]})
    mon = paste.normalize_team(team)[0]
    joined = " ".join(mon["warnings"])
    check("Zzzzzz" in joined, "un objeto irreconocible debe avisarse")
    check("Qqqqqq" in joined, "un tipo tera irreconocible debe avisarse")


def test_move_slots_keep_position() -> None:
    """Los huecos vacios conservan su indice para que las marcas cuadren."""
    team = RawTeam.model_validate({"pokemon": [
        {"species": "Incineroar", "moves": ["Fake Out", "", "Knock Of", ""]}
    ]})
    mon = paste.normalize_team(team)[0]
    check(len(mon["moves"]) == 4, "deben conservarse los cuatro huecos")
    check(mon["moves"][2]["value"] == "Knock Off", "la correccion debe caer en el indice 2")
    check(len(mon["warnings"]) == 1, "los huecos vacios no deben generar avisos")
    check(paste.render_mon(mon).count("\n- ") == 2, "el paste solo lleva los movimientos reales")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  {test.__name__}")
    if failures:
        print(f"\n{len(failures)} FALLOS:")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print(f"\n{len(tests)} pruebas OK")
