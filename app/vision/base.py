"""Contrato comun a todos los motores de vision."""

from __future__ import annotations

from typing import Protocol

from ..schema import RawTeam

# El modelo transcribe; no corrige. La correccion ortografica la hace dex.py
# contra el vocabulario real de Showdown, que acierta mucho mas que un modelo
# adivinando a que se parecia lo que acaba de leer.
PROMPT = """Lees capturas de la pantalla "Replicate This Battle Team?" del
videojuego Pokemon Champions. Los textos estan en ingles.

MAQUETACION DE LA PANTALLA

Arriba hay un "Team ID" y dos pestanas; la activa aparece resaltada en verde:
- "Moves & More": especies, generos, habilidades, objetos y movimientos.
- "Stats": naturaleza, puntos de esfuerzo (SP) y, si los hay, IVs y Teracristal.

Debajo hay hasta seis tarjetas en dos columnas y tres filas. Cada tarjeta lleva
un numero grande y tenue de fondo, del 1 al 6, que es su posicion en el equipo:
la 1 y la 2 arriba (izquierda y derecha), la 3 y la 4 en medio, la 5 y la 6
abajo. Devuelve los Pokemon ordenados por ese numero.

En la pestana "Moves & More" cada tarjeta contiene:
- Arriba y en grande, el nombre de la especie.
- A su derecha, un simbolo de genero y uno o dos iconos de tipo.
- Justo debajo del nombre y sin icono, la HABILIDAD.
- Debajo y con un icono de objeto, el OBJETO equipado.
- En la columna derecha, los cuatro MOVIMIENTOS, cada uno con un icono.

En la pestana "Stats" cada tarjeta contiene las seis estadisticas en dos
columnas: a la izquierda HP, Attack y Defense; a la derecha Sp. Atk, Sp. Def y
Speed. Cada fila lleva, en este orden:

  [icono] [nombre] [flechas?] [NUMERO GRANDE] [barra] [numero pequeno]

- El NUMERO GRANDE, pegado al nombre, es el valor final de la estadistica
  (rondan las tres cifras). Va en `stats`.
- El numero pequeno, al final de la fila y despues de la barra de color, son los
  puntos invertidos: de 0 a 32. Va en `sp`. La suma de los seis es SIEMPRE 66.
- Las flechas solo aparecen en dos estadisticas: unas rojas hacia ARRIBA en la
  potenciada (`boosted_stat`) y unas azules hacia ABAJO en la reducida
  (`hindered_stat`). Asi se indica la naturaleza, que no se escribe en ninguna
  parte. Si no ves flechas, deja ambos campos a null.
- Usa estos identificadores para las flechas: hp, atk, defense, sp_atk, sp_def,
  speed.

No confundas los dos numeros: el grande ronda 50-250 y el pequeno nunca pasa de
32. Si un Pokemon tiene 0 puntos en una estadistica, el numero pequeno es 0 y la
barra aparece vacia.

QUE IGNORAR

Los iconos de tipo junto al nombre son los tipos del Pokemon y los iconos junto
a cada movimiento son el tipo del movimiento. Son decorativos: se deducen de la
especie y del movimiento. No los transcribas ni los uses para rellenar
`tera_type`. El Teracristal, si existe, solo aparece en la pestana "Stats".

REGLAS

- Identifica cada captura por la pestana resaltada, no por el orden en que te
  llegan. Si te dan dos capturas de la misma pestana, son la misma pantalla:
  devuelve un solo equipo de seis, no doce Pokemon.
- Transcribe EXACTAMENTE lo que lees, caracter a caracter. No corrijas la
  ortografia, no completes nombres ni los traduzcas.
- Usa null en cualquier campo que no aparezca en las capturas. No lo deduzcas,
  no lo inventes y no uses los valores "tipicos" de ese Pokemon. Sin la pestana
  "Stats", `sp`, `stats`, `boosted_stat` y `hindered_stat` van todos a null.
- Champions no tiene IVs ni muestra el nombre de la naturaleza: no intentes
  rellenarlos.
- La habilidad es la linea sin icono bajo el nombre; el objeto es la linea con
  icono. No los intercambies.
- `gender` es "M" para el simbolo masculino, "F" para el femenino y null si no
  hay ninguno.
- `nickname` solo si el mote difiere del nombre de la especie.
- Copia el "Team ID" de la cabecera en `team_id`.
"""


class VisionBackend(Protocol):
    """Convierte una o dos capturas en un equipo sin normalizar."""

    name: str

    def extract(self, images: list[tuple[str, bytes]]) -> RawTeam:
        """`images` son pares (media_type, bytes) en orden de pantalla."""
        ...
