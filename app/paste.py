"""Normalising a read team and rendering it as a Showdown paste."""

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
    """Champions always spends 66 SP, with 32 as the per-stat cap.

    A free checksum: if the numbers do not add up, something was misread.
    """
    if not sp:
        return
    for key, value in sp.items():
        if value > champions.MAX_SP_PER_STAT:
            warnings.append(
                f"{dex.STAT_LABELS[key]} has {value} SP, above the maximum of "
                f"{champions.MAX_SP_PER_STAT}: it was most likely misread"
            )
    total = sum(sp.values())
    if total != champions.MAX_SP_TOTAL:
        warnings.append(
            f"SP add up to {total}, and in Champions they always total "
            f"{champions.MAX_SP_TOTAL}: check the small numbers"
        )


def _check_stats(species: str | None, evs: dict[str, int], shown: dict[str, int],
                 boosted: str | None, hindered: str | None, warnings: list[str]) -> None:
    """Recompute the stats and check them against the ones on screen.

    This closes the loop: if the SP, the species or the arrows were misread, the
    recomputed value stops matching the large number in the screenshot.
    """
    if not species or not shown:
        return
    expected = champions.expected_stats(species, evs, boosted, hindered)
    if expected is None:
        return
    for key, value in shown.items():
        if expected[key] != value:
            warnings.append(
                f"{dex.STAT_LABELS[key]}: the screenshot shows {value} but with these SP "
                f"it should be {expected[key]}"
            )


def normalize_mon(raw: RawMon, legacy: bool = False) -> dict:
    """Anchor every read field to Showdown's vocabulary and collect the doubts."""
    resolved = {
        "species": _field(dex.species.match(raw.species)),
        "item": _field(dex.items.match(raw.item)),
        "ability": _field(dex.abilities.match(raw.ability)),
        "tera_type": _field(dex.tera.match(raw.tera_type)),
        # Empty slots are kept so the indices stay aligned with the editor's
        # fields; they are dropped at render time, not here.
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
        warnings.append(f"Species not recognised: {raw.species!r}")
    elif not resolved["species"]["exact"]:
        warnings.append(f"Species corrected: {raw.species!r} -> {species}")

    for label, key in (
        ("Item", "item"), ("Ability", "ability"), ("Tera type", "tera_type"),
    ):
        field = resolved[key]
        if field["raw"] and field["value"] is None:
            warnings.append(f"{label} not recognised: {field['raw']!r}")
        elif field["value"] and not field["exact"]:
            warnings.append(f"{label} corrected: {field['raw']!r} -> {field['value']}")

    for move in resolved["moves"]:
        if not move["raw"].strip():
            continue
        if move["value"] is None:
            warnings.append(f"Move not recognised: {move['raw']!r}")
        elif not move["exact"]:
            warnings.append(f"Move corrected: {move['raw']!r} -> {move['value']}")

    _check_sp(resolved["sp"], warnings)

    resolved["nature"] = champions.nature_from_arrows(
        resolved["boosted_stat"], resolved["hindered_stat"]
    )

    # Verification always uses the classic scale: that is what the game's formula
    # operates on, regardless of how the paste is emitted.
    _check_stats(species, champions.sp_to_evs(resolved["sp"]), _stats(raw.stats),
                 resolved["boosted_stat"], resolved["hindered_stat"], warnings)

    evs = champions.paste_evs(resolved["sp"], legacy)
    if legacy and sum(evs.values()) > champions.MAX_EV_TOTAL:
        warnings.append(
            f"On the classic scale this spread totals {sum(evs.values())} EVs, above the "
            f"{champions.MAX_EV_TOTAL} an older Showdown format allows"
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
    # Champions has no IVs: they are equivalent to 31, which is exactly what
    # Showdown assumes when a paste carries no IVs line. So none is emitted.

    lines.extend(
        f"- {m['value'] or m['raw']}" for m in mon["moves"] if m["raw"].strip()
    )
    return "\n".join(lines)


def render_team(mons: list[dict], level: int | None = champions.LEVEL) -> str:
    return "\n\n".join(render_mon(mon, level) for mon in mons)
