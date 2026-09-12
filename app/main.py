"""API HTTP: capturas de Pokemon Champions -> paste de Pokemon Showdown."""

from __future__ import annotations

import os
import pathlib

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import dex, paste
from .schema import RawTeam
from .vision import get_backend

STATIC = pathlib.Path(__file__).resolve().parent / "static"
MAX_IMAGE_BYTES = int(os.environ.get("MAX_IMAGE_BYTES", 8 * 1024 * 1024))
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}

app = FastAPI(title="champions2paste", docs_url="/api/docs")


class RenderRequest(BaseModel):
    team: RawTeam
    level: int | None = Field(default=50, ge=1, le=100)
    legacy: bool = Field(default=False, description="Emitir EVs en la escala clasica (1 SP = 8 EVs)")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "backend": os.environ.get("VISION_BACKEND", "ocr")}


@app.get("/api/vocab")
def vocab() -> dict:
    """Alimenta el autocompletado del editor con los nombres canonicos."""
    return {
        "species": dex.species.names,
        "moves": dex.moves.names,
        "items": dex.items.names,
        "abilities": dex.abilities.names,
        "stat_order": dex.STAT_ORDER,
        "stat_labels": dex.STAT_LABELS,
        "natures": dex.NATURES,
        "tera": dex.TERA_TYPES,
    }


async def _read_images(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if not files:
        raise HTTPException(400, "Sube al menos una captura")
    if len(files) > 2:
        raise HTTPException(400, "Como maximo dos capturas: equipo y entrenamiento")

    images: list[tuple[str, bytes]] = []
    for upload in files:
        if upload.content_type not in ALLOWED_TYPES:
            raise HTTPException(
                400, f"Formato no soportado: {upload.content_type}. Usa PNG, JPEG o WebP."
            )
        data = await upload.read()
        if not data:
            raise HTTPException(400, f"{upload.filename} esta vacio")
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(
                413, f"{upload.filename} supera el limite de {MAX_IMAGE_BYTES // 1024 // 1024} MB"
            )
        images.append((upload.content_type, data))
    return images


@app.post("/api/extract")
async def extract(files: list[UploadFile] = File(...), level: int = 50,
                  legacy: bool = False) -> dict:
    images = await _read_images(files)

    try:
        team = get_backend().extract(images)
    except ValueError as exc:                      # motor mal configurado
        raise HTTPException(500, str(exc)) from exc
    except Exception as exc:                       # fallo del modelo o de la red
        raise HTTPException(502, f"El motor de vision fallo: {exc}") from exc

    if not team.pokemon:
        raise HTTPException(
            422, "No se reconocio ningun Pokemon en las capturas. Prueba con una imagen mas nitida."
        )

    mons = paste.normalize_team(team, legacy)
    return {"team": team.model_dump(), "mons": mons, "paste": paste.render_team(mons, level)}


@app.post("/api/render")
def render(request: RenderRequest) -> dict:
    """Re-normaliza y re-renderiza tras editar a mano, sin volver a llamar al modelo."""
    mons = paste.normalize_team(request.team, request.legacy)
    return {"mons": mons, "paste": paste.render_team(mons, request.level)}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
