"""Registro de motores de vision, seleccionable por la variable VISION_BACKEND."""

from __future__ import annotations

import functools
import os

from .base import VisionBackend

BACKENDS = ("ocr", "ollama", "claude")


@functools.lru_cache(maxsize=None)
def get_backend(name: str | None = None) -> VisionBackend:
    name = (name or os.environ.get("VISION_BACKEND", "ocr")).lower()

    if name == "ocr":
        from .ocr import OcrBackend
        return OcrBackend()
    if name == "ollama":
        from .ollama import OllamaBackend
        return OllamaBackend()
    if name == "claude":
        from .claude import ClaudeBackend
        return ClaudeBackend()

    raise ValueError(f"Motor desconocido: {name!r}. Opciones: {', '.join(BACKENDS)}")
