"""Forma de los datos que el motor de vision debe devolver.

Refleja lo que hay EN PANTALLA en Pokemon Champions, no el modelo de Showdown:
puntos SP en lugar de EVs, flechas en lugar del nombre de la naturaleza, y sin
IVs porque el juego no los tiene. La traduccion la hace `app/champions.py`.
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
    species: str = Field(description="Nombre de la especie tal y como aparece en pantalla")
    nickname: str | None = Field(default=None, description="Apodo, solo si difiere de la especie")
    gender: str | None = Field(default=None, description="'M', 'F' o null si no se muestra")
    item: str | None = Field(default=None, description="Objeto equipado")
    ability: str | None = Field(default=None, description="Habilidad")
    tera_type: str | None = Field(default=None, description="Tipo Teracristal, si el juego lo muestra")
    moves: list[str] = Field(default_factory=list, description="Movimientos, en orden")

    sp: RawStats | None = Field(
        default=None,
        description="Puntos invertidos en cada estadistica: el numero PEQUENO de la derecha, de 0 a 32",
    )
    stats: RawStats | None = Field(
        default=None,
        description="Valor final de cada estadistica: el numero GRANDE de la izquierda",
    )
    boosted_stat: str | None = Field(
        default=None,
        description=f"Estadistica con flechas rojas hacia arriba. Uno de: {STAT_FIELDS}",
    )
    hindered_stat: str | None = Field(
        default=None,
        description=f"Estadistica con flechas azules hacia abajo. Uno de: {STAT_FIELDS}",
    )


class RawTeam(BaseModel):
    pokemon: list[RawMon] = Field(description="Los Pokemon del equipo, ordenados por su numero de tarjeta")
    team_id: str | None = Field(default=None, description="El 'Team ID' de la cabecera, si se ve")
