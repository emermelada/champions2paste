"""The contract shared by every vision engine."""

from __future__ import annotations

from typing import Protocol

from ..schema import RawTeam

# The model transcribes; it does not correct. Spelling is fixed downstream by
# dex.py against Showdown's real vocabulary, which is far more accurate than a
# model guessing what the text it just read was supposed to say.
PROMPT = """You are reading screenshots of the "Replicate This Battle Team?"
screen from the video game Pokemon Champions.

SCREEN LAYOUT

At the top there is a "Team ID" and two tabs; the active one is highlighted in
green:
- "Moves & More": species, genders, abilities, held items and moves.
- "Stats": nature, stat points (SP) and, if present, Tera type.

Below are up to six cards in two columns and three rows. Each card carries a
large, faint background number from 1 to 6, which is its position in the team:
1 and 2 on top (left and right), 3 and 4 in the middle, 5 and 6 at the bottom.
Return the Pokemon ordered by that number.

On the "Moves & More" tab each card contains:
- At the top, in large type, the species name.
- To its right, a gender symbol and one or two type icons.
- Directly below the name and with no icon, the ABILITY.
- Below that and with an item icon, the held ITEM.
- In the right-hand column, the four MOVES, each with an icon.

On the "Stats" tab each card contains the six stats in two columns: HP, Attack
and Defense on the left; Sp. Atk, Sp. Def and Speed on the right. Each row reads,
in this order:

  [icon] [name] [arrows?] [LARGE NUMBER] [bar] [small number]

- The LARGE NUMBER, next to the name, is the stat's final value (usually three
  digits). It goes in `stats`.
- The small number, at the end of the row after the coloured bar, is the points
  invested: 0 to 32. It goes in `sp`. The six ALWAYS add up to 66.
- Arrows appear on only two stats: pink ones pointing UP on the boosted stat
  (`boosted_stat`) and blue ones pointing DOWN on the hindered stat
  (`hindered_stat`). That is how the nature is shown, since it is never written
  anywhere. If you see no arrows, leave both fields null.
- Use these identifiers for the arrows: hp, atk, defense, sp_atk, sp_def, speed.

Do not confuse the two numbers: the large one is around 50-250 and the small one
never exceeds 32. If a Pokemon has 0 points in a stat, the small number is 0 and
the bar looks empty.

WHAT TO IGNORE

The type icons beside the name are the Pokemon's types, and the icons beside each
move are the move's type. They are decorative: both can be derived from the
species and the move. Do not transcribe them and do not use them to fill in
`tera_type`. The Tera type, if it exists, only appears on the "Stats" tab.

RULES

- Identify each screenshot by its highlighted tab, not by the order they reach
  you. If you are given two screenshots of the same tab, they are the same
  screen: return a single team of six, not twelve Pokemon.
- Transcribe EXACTLY what you read, character by character. Do not fix spelling,
  do not complete names and do not translate them.
- Use null for any field that does not appear in the screenshots. Do not infer
  it, do not invent it and do not fall back on that Pokemon's "typical" values.
  Without the "Stats" tab, `sp`, `stats`, `boosted_stat` and `hindered_stat` are
  all null.
- Champions has no IVs and never shows the nature's name: do not try to fill
  those in.
- The ability is the line without an icon below the name; the item is the line
  with an icon. Do not swap them.
- `gender` is "M" for the male symbol, "F" for the female one, and null if
  neither is shown.
- Set `nickname` only if the nickname differs from the species name.
- Copy the header's "Team ID" into `team_id`.
"""


class VisionBackend(Protocol):
    """Turns one or two screenshots into an un-normalised team."""

    name: str

    def extract(self, images: list[tuple[str, bytes]]) -> RawTeam:
        """`images` are (media_type, bytes) pairs in on-screen order."""
        ...
