"""Motor local via Ollama. Requiere una maquina con musculo (GPU o CPU x86 rapida)."""

from __future__ import annotations

import base64
import json
import os

import httpx

from ..schema import RawTeam
from .base import PROMPT


class OllamaBackend:
    name = "ollama"

    def __init__(self) -> None:
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.model = os.environ.get("OLLAMA_MODEL", "qwen3-vl:8b")
        # Un VLM leyendo dos capturas densas tarda; el timeout por defecto de
        # httpx (5s) las cortaria siempre.
        self.timeout = float(os.environ.get("OLLAMA_TIMEOUT", "600"))

    def extract(self, images: list[tuple[str, bytes]]) -> RawTeam:
        payload = {
            "model": self.model,
            "stream": False,
            # Ollama acepta un JSON Schema en `format` y restringe el decodificado
            # a el, asi que obtenemos la misma garantia estructural que con Claude.
            "format": RawTeam.model_json_schema(),
            "options": {"temperature": 0},
            "messages": [{
                "role": "user",
                "content": PROMPT,
                "images": [base64.b64encode(data).decode() for _, data in images],
            }],
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()

        content = body.get("message", {}).get("content", "")
        if not content.strip():
            raise RuntimeError(f"El modelo {self.model} devolvio una respuesta vacia")

        try:
            return RawTeam.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"Respuesta no valida de {self.model}: {exc}") from exc
