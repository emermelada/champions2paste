"""The shape of the data a vision engine must return.

It mirrors what is ON SCREEN in Pokemon Champions, not Showdown's model: SP
instead of EVs, arrows instead of a nature name, and no IVs because the game has
none. The translation happens in `app/champions.py`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

STAT_FIELDS = "hp, atk, defense, sp_atk, sp_def, speed"


class RawStats(BaseModel):
    hp: int | None = None
    atk: int | None = None
    defense: int | None = None
    sp_atk: int | None = None
    sp_def: int | None = None
    speed: int | None = None


class RawMon(BaseModel):
    species: str = Field(description="Species name exactly as it appears on screen")
    nickname: str | None = Field(default=None, description="Nickname, only if it differs from the species")
    gender: str | None = Field(default=None, description="'M', 'F', or null if not shown")
    item: str | None = Field(default=None, description="Held item")
    ability: str | None = Field(default=None, description="Ability")
    tera_type: str | None = Field(default=None, description="Tera type, if the game shows one")
    moves: list[str] = Field(default_factory=list, description="Moves, in order")

    sp: RawStats | None = Field(
        default=None,
        description="Points invested in each stat: the SMALL number on the right, 0 to 32",
    )
    stats: RawStats | None = Field(
        default=None,
        description="Each stat's final value: the LARGE number on the left",
    )
    boosted_stat: str | None = Field(
        default=None,
        description=f"The stat with pink arrows pointing up. One of: {STAT_FIELDS}",
    )
    hindered_stat: str | None = Field(
        default=None,
        description=f"The stat with blue arrows pointing down. One of: {STAT_FIELDS}",
    )


class RawTeam(BaseModel):
    pokemon: list[RawMon] = Field(description="The team's Pokemon, ordered by their card number")
    team_id: str | None = Field(default=None, description="The header's 'Team ID', if visible")
