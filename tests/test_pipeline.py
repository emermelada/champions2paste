"""Tests for the normalisation and rendering pipeline.

No external dependencies: `python tests/test_pipeline.py`.
The fixture is a real Pokemon Champions screenshot (Regulation M-C).
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
    """The team from the two real screenshots must come out without a single fix."""
    data = json.loads((FIXTURES / "team.expected.json").read_text())
    team = RawTeam.model_validate(data["team"])
    mons = paste.normalize_team(team)
    text = paste.render_team(mons, data["level"])

    check(len(mons) == 6, f"expected 6 Pokemon, got {len(mons)}")

    warnings = [w for mon in mons for w in mon["warnings"]]
    check(not warnings, f"the real screenshots should raise no warnings: {warnings}")

    # The team carries a mega stone: Champions allows mega evolution, and the
    # paste's ability must be the base form's, not the mega's.
    check("Salamence (F) @ Salamencite" in text, "Salamence's line with its stone is missing")
    check("Ability: Intimidate" in text, "Salamence must keep Intimidate, not Aerilate")

    check(text.count("Level: 50") == 6, "all six must be level 50")
    check("IVs:" not in text, "Champions has no IVs: the line must not be emitted")
    check("- Kowtow Cleave" in text and "- High Horsepower" in text, "moves are missing")


def test_champions_stat_rules() -> None:
    """SP are emitted on the game's own scale and total 66 for every Pokemon."""
    data = json.loads((FIXTURES / "team.expected.json").read_text())
    mons = paste.normalize_team(RawTeam.model_validate(data["team"]))

    for mon in mons:
        name = mon["species"]["value"]
        total = sum(mon["sp"].values())
        check(total == champions.MAX_SP_TOTAL, f"{name}: SP total {total}, not 66")
        check(max(mon["sp"].values()) <= champions.MAX_SP_PER_STAT,
              f"{name}: some stat exceeds 32 SP")
        check(mon["evs"] == mon["sp"], f"{name}: by default the paste carries raw SP")

    text = paste.render_team(mons)
    check("EVs: 9 HP / 25 SpA / 32 Spe" in text, "Salamence must carry its SP as-is")
    check("Timid Nature" in text, "Salamence: +Spe/-Atk is Timid")
    check("Modest Nature" in text, "Sylveon: +SpA/-Atk is Modest")
    check(text.count("Adamant Nature") == 3, "three of the team are Adamant")


def test_stats_match_screenshot() -> None:
    """Recomputing the stats must reproduce the numbers in the screenshot.

    This is the check that closes the loop: had the SP, the species or the arrows
    been misread, the recomputed value would stop matching.
    """
    data = json.loads((FIXTURES / "team.expected.json").read_text())
    for entry in data["team"]["pokemon"]:
        evs = champions.sp_to_evs({k: v for k, v in entry["sp"].items()})
        got = champions.expected_stats(
            entry["species"], evs, entry["boosted_stat"], entry["hindered_stat"]
        )
        check(got == entry["stats"],
              f"{entry['species']}: recomputed {got} against screenshot {entry['stats']}")


def test_legacy_scale() -> None:
    """On the classic scale each SP is worth 8 EVs, capped at 252."""
    data = json.loads((FIXTURES / "team.expected.json").read_text())
    mons = paste.normalize_team(RawTeam.model_validate(data["team"]), legacy=True)
    salamence = mons[0]
    check(salamence["evs"]["speed"] == 252, "32 SP cap at 252 EVs, not 256")
    check(salamence["evs"]["hp"] == 72, "9 SP is 72 EVs")
    check(any("508" in w for w in salamence["warnings"]),
          "on the classic scale exceeding 508 must be warned about")


def test_sp_checksum() -> None:
    """A total other than 66 gives away a misread number."""
    team = RawTeam.model_validate({"pokemon": [{
        "species": "Incineroar", "moves": ["Fake Out"],
        "sp": {"hp": 32, "atk": 32, "defense": 0, "sp_atk": 0, "sp_def": 0, "speed": 0},
    }]})
    warnings = " ".join(paste.normalize_team(team)[0]["warnings"])
    check("66" in warnings, "a total of 64 SP must be flagged")

    team = RawTeam.model_validate({"pokemon": [{
        "species": "Incineroar", "moves": ["Fake Out"],
        "sp": {"hp": 40, "atk": 26, "defense": 0, "sp_atk": 0, "sp_def": 0, "speed": 0},
    }]})
    warnings = " ".join(paste.normalize_team(team)[0]["warnings"])
    check("32" in warnings, "40 SP in one stat is over the cap and must be flagged")


def test_nature_grid() -> None:
    """The nature grid covers all 20 non-neutral combinations."""
    stats = ["atk", "defense", "sp_atk", "sp_def", "speed"]
    seen = {champions.nature_from_arrows(u, d) for u in stats for d in stats}
    check(None in seen, "neutral combinations must return None")
    check(len(seen - {None}) == 20, f"expected 20 natures, got {len(seen - {None})}")


def test_canonical_round_trip() -> None:
    """Every canonical name must be recognised as-is, without fuzzy matching."""
    for label, vocab in [("species", dex.species), ("moves", dex.moves),
                         ("items", dex.items), ("abilities", dex.abilities)]:
        bad = [n for n in vocab.names if (m := vocab.match(n)).value != n or not m.exact]
        check(not bad, f"{label}: {len(bad)} fail to round-trip, e.g. {bad[:3]}")


def test_typo_recovery() -> None:
    """Given the typical OCR error (a dropped character) the name must come back."""
    random.seed(7)
    for label, vocab in [("species", dex.species), ("moves", dex.moves),
                         ("items", dex.items), ("abilities", dex.abilities)]:
        ok = total = 0
        for name in vocab.names:
            letters = [i for i, c in enumerate(name) if c.isalpha()]
            if len(letters) < 4:
                continue
            i = random.choice(letters)
            total += 1
            ok += vocab.match(name[:i] + name[i + 1:]).value == name
        rate = ok / total
        check(rate >= 0.99, f"{label}: only recovers {rate:.1%}, below 99%")


def test_no_silent_drops() -> None:
    """An unrecognisable value is flagged; it never just disappears."""
    team = RawTeam.model_validate({"pokemon": [{
        "species": "Incineroar", "item": "Zzzzzz", "tera_type": "Qqqqqq",
        "ability": "Intimidate", "moves": ["Fake Out"],
    }]})
    mon = paste.normalize_team(team)[0]
    joined = " ".join(mon["warnings"])
    check("Zzzzzz" in joined, "an unrecognisable item must be flagged")
    check("Qqqqqq" in joined, "an unrecognisable tera type must be flagged")


def test_move_slots_keep_position() -> None:
    """Empty slots keep their index so the editor's markers line up."""
    team = RawTeam.model_validate({"pokemon": [
        {"species": "Incineroar", "moves": ["Fake Out", "", "Knock Of", ""]}
    ]})
    mon = paste.normalize_team(team)[0]
    check(len(mon["moves"]) == 4, "all four slots must be preserved")
    check(mon["moves"][2]["value"] == "Knock Off", "the correction must land on index 2")
    check(len(mon["warnings"]) == 1, "empty slots must not raise warnings")
    check(paste.render_mon(mon).count("\n- ") == 2, "the paste carries only the real moves")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  {test.__name__}")
    if failures:
        print(f"\n{len(failures)} FAILURES:")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print(f"\n{len(tests)} tests passed")
