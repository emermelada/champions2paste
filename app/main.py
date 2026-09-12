"""HTTP API: Pokemon Champions screenshots -> Pokemon Showdown paste."""

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
    legacy: bool = Field(default=False, description="Emit EVs on the classic scale (1 SP = 8 EVs)")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "backend": os.environ.get("VISION_BACKEND", "ocr")}


@app.get("/api/vocab")
def vocab() -> dict:
    """Feeds the editor's autocomplete with the canonical names."""
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
        raise HTTPException(400, "Upload at least one screenshot")
    if len(files) > 2:
        raise HTTPException(400, "Two screenshots at most: Moves & More and Stats")

    images: list[tuple[str, bytes]] = []
    for upload in files:
        if upload.content_type not in ALLOWED_TYPES:
            raise HTTPException(
                400, f"Unsupported format: {upload.content_type}. Use PNG, JPEG or WebP."
            )
        data = await upload.read()
        if not data:
            raise HTTPException(400, f"{upload.filename} is empty")
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(
                413, f"{upload.filename} exceeds the {MAX_IMAGE_BYTES // 1024 // 1024} MB limit"
            )
        images.append((upload.content_type, data))
    return images


@app.post("/api/extract")
async def extract(files: list[UploadFile] = File(...), level: int = 50,
                  legacy: bool = False) -> dict:
    images = await _read_images(files)

    try:
        team = get_backend().extract(images)
    except ValueError as exc:                      # misconfigured engine
        raise HTTPException(500, str(exc)) from exc
    except Exception as exc:                       # engine or network failure
        raise HTTPException(502, f"The vision engine failed: {exc}") from exc

    if not team.pokemon:
        raise HTTPException(
            422, "No Pokemon were recognised in the screenshots. Try a sharper image."
        )

    mons = paste.normalize_team(team, legacy)
    return {"team": team.model_dump(), "mons": mons, "paste": paste.render_team(mons, level)}


@app.post("/api/render")
def render(request: RenderRequest) -> dict:
    """Re-normalise and re-render after a manual edit, without calling the engine."""
    mons = paste.normalize_team(request.team, request.legacy)
    return {"mons": mons, "paste": paste.render_team(mons, request.level)}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
