"""Normalizacion de un equipo leido y renderizado al formato paste de Showdown."""

from __future__ import annotations

from . import champions, dex
from .schema import RawMon, RawStats, RawTeam


def _field(match: dex.Match) -> dict:
    return {"value": match.value, "raw": match.raw, "exact": match.exact}


def _stats(raw: RawStats | None) -> dict[str, int]:
    if raw is None:
        return {}
    return {key: value for key in dex.STAT_ORDER if (value := getattr(raw, key)) is not None}


def _check_sp(sp: dict[str, int], warnings: list[str]) -> None:
    """Champions reparte siempre 66 SP, con 32 como tope por estadistica.

    Es un checksum gratuito: si la lectura no cuadra, algun numero se ha leido mal.
    """
    if not sp:
        return
    for key, value in sp.items():
        if value > champions.MAX_SP_PER_STAT:
            warnings.append(
                f"{dex.STAT_LABELS[key]} tiene {value} SP, por encima del maximo de "
                f"{champions.MAX_SP_PER_STAT}: seguramente esta mal leido"
            )
    total = sum(sp.values())
    if total != champions.MAX_SP_TOTAL:
        warnings.append(
            f"Los SP suman {total} y en Champions siempre suman "
            f"{champions.MAX_SP_TOTAL}: revisa los numeros pequenos"
        )


def _check_stats(species: str | None, evs: dict[str, int], shown: dict[str, int],
                 boosted: str | None, hindered: str | None, warnings: list[str]) -> None:
    """Recalcula las estadisticas y las contrasta con las que muestra la captura.

    Cierra el circulo: si los SP, la especie o las flechas se leyeron mal, el
    valor recalculado deja de cuadrar con el numero grande de la pantalla.
    """
    if not species or not shown:
        return
    expected = champions.expected_stats(species, evs, boosted, hindered)
    if expected is None:
        return
    for key, value in shown.items():
        if expected[key] != value:
            warnings.append(
                f"{dex.STAT_LABELS[key]}: la captura muestra {value} pero con estos SP "
                f"deberia ser {expected[key]}"
            )


def normalize_mon(raw: RawMon, legacy: bool = False) -> dict:
    """Ancla cada campo leido al vocabulario de Showdown y recoge las dudas."""
    resolved = {
        "species": _field(dex.species.match(raw.species)),
        "item": _field(dex.items.match(raw.item)),
        "ability": _field(dex.abilities.match(raw.ability)),
        "tera_type": _field(dex.tera.match(raw.tera_type)),
        # Los huecos vacios se conservan para que los indices sigan cuadrando con
        # los campos del editor; se descartan al renderizar, no aqui.
        "moves": [_field(dex.moves.match(m)) for m in raw.moves],
        "nickname": raw.nickname,
        "gender": raw.gender if raw.gender in {"M", "F"} else None,
        "sp": _stats(raw.sp),
        "boosted_stat": raw.boosted_stat if raw.boosted_stat in dex.STAT_ORDER else None,
        "hindered_stat": raw.hindered_stat if raw.hindered_stat in dex.STAT_ORDER else None,
    }

    warnings: list[str] = []
    species = resolved["species"]["value"]

    if species is None:
        warnings.append(f"Especie no reconocida: {raw.species!r}")
    elif not resolved["species"]["exact"]:
        warnings.append(f"Especie corregida: {raw.species!r} -> {species}")

    for label, key in (
        ("Objeto", "item"), ("Habilidad", "ability"), ("Tipo Tera", "tera_type"),
    ):
        field = resolved[key]
        if field["raw"] and field["value"] is None:
            warnings.append(f"{label} no reconocido: {field['raw']!r}")
        elif field["value"] and not field["exact"]:
            warnings.append(f"{label} corregido: {field['raw']!r} -> {field['value']}")

    for move in resolved["moves"]:
        if not move["raw"].strip():
            continue
        if move["value"] is None:
            warnings.append(f"Movimiento no reconocido: {move['raw']!r}")
        elif not move["exact"]:
            warnings.append(f"Movimiento corregido: {move['raw']!r} -> {move['value']}")

    _check_sp(resolved["sp"], warnings)

    resolved["nature"] = champions.nature_from_arrows(
        resolved["boosted_stat"], resolved["hindered_stat"]
    )

    # La verificacion siempre usa la escala clasica: es en la que opera la
    # formula del juego, independientemente de como se emita el paste.
    _check_stats(species, champions.sp_to_evs(resolved["sp"]), _stats(raw.stats),
                 resolved["boosted_stat"], resolved["hindered_stat"], warnings)

    evs = champions.paste_evs(resolved["sp"], legacy)
    if legacy and sum(evs.values()) > champions.MAX_EV_TOTAL:
        warnings.append(
            f"En escala clasica el spread suma {sum(evs.values())} EVs, por encima de los "
            f"{champions.MAX_EV_TOTAL} que admite un formato antiguo de Showdown"
        )

    resolved["evs"] = evs
    resolved["ev_total"] = sum(evs.values())
    resolved["warnings"] = warnings
    return resolved


def normalize_team(team: RawTeam, legacy: bool = False) -> list[dict]:
    return [normalize_mon(mon, legacy) for mon in team.pokemon]


def _ev_line(evs: dict[str, int]) -> str | None:
    parts = [
        f"{value} {dex.STAT_LABELS[key]}"
        for key in dex.STAT_ORDER
        if (value := evs.get(key))
    ]
    return f"EVs: {' / '.join(parts)}" if parts else None


def render_mon(mon: dict, level: int | None = champions.LEVEL) -> str:
    species = mon["species"]["value"] or mon["species"]["raw"]

    head = f"{mon['nickname']} ({species})" if mon.get("nickname") else species
    if mon.get("gender"):
        head += f" ({mon['gender']})"
    if item := mon["item"]["value"]:
        head += f" @ {item}"

    lines = [head]
    if ability := mon["ability"]["value"]:
        lines.append(f"Ability: {ability}")
    if level:
        lines.append(f"Level: {level}")
    if tera_type := mon["tera_type"]["value"]:
        lines.append(f"Tera Type: {tera_type}")
    if ev_line := _ev_line(mon["evs"]):
        lines.append(ev_line)
    if nature := mon.get("nature"):
        lines.append(f"{nature} Nature")
    # Champions no tiene IVs: equivalen a 31, que es justo lo que Showdown asume
    # cuando el paste no lleva linea de IVs. Por eso no se emite ninguna.

    lines.extend(
        f"- {m['value'] or m['raw']}" for m in mon["moves"] if m["raw"].strip()
    )
    return "\n".join(lines)


def render_team(mons: list[dict], level: int | None = champions.LEVEL) -> str:
    return "\n\n".join(render_mon(mon, level) for mon in mons)
